"""Orchestration d'une session : audio → transcription → traduction → carte, notes, photos."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

import soundfile

from confmap.audio import SAMPLE_RATE, AudioSource, WavRecorder
from confmap.config import Settings
from confmap.events import (
    ContextEvent,
    Event,
    LlmUsageEvent,
    MapPositionsEvent,
    MapUpdateEvent,
    NoteEvent,
    SegmentEvent,
    SlideEvent,
    StatusEvent,
    TranslationEvent,
    new_id,
)
from confmap.llm import LlmClient, LlmError, LlmResult, NetworkUnavailable
from confmap.map_model import apply_update, is_full
from confmap.map_updater import ContentItem, request_update
from confmap.segmenter import Segmenter, SpeechDetector, SpeechSegment
from confmap.session_store import SessionLog
from confmap.transcriber import MlxWhisperTranscriber, Transcriber, is_hallucination
from confmap.translator import SegmentToTranslate, TranslatedPair, translate_batch
from confmap.vision import analyze_photo

log = logging.getLogger(__name__)

T = TypeVar("T")

MAX_LAG_SECONDS = 15.0
TRANSLATE_BATCH = 8
RETRY_MAX_SECONDS = 30.0


@dataclass
class SessionState:
    """État dérivé du journal (reconstructible par relecture)."""

    title: str = ""
    speaker: str = ""
    segments: dict[str, SegmentEvent] = field(default_factory=dict)
    translations: dict[str, str] = field(default_factory=dict)
    notes: list[NoteEvent] = field(default_factory=list)
    slides: dict[str, SlideEvent] = field(default_factory=dict)
    topics: list[dict] = field(default_factory=list)
    covered_ids: set[str] = field(default_factory=set)
    covered_text: str = ""
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    cost_usd: float = 0.0

    def apply(self, event: Event) -> None:
        """Met l'état à jour avec un événement."""
        if isinstance(event, ContextEvent):
            self.title, self.speaker = event.title, event.speaker
        elif isinstance(event, SegmentEvent) and not event.final:
            self.segments[event.id] = event
        elif isinstance(event, TranslationEvent):
            self.translations[event.segment_id] = event.text_fr
        elif isinstance(event, NoteEvent):
            self.notes.append(event)
        elif isinstance(event, SlideEvent):
            self.slides[event.photo_id] = event
        elif isinstance(event, MapUpdateEvent):
            self.topics = [dict(topic) for topic in event.topics]
            self.covered_ids.update(event.source_ids)
            self.covered_text = (self.covered_text + " " + event.source_text)[-2000:]
        elif isinstance(event, MapPositionsEvent):
            self.positions.update(event.positions)
        elif isinstance(event, LlmUsageEvent):
            self.cost_usd += event.cost_usd

    def context_line(self) -> str:
        """Contexte injecté dans tous les prompts."""
        parts = []
        if self.title:
            parts.append(f"conférence « {self.title} »")
        if self.speaker:
            parts.append(f"orateur : {self.speaker}")
        recent_notes = [note.text for note in self.notes[-5:]]
        if recent_notes:
            parts.append("notes de l'auditeur : " + " | ".join(recent_notes))
        return " ; ".join(parts)

    def untranslated_segments(self) -> list[SegmentEvent]:
        """Segments du direct sans traduction, dans l'ordre."""
        return [s for s in self.segments.values() if s.id not in self.translations]

    def pending_map_content(self) -> list[ContentItem]:
        """Contenu prêt (traduit / analysé) pas encore intégré à la carte, trié par temps."""
        timed: list[tuple[float, ContentItem]] = []
        for segment in self.segments.values():
            if segment.id in self.covered_ids or segment.id not in self.translations:
                continue
            timed.append(
                (
                    segment.t0,
                    ContentItem(segment.id, "speech", self.translations[segment.id]),
                )
            )
        for note in self.notes:
            if note.id not in self.covered_ids:
                timed.append((note.ts, ContentItem(note.id, "note", note.text)))
        for slide in self.slides.values():
            if (
                slide.status == "done"
                and slide.text_fr
                and slide.id not in self.covered_ids
            ):
                timed.append((slide.ts, ContentItem(slide.id, "slide", slide.text_fr)))
        return [item for _, item in sorted(timed, key=lambda pair: pair[0])]

    def recent_french(self, seconds: float, now: float) -> str:
        """Traductions des dernières `seconds` secondes."""
        return " ".join(
            self.translations[s.id]
            for s in self.segments.values()
            if s.id in self.translations and s.t1 >= now - seconds
        )


class SessionRuntime:
    """Fait vivre une session ouverte.

    Args:
        session: Journal de la session.
        settings: Configuration.
        llm: Client LLM.
        transcriber: Moteur Whisper.
        detector_factory: Fabrique du VAD (un par enregistrement).
    """

    def __init__(
        self,
        session: SessionLog,
        settings: Settings,
        llm: LlmClient,
        transcriber: Transcriber,
        detector_factory: Callable[[], SpeechDetector],
    ) -> None:
        """Reconstruit l'état à partir du journal."""
        self.session = session
        self.settings = settings
        self.llm = llm
        self.transcriber = transcriber
        self.detector_factory = detector_factory
        self.state = SessionState()
        for event in session.events:
            self.state.apply(event)
        self.recording = False
        self._source: AudioSource | None = None
        self._recorder: WavRecorder | None = None
        self._time_offset = self._previous_audio_duration()
        self._tasks: set[asyncio.Task] = set()
        self._segment_queue: asyncio.Queue[SpeechSegment | None] = asyncio.Queue()
        self._translate_wakeup = asyncio.Event()
        self._map_force = asyncio.Event()
        self._last_map_call = 0.0
        self._network_ok = True
        self._pending_llm = 0
        self._audio_done = asyncio.Event()
        self._audio_done.set()
        self._transcription_idle = asyncio.Event()
        self._transcription_idle.set()
        self._started = False

    # ---------- horloge ----------

    def now(self) -> float:
        """Temps de session en secondes (audio cumulé)."""
        if self._recorder is not None:
            return self._time_offset + self._recorder.samples_written / SAMPLE_RATE
        return self._time_offset

    def _previous_audio_duration(self) -> float:
        total = 0.0
        for name in self.session.meta.audio_files:
            path = self.session.directory / name
            with contextlib.suppress(RuntimeError, soundfile.LibsndfileError):
                total += soundfile.info(str(path)).duration
        return total

    # ---------- événements ----------

    def emit(self, event: Event) -> Event:
        """Ajoute un événement au journal et met l'état à jour."""
        self.state.apply(event)
        return self.session.append(event)

    def _status(self, component: str, state: str, detail: str = "") -> None:
        self.emit(
            StatusEvent(
                ts=self.now(),
                component=component,
                state=state,
                detail=detail,
                pending=self._pending_llm,
            )
        )

    # ---------- cycle de vie ----------

    def start_workers(self) -> None:
        """Lance les boucles de traduction et de carte (idempotent)."""
        if self._started:
            return
        self._started = True
        self._spawn(self._transcribe_loop())
        self._spawn(self._translate_loop())
        self._spawn(self._map_loop())
        if self.state.untranslated_segments():
            self._translate_wakeup.set()

    def start_recording(self, source: AudioSource) -> None:
        """Démarre la capture audio dans un nouveau fichier WAV."""
        if self.recording:
            return
        self.start_workers()
        index = len(self.session.meta.audio_files) + 1
        filename = "enregistrement.wav" if index == 1 else f"enregistrement-{index}.wav"
        self.session.meta.audio_files.append(filename)
        self.session.save_meta()
        self._recorder = WavRecorder(self.session.directory / filename)
        self._source = source
        self.recording = True
        self._audio_done.clear()
        self._spawn(self._audio_loop(source, self._recorder, self._time_offset))
        self._status("audio", "recording", filename)

    async def stop_recording(self) -> None:
        """Arrête la capture et attend la fin des transcriptions en cours."""
        if self._source is not None:
            self._source.stop()
        await self._audio_done.wait()
        await self._segment_queue.join()
        if self._recorder is not None:
            self._time_offset += self._recorder.samples_written / SAMPLE_RATE
            self._recorder.close()
            self._recorder = None
        self._source = None
        self.recording = False
        self._status("audio", "stopped")

    async def drain(self, timeout: float = 120.0) -> None:
        """Attend que traductions et carte aient rattrapé le contenu (fin de session)."""
        deadline = time.monotonic() + timeout
        while self.state.untranslated_segments() and time.monotonic() < deadline:
            self._translate_wakeup.set()
            await asyncio.sleep(0.5)
        if self.state.pending_map_content():
            self.force_map()
            while self.state.pending_map_content() and time.monotonic() < deadline:
                await asyncio.sleep(0.5)

    async def shutdown(self) -> None:
        """Arrête toutes les tâches."""
        if self.recording:
            await self.stop_recording()
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._started = False

    def _spawn(self, coroutine: Awaitable[None]) -> asyncio.Task:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("tâche en échec", exc_info=task.exception())

    # ---------- actions utilisateur ----------

    def set_context(self, title: str, speaker: str) -> None:
        """Change le titre et l'orateur."""
        self.emit(
            ContextEvent(ts=self.now(), title=title.strip(), speaker=speaker.strip())
        )

    def add_note(self, text: str, origin: str = "mac") -> NoteEvent:
        """Ajoute une note et déclenche une mise à jour de la carte."""
        note = self.emit(NoteEvent(ts=self.now(), text=text.strip(), origin=origin))
        self.force_map()
        return note

    def add_photo(self, raw_image: bytes) -> SlideEvent:
        """Enregistre une photo et lance son analyse."""
        photo_id = new_id()
        photos_dir = self.session.directory / "photos"
        photos_dir.mkdir(exist_ok=True)
        photo_path = photos_dir / f"{photo_id}.img"
        photo_path.write_bytes(raw_image)
        slide = self.emit(
            SlideEvent(ts=self.now(), photo_id=photo_id, status="pending")
        )
        self.start_workers()
        self._spawn(self._analyze_photo(slide, photo_path))
        return slide

    def set_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        """Mémorise les positions affichées des nœuds."""
        if positions and positions != {
            k: self.state.positions.get(k) for k in positions
        }:
            self.emit(MapPositionsEvent(ts=self.now(), positions=positions))

    def force_map(self) -> None:
        """Demande une mise à jour de la carte dès que possible."""
        self.start_workers()
        self._map_force.set()

    # ---------- appels LLM avec reprise ----------

    async def call_llm(
        self,
        purpose: str,
        model: str,
        call: Callable[[], Awaitable[tuple[T, LlmResult]]],
    ) -> T:
        """Exécute un appel LLM ; réessaie indéfiniment tant que le réseau manque.

        Les erreurs non réseau sont relancées après une seule nouvelle tentative.
        """
        delay = 1.0
        attempts = 0
        self._pending_llm += 1
        try:
            while True:
                attempts += 1
                started = time.monotonic()
                try:
                    value, result = await call()
                except NetworkUnavailable as error:
                    self._set_network(False, str(error))
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, RETRY_MAX_SECONDS)
                    continue
                except LlmError as error:
                    self.emit(
                        LlmUsageEvent(
                            ts=self.now(),
                            purpose=purpose,
                            model=model,
                            ok=False,
                            duration_ms=int((time.monotonic() - started) * 1000),
                        )
                    )
                    if attempts >= 2:
                        raise
                    log.warning("%s : %s, nouvelle tentative", purpose, error)
                    continue
                self._set_network(True)
                self.emit(
                    LlmUsageEvent(
                        ts=self.now(),
                        purpose=purpose,
                        model=model,
                        cost_usd=result.cost_usd,
                        duration_ms=result.duration_ms,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                    )
                )
                return value
        finally:
            self._pending_llm -= 1

    def _set_network(self, available: bool, detail: str = "") -> None:
        if available != self._network_ok:
            self._network_ok = available
            self._status("network", "ok" if available else "down", detail[:200])
        elif not available:
            self._status("network", "down", detail[:200])

    # ---------- boucles ----------

    async def _audio_loop(
        self, source: AudioSource, recorder: WavRecorder, offset: float
    ) -> None:
        segmenter = Segmenter(self.detector_factory())
        try:
            async for block in source.blocks():
                recorder.write(block)
                segment = segmenter.feed(block)
                if segment is not None:
                    self._queue_segment(segment, offset)
            final_segment = segmenter.flush()
            if final_segment is not None:
                self._queue_segment(final_segment, offset)
        except Exception as error:  # micro débranché, permission refusée...
            log.exception("capture audio interrompue")
            self._status("audio", "error", str(error))
        finally:
            self._audio_done.set()

    def _queue_segment(self, segment: SpeechSegment, offset: float) -> None:
        segment.t0 += offset
        segment.t1 += offset
        self._segment_queue.put_nowait(segment)

    async def _transcribe_loop(self) -> None:
        slow_streak = 0
        while True:
            segment = await self._segment_queue.get()
            try:
                if segment is None:
                    continue
                result = await self.transcriber.transcribe(segment.samples)
                lag = self.now() - segment.t1 if self.recording else 0.0
                slow_streak = slow_streak + 1 if lag > MAX_LAG_SECONDS else 0
                if (
                    slow_streak >= 3
                    and isinstance(self.transcriber, MlxWhisperTranscriber)
                    and self.transcriber.use_fallback()
                ):
                    self._status(
                        "whisper",
                        "fallback",
                        f"retard {lag:.0f} s → {self.transcriber.active_model}",
                    )
                    slow_streak = 0
                if is_hallucination(result.text):
                    continue
                self.emit(
                    SegmentEvent(
                        ts=segment.t0,
                        t0=segment.t0,
                        t1=segment.t1,
                        lang=result.lang,
                        text=result.text,
                    )
                )
                self._translate_wakeup.set()
            except Exception as error:
                log.exception("transcription en échec")
                self._status("whisper", "error", str(error))
            finally:
                self._segment_queue.task_done()

    async def _translate_loop(self) -> None:
        while True:
            await self._translate_wakeup.wait()
            self._translate_wakeup.clear()
            while pending := self.state.untranslated_segments():
                batch = pending[:TRANSLATE_BATCH]
                french_batch = [s for s in batch if s.lang == "fr"]
                foreign_batch = [s for s in batch if s.lang != "fr"]
                for segment in french_batch:  # pas d'appel pour du français
                    self.emit(
                        TranslationEvent(
                            ts=segment.ts, segment_id=segment.id, text_fr=segment.text
                        )
                    )
                if not foreign_batch:
                    continue
                history = self._translation_history(foreign_batch[0])
                to_translate = [
                    SegmentToTranslate(s.id, s.lang, s.text) for s in foreign_batch
                ]
                try:
                    translations = await self.call_llm(
                        "translate",
                        self.settings.models.translate,
                        lambda items=to_translate, past=history: translate_batch(
                            self.llm,
                            self.settings.models.translate,
                            self.state.context_line(),
                            past,
                            items,
                        ),
                    )
                except LlmError as error:
                    self._status("llm", "error", f"traduction : {error}")
                    translations = {}
                for segment in foreign_batch:
                    # Un échec définitif laisse l'original, pour ne pas bloquer la carte.
                    text = (
                        translations.get(segment.id)
                        or f"[{segment.lang}] {segment.text}"
                    )
                    self.emit(
                        TranslationEvent(
                            ts=segment.ts, segment_id=segment.id, text_fr=text
                        )
                    )
                if (
                    not self._map_force.is_set()
                    and len(self.state.pending_map_content()) >= 40
                ):
                    self._map_force.set()

    def _translation_history(self, before: SegmentEvent) -> list[TranslatedPair]:
        done = [
            s
            for s in self.state.segments.values()
            if s.id in self.state.translations and s.t0 < before.t0
        ]
        return [
            TranslatedPair(s.text, self.state.translations[s.id]) for s in done[-2:]
        ]

    async def _map_loop(self) -> None:
        interval = self.settings.map.interval_seconds
        min_gap = self.settings.map.min_gap_seconds
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._map_force.wait(), timeout=interval)
            self._map_force.clear()
            wait = self._last_map_call + min_gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            items = self.state.pending_map_content()
            if not items:
                continue
            self._last_map_call = time.monotonic()
            await self._update_map(items)

    async def _update_map(self, items: list[ContentItem]) -> None:
        map_settings = self.settings.map
        now = self.now()
        topics = [
            dict(topic, nodes=list(topic["nodes"]), edges=list(topic["edges"]))
            for topic in self.state.topics
        ]
        current_full = bool(topics) and is_full(
            topics[-1],
            now,
            map_settings.max_nodes_per_topic,
            map_settings.max_topic_seconds,
        )
        try:
            update = await self.call_llm(
                "map",
                self.settings.models.map,
                lambda: request_update(
                    self.llm,
                    self.settings.models.map,
                    self.state.context_line(),
                    topics,
                    current_full,
                    self.state.covered_text,
                    items,
                ),
            )
        except LlmError as error:
            self._status("llm", "error", f"carte : {error}")
            return
        source_ids = [item.event_id for item in items]
        added = apply_update(
            topics,
            update,
            now,
            source_ids,
            map_settings.max_nodes_per_topic,
            map_settings.max_topic_seconds,
        )
        source_text = " ".join(item.text for item in items)
        self.emit(
            MapUpdateEvent(
                ts=now,
                topics=topics,
                added_node_ids=added,
                source_ids=source_ids,
                source_text=source_text[-3000:],
            )
        )

    async def _analyze_photo(self, slide: SlideEvent, photo_path: Path) -> None:
        raw = photo_path.read_bytes()
        try:
            text = await self.call_llm(
                "vision",
                self.settings.models.vision,
                lambda: analyze_photo(
                    self.llm,
                    self.settings.models.vision,
                    self.state.context_line(),
                    self.state.recent_french(60, slide.ts),
                    raw,
                ),
            )
        except Exception as error:
            log.exception("analyse de photo en échec")
            self.emit(
                SlideEvent(
                    id=slide.id,
                    ts=slide.ts,
                    photo_id=slide.photo_id,
                    status="error",
                    text_fr=str(error)[:200],
                )
            )
            return
        self.emit(
            SlideEvent(
                id=slide.id,
                ts=slide.ts,
                photo_id=slide.photo_id,
                status="done",
                text_fr=text,
            )
        )
        photo_path.unlink(missing_ok=True)
        if text:
            self.force_map()

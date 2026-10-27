"""Fin de session : re-transcription, re-traduction, résumé, écriture dans le vault.

Chaque étape écrit un `finalize_step` ; une relance saute les étapes terminées.
"""

from __future__ import annotations

import datetime
import logging
import time
from collections import Counter
from pathlib import Path

import soundfile

from confmap.events import FinalizeStepEvent, SegmentEvent, TranslationEvent
from confmap.llm import LlmError
from confmap.runtime import SessionRuntime
from confmap.transcriber import MlxWhisperTranscriber
from confmap.translator import SegmentToTranslate, translate_batch
from confmap.vault_writer import (
    FinalNoteData,
    NoteItem,
    Summary,
    TranscriptLine,
    write_conference,
)

log = logging.getLogger(__name__)

STEPS = ("retranscribe", "retranslate", "summary", "write")
RETRANSLATE_WORDS = 1500

SUMMARY_SYSTEM = """Tu rédiges, en français, le compte rendu d'une conférence pour les notes d'un chercheur.
Tu reçois la transcription traduite, ses notes, le texte des slides photographiées et la carte des idées.
- overview : 3 à 5 phrases, le propos central et la contribution, sans formule creuse.
- key_points : 3 à 6 points clés, précis (méthodes, résultats chiffrés, noms).
- open_questions : questions ouvertes, limites ou pistes évoquées (0 à 4).
- suggested_title : titre court de la conférence (utile si l'auditeur n'en a pas saisi).
N'invente rien qui ne figure pas dans le matériau."""

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "suggested_title": {"type": "string"},
    },
    "required": ["overview", "key_points", "open_questions", "suggested_title"],
    "additionalProperties": False,
}


class Finalizer:
    """Enchaîne les étapes de finalisation d'une session."""

    def __init__(self, runtime: SessionRuntime, vault_root: Path) -> None:
        """Prépare la finalisation d'une session dont la capture est arrêtée."""
        self.runtime = runtime
        self.session = runtime.session
        self.settings = runtime.settings
        self.vault_root = vault_root

    def completed_steps(self) -> set[str]:
        """Étapes déjà terminées."""
        return {
            e.step
            for e in self.session.events
            if isinstance(e, FinalizeStepEvent) and e.state == "done"
        }

    def _step_data(self, step: str) -> dict:
        for event in reversed(self.session.events):
            if (
                isinstance(event, FinalizeStepEvent)
                and event.step == step
                and event.state == "done"
            ):
                return event.data
        return {}

    def _mark(
        self,
        step: str,
        state: str,
        detail: str = "",
        data: dict | None = None,
        output_path: str = "",
    ) -> None:
        self.runtime.emit(
            FinalizeStepEvent(
                ts=self.runtime.now(),
                step=step,
                state=state,
                detail=detail,
                data=data or {},
                output_path=output_path,
            )
        )

    async def run(self) -> Path | None:
        """Exécute les étapes restantes ; retourne le chemin de la note."""
        done = self.completed_steps()
        steps = {
            "retranscribe": self._retranscribe,
            "retranslate": self._retranslate,
            "summary": self._summary,
            "write": self._write,
        }
        for step in STEPS:
            if step in done:
                continue
            self._mark(step, "running")
            try:
                data = await steps[step]()
            except Exception as error:
                log.exception("finalisation : étape %s en échec", step)
                self._mark(step, "error", str(error)[:300])
                return None
            output_path = str(data.pop("output_path", "")) if data else ""
            self._mark(step, "done", data=data, output_path=output_path)
        return Path(self._last_output()) if self._last_output() else None

    def _last_output(self) -> str:
        for event in reversed(self.session.events):
            if (
                isinstance(event, FinalizeStepEvent)
                and event.step == "write"
                and event.output_path
            ):
                return event.output_path
        return ""

    # ---------- étapes ----------

    def _final_segments(self) -> list[SegmentEvent]:
        # Seuls les segments de la dernière re-transcription réussie comptent (une relance repart de zéro).
        started_wall = float(self._step_data("retranscribe").get("started_wall", 0.0))
        return sorted(
            (
                e
                for e in self.session.events
                if isinstance(e, SegmentEvent) and e.final and e.wall >= started_wall
            ),
            key=lambda e: e.t0,
        )

    def _translations(self) -> dict[str, str]:
        return {
            e.segment_id: e.text_fr
            for e in self.session.events
            if isinstance(e, TranslationEvent)
        }

    async def _retranscribe(self) -> dict:
        transcriber = self.runtime.transcriber
        if not isinstance(transcriber, MlxWhisperTranscriber):
            return {"skipped": True}
        started_wall = time.time()
        live_languages = Counter(s.lang for s in self.runtime.state.segments.values())
        language = live_languages.most_common(1)[0][0] if live_languages else None
        offset = 0.0
        count = 0
        for filename in self.session.meta.audio_files:
            path = self.session.directory / filename
            if not path.exists():
                continue
            detected, pieces = await transcriber.transcribe_file(
                path, self.settings.models.whisper_final, language
            )
            for piece in pieces:
                self.runtime.emit(
                    SegmentEvent(
                        ts=offset + piece.t0,
                        t0=offset + piece.t0,
                        t1=offset + piece.t1,
                        lang=detected,
                        text=piece.text,
                        final=True,
                    )
                )
                count += 1
            offset += soundfile.info(str(path)).duration
        return {"segments": count, "started_wall": started_wall}

    async def _retranslate(self) -> dict:
        segments = self._final_segments()
        if not segments:
            return {"skipped": True}
        existing = self._translations()
        todo = [s for s in segments if s.id not in existing]
        glossary = sorted(
            {
                node["label"]
                for topic in self.runtime.state.topics
                for node in topic["nodes"]
            }
        )
        context = self.runtime.state.context_line()
        if glossary:
            context += " ; glossaire de la carte : " + ", ".join(glossary[:80])
        model = self.settings.models.summary
        batch: list[SegmentEvent] = []
        words = 0
        translated = 0
        for segment in todo + [None]:  # type: ignore[list-item]
            if segment is not None:
                batch.append(segment)
                words += len(segment.text.split())
            if batch and (segment is None or words >= RETRANSLATE_WORDS):
                items = [SegmentToTranslate(s.id, s.lang, s.text) for s in batch]
                if all(s.lang == "fr" for s in batch):
                    translations = {s.id: s.text for s in batch}
                else:
                    translations = await self.runtime.call_llm(
                        "retranslate",
                        model,
                        lambda items=items: translate_batch(
                            self.runtime.llm, model, context, [], items
                        ),
                    )
                for s in batch:
                    if s.id in translations:
                        self.runtime.emit(
                            TranslationEvent(
                                ts=s.ts, segment_id=s.id, text_fr=translations[s.id]
                            )
                        )
                        translated += 1
                batch, words = [], 0
        return {"translated": translated}

    def _transcript_lines(self) -> tuple[list[TranscriptLine], str]:
        translations = self._translations()
        final = self._final_segments()
        # Repli sur le direct si la re-transcription manque ou si sa traduction est très incomplète.
        if final and sum(1 for s in final if s.id in translations) >= 0.8 * len(final):
            chosen = final
        else:
            chosen = sorted(self.runtime.state.segments.values(), key=lambda s: s.t0)
        languages = Counter(s.lang for s in chosen)
        source_lang = languages.most_common(1)[0][0] if languages else "und"
        lines = [
            TranscriptLine(
                t0=s.t0,
                t1=s.t1,
                text_original=s.text,
                text_fr=translations.get(s.id, s.text),
                lang=s.lang,
            )
            for s in chosen
        ]
        return lines, source_lang

    def _note_items(self) -> list[NoteItem]:
        state = self.runtime.state
        items = [NoteItem(ts=n.ts, kind="note", text=n.text) for n in state.notes]
        items += [
            NoteItem(ts=s.ts, kind="slide", text=s.text_fr)
            for s in state.slides.values()
            if s.status == "done" and s.text_fr
        ]
        return sorted(items, key=lambda item: item.ts)

    async def _summary(self) -> dict:
        lines, _ = self._transcript_lines()
        state = self.runtime.state
        transcript = " ".join(line.text_fr for line in lines)
        notes = "\n".join(f"- [{item.kind}] {item.text}" for item in self._note_items())
        topics = "\n".join(
            f"- {t['title']} ({t['kind']}) : "
            + ", ".join(n["label"] for n in t["nodes"])
            for t in state.topics
        )
        prompt = (
            f"CONTEXTE : {state.context_line() or '(aucun)'}\n\n"
            f"CARTE DES IDÉES :\n{topics or '(vide)'}\n\n"
            f"NOTES ET SLIDES :\n{notes or '(aucune)'}\n\n"
            f'TRANSCRIPTION TRADUITE :\n"""\n{transcript[-120_000:]}\n"""'
        )
        if not transcript and not notes:
            return {
                "overview": "Aucun contenu enregistré.",
                "key_points": [],
                "open_questions": [],
                "suggested_title": "",
            }
        model = self.settings.models.summary

        async def call():
            result = await self.runtime.llm.complete(
                model, SUMMARY_SYSTEM, prompt, schema=SUMMARY_SCHEMA, timeout=180
            )
            if not result.data:
                raise LlmError("résumé vide")
            return result.data, result

        return dict(await self.runtime.call_llm("summary", model, call))

    async def _write(self) -> dict:
        summary_data = self._step_data("summary")
        state = self.runtime.state
        lines, source_lang = self._transcript_lines()
        title = state.title or summary_data.get("suggested_title") or "Conférence"
        created = datetime.datetime.fromtimestamp(self.session.meta.created_at)
        audio = [
            str(self.session.directory / name) for name in self.session.meta.audio_files
        ]
        data = FinalNoteData(
            title=title,
            speaker=state.speaker,
            date=created.date(),
            source_lang=source_lang,
            duration_seconds=self.runtime.now(),
            audio_path=audio[0] if audio else "",
            summary=Summary(
                overview=summary_data.get("overview", ""),
                key_points=list(summary_data.get("key_points", [])),
                open_questions=list(summary_data.get("open_questions", [])),
            ),
            topics=state.topics,
            positions={k: tuple(v) for k, v in state.positions.items()},
            notes=self._note_items(),
            transcript=lines,
        )
        note_path = write_conference(data, self.vault_root)
        return {"output_path": str(note_path)}

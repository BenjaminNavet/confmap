import asyncio
import contextlib

import pytest
from conftest import FakeDetector, FakeTranscriber, fast_settings, png_bytes, wait_until

from confmap import runtime as runtime_module
from confmap.audio import FileSource
from confmap.events import (
    LlmUsageEvent,
    MapUpdateEvent,
    SegmentEvent,
    SlideEvent,
    StatusEvent,
    TranslationEvent,
)
from confmap.llm import NetworkUnavailable
from confmap.runtime import SessionRuntime


def events_of(runtime, event_type):
    return [e for e in runtime.session.events if isinstance(e, event_type)]


@contextlib.asynccontextmanager
async def running(runtime):
    try:
        yield runtime
    finally:
        await runtime.shutdown()


async def test_full_pipeline(make_runtime, fake_llm, speech_wav):
    runtime = make_runtime()
    async with running(runtime):
        runtime.set_context("Ma conf", "Ada")
        runtime.start_recording(FileSource(speech_wav, speed=0))
        await asyncio.wait_for(runtime._audio_done.wait(), 10)
        await runtime.stop_recording()
        await runtime.drain(timeout=10)

        segments = events_of(runtime, SegmentEvent)
        assert len(segments) == 4
        translations = {
            t.segment_id: t.text_fr for t in events_of(runtime, TranslationEvent)
        }
        assert set(translations) == {s.id for s in segments}
        for segment in segments:
            if segment.lang == "fr":
                assert translations[segment.id] == segment.text  # copié sans appel
            else:
                assert translations[segment.id] == f"FR {segment.text}"
        foreign = [s for s in segments if s.lang != "fr"]
        translate_prompts = "\n".join(fake_llm.prompts("translate"))
        assert all(s.text in translate_prompts for s in foreign)
        sent = [line for line in translate_prompts.splitlines() if line.startswith("[")]
        assert sent and all(
            ") " in line and " (en) " in line for line in sent
        )  # aucun (fr)
        assert "Ma conf" in translate_prompts

        updates = events_of(runtime, MapUpdateEvent)
        assert updates
        assert runtime.state.topics
        assert not runtime.state.pending_map_content()

        usages = events_of(runtime, LlmUsageEvent)
        assert usages and all(u.ok for u in usages)
        assert len(usages) == len(fake_llm.calls)
        assert runtime.state.cost_usd == pytest.approx(0.01 * len(fake_llm.calls))
        assert runtime.state.cost_usd == pytest.approx(sum(u.cost_usd for u in usages))
        assert not runtime.recording
        assert (runtime.session.directory / "enregistrement.wav").exists()


async def test_note_triggers_map_update(make_runtime, fake_llm):
    runtime = make_runtime()
    async with running(runtime):
        runtime.add_note("  Penser à Bayes  ")
        await wait_until(lambda: events_of(runtime, MapUpdateEvent))
        assert any("[NOTE] Penser à Bayes" in p for p in fake_llm.prompts("map"))
        assert runtime.state.notes[0].text == "Penser à Bayes"


async def test_photo_flow(make_runtime, fake_llm):
    runtime = make_runtime()
    async with running(runtime):
        slide = runtime.add_photo(png_bytes())
        photos = list((runtime.session.directory / "photos").iterdir())
        assert len(photos) == 1
        assert runtime.state.slides[slide.photo_id].status == "pending"

        await wait_until(lambda: events_of(runtime, MapUpdateEvent))
        statuses = [
            e.status for e in events_of(runtime, SlideEvent) if e.id == slide.id
        ]
        assert statuses == ["pending", "done"]
        assert "Titre slide" in runtime.state.slides[slide.photo_id].text_fr
        assert not list((runtime.session.directory / "photos").iterdir())
        assert fake_llm.calls[0]["kind"] == "vision"
        assert fake_llm.calls[0]["images"]
        assert any("[SLIDE]" in p for p in fake_llm.prompts("map"))


async def test_network_failure_then_recovery(make_runtime, fake_llm, monkeypatch):
    real_sleep = asyncio.sleep

    async def fast_sleep(delay, *args):
        await real_sleep(min(delay, 0.01))

    monkeypatch.setattr(runtime_module.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(runtime_module, "RETRY_MAX_SECONDS", 0.02)
    fake_llm.failures["translate"] = [
        NetworkUnavailable("ENOTFOUND"),
        NetworkUnavailable("ENOTFOUND"),
    ]
    runtime = make_runtime()
    async with running(runtime):
        segment = runtime.emit(
            SegmentEvent(ts=0, t0=0, t1=2, lang="en", text="Hello there")
        )
        runtime.start_workers()
        runtime._translate_wakeup.set()
        await wait_until(lambda: segment.id in runtime.state.translations)

        assert runtime.state.translations[segment.id] == "FR Hello there"
        states = [
            e.state for e in events_of(runtime, StatusEvent) if e.component == "network"
        ]
        assert states[0] == "down"
        assert states[-1] == "ok"
        assert len([c for c in fake_llm.calls if c["kind"] == "translate"]) == 3
        # seul l'appel réussi est facturé
        assert len(events_of(runtime, LlmUsageEvent)) == 1


async def test_llm_error_twice_keeps_original(make_runtime, fake_llm):
    from confmap.llm import LlmError

    fake_llm.failures["translate"] = [LlmError("a"), LlmError("b")]
    runtime = make_runtime()
    async with running(runtime):
        segment = runtime.emit(SegmentEvent(ts=0, t0=0, t1=2, lang="de", text="Hallo"))
        runtime.start_workers()
        runtime._translate_wakeup.set()
        await wait_until(lambda: segment.id in runtime.state.translations)
        assert runtime.state.translations[segment.id] == "[de] Hallo"
        failed = [u for u in events_of(runtime, LlmUsageEvent) if not u.ok]
        assert len(failed) == 2


async def test_replay_rebuilds_state(make_runtime, store, fake_llm, speech_wav):
    runtime = make_runtime()
    async with running(runtime):
        runtime.set_context("Replay", "Bob")
        runtime.add_note("une note")
        runtime.start_recording(FileSource(speech_wav, speed=0))
        await asyncio.wait_for(runtime._audio_done.wait(), 10)
        await runtime.stop_recording()
        await runtime.drain(timeout=10)
        runtime.set_positions({"a": (1.0, 2.0)})

    reloaded_session = type(store)(store.root).load(runtime.session.id)
    replayed = SessionRuntime(
        reloaded_session, fast_settings(), fake_llm, FakeTranscriber(), FakeDetector
    )
    original, rebuilt = runtime.state, replayed.state
    assert rebuilt.title == "Replay" and rebuilt.speaker == "Bob"
    assert rebuilt.topics == original.topics and rebuilt.topics
    assert rebuilt.translations == original.translations
    assert list(rebuilt.segments) == list(original.segments)
    assert [n.text for n in rebuilt.notes] == ["une note"]
    assert rebuilt.positions == original.positions
    assert rebuilt.covered_ids == original.covered_ids
    assert rebuilt.cost_usd == pytest.approx(original.cost_usd)
    assert rebuilt.cost_usd > 0
    # le temps cumulé de l'enregistrement précédent est repris
    assert replayed.now() == pytest.approx(16.0, abs=0.1)

import pytest

from confmap.events import (
    FinalizeStepEvent,
    MapUpdateEvent,
    SegmentEvent,
    TranslationEvent,
)
from confmap.finalizer import STEPS, Finalizer
from confmap.llm import LlmError


@pytest.fixture
async def prepared(make_runtime):
    runtime = make_runtime()
    runtime.set_context("Conf finale", "Ada")
    runtime.add_note("note perso")
    runtime._map_force.clear()
    for index, (lang, text, french) in enumerate(
        [
            ("en", "Hello world", "Bonjour le monde"),
            ("en", "Second part", "Deuxième partie"),
        ]
    ):
        segment = runtime.emit(
            SegmentEvent(
                ts=index * 3, t0=index * 3, t1=index * 3 + 2.5, lang=lang, text=text
            )
        )
        runtime.emit(TranslationEvent(segment_id=segment.id, text_fr=french))
    runtime.emit(
        MapUpdateEvent(
            topics=[
                {
                    "id": "t1",
                    "title": "Sujet",
                    "kind": "process",
                    "started_at": 0,
                    "nodes": [
                        {"id": "a", "label": "Boîte", "emoji": "", "sources": []}
                    ],
                    "edges": [],
                }
            ]
        )
    )
    return runtime


def step_events(runtime):
    return [
        (e.step, e.state)
        for e in runtime.session.events
        if isinstance(e, FinalizeStepEvent)
    ]


async def test_run_writes_note(prepared, fake_llm, tmp_path):
    vault = tmp_path / "vault"
    note_path = await Finalizer(prepared, vault).run()

    assert note_path is not None and note_path.exists()
    markdown = note_path.read_text(encoding="utf-8")
    assert "Aperçu de test." in markdown
    assert "Bonjour le monde" in markdown and "Deuxième partie" in markdown
    assert "Conf finale" in markdown
    assert list(note_path.parent.glob("*.canvas"))
    for step in STEPS:
        assert (step, "running") in step_events(prepared)
        assert (step, "done") in step_events(prepared)
    assert prepared.session.is_finalized()
    assert len(fake_llm.prompts("summary")) == 1


async def test_resume_after_summary_failure(prepared, fake_llm, tmp_path):
    vault = tmp_path / "vault"
    fake_llm.failures["summary"] = [LlmError("un"), LlmError("deux")]

    assert await Finalizer(prepared, vault).run() is None
    events = step_events(prepared)
    assert ("summary", "error") in events
    assert ("write", "running") not in events
    assert not prepared.session.is_finalized()
    assert Finalizer(prepared, vault).completed_steps() == {
        "retranscribe",
        "retranslate",
    }
    summary_calls = len(fake_llm.prompts("summary"))
    assert summary_calls == 2

    note_path = await Finalizer(prepared, vault).run()
    assert note_path is not None
    assert "Aperçu de test." in note_path.read_text(encoding="utf-8")
    after = step_events(prepared)[len(events) :]
    assert ("retranscribe", "running") not in after
    assert ("retranslate", "running") not in after
    assert ("summary", "done") in after and ("write", "done") in after
    assert len(fake_llm.prompts("summary")) == summary_calls + 1
    assert prepared.session.is_finalized()

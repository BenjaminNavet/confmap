import asyncio
import json

import pytest

from confmap.events import (
    ContextEvent,
    FinalizeStepEvent,
    LlmUsageEvent,
    MapPositionsEvent,
    MapUpdateEvent,
    NoteEvent,
    SegmentEvent,
    SlideEvent,
    StatusEvent,
    TranslationEvent,
    parse_event,
)
from confmap.session_store import SessionStore

ALL_EVENTS = [
    ContextEvent(title="T", speaker="S"),
    SegmentEvent(t0=0, t1=2, lang="en", text="hi"),
    TranslationEvent(segment_id="x", text_fr="salut"),
    NoteEvent(text="n", origin="iphone"),
    SlideEvent(photo_id="p", text_fr="txt", status="done"),
    MapUpdateEvent(topics=[{"id": "t"}], added_node_ids=["a"], source_ids=["s"]),
    MapPositionsEvent(positions={"a": (1.0, 2.0)}),
    StatusEvent(component="network", state="down", detail="d", pending=2),
    LlmUsageEvent(purpose="map", model="m", cost_usd=0.5, input_tokens=3),
    FinalizeStepEvent(step="write", state="done", output_path="/x", data={"k": 1}),
]


@pytest.mark.parametrize("event", ALL_EVENTS, ids=lambda e: e.type)
def test_event_round_trip(event):
    assert parse_event(event.model_dump_json()) == event
    assert parse_event(event.model_dump(mode="json")) == event
    assert type(parse_event(event.model_dump_json())) is type(event)


def test_parse_unknown_type_fails():
    with pytest.raises(ValueError):
        parse_event('{"type": "nope"}')


def test_create_load_list(tmp_path):
    store = SessionStore(tmp_path / "s")
    first = store.create()
    second = store.create()
    assert first.id != second.id
    assert store.list_ids() == sorted([first.id, second.id], reverse=True)
    assert len(first.meta.token) >= 16

    reopened = SessionStore(tmp_path / "s").load(first.id)
    assert reopened.meta.token == first.meta.token
    assert store.load(first.id) is first  # cache
    with pytest.raises(KeyError):
        store.load("inconnue")


def test_append_persists_and_reloads(tmp_path):
    store = SessionStore(tmp_path)
    session = store.create()
    appended = session.append(NoteEvent(text="une note"))
    assert appended.session_id == session.id
    lines = (session.directory / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == "une note"

    reloaded = SessionStore(tmp_path).load(session.id)
    assert [e.text for e in reloaded.events] == ["une note"]


async def test_append_publishes_on_bus(tmp_path):
    session = SessionStore(tmp_path).create()
    queue = session.bus.subscribe()
    session.append(NoteEvent(text="x"))
    event = await asyncio.wait_for(queue.get(), 1)
    assert event.text == "x"
    session.bus.unsubscribe(queue)
    session.append(NoteEvent(text="y"))
    assert queue.empty()


def test_truncated_last_line_is_ignored(tmp_path):
    store = SessionStore(tmp_path)
    session = store.create()
    session.append(NoteEvent(text="ok"))
    with (session.directory / "events.jsonl").open("a") as events_file:
        events_file.write('{"type": "note", "text": "tron')
    reloaded = SessionStore(tmp_path).load(session.id)
    assert [e.text for e in reloaded.events] == ["ok"]


def test_is_finalized(tmp_path):
    session = SessionStore(tmp_path).create()
    assert not session.is_finalized()
    session.append(FinalizeStepEvent(step="summary", state="done"))
    session.append(FinalizeStepEvent(step="write", state="error"))
    assert not session.is_finalized()
    session.append(FinalizeStepEvent(step="write", state="done"))
    assert session.is_finalized()
    assert SessionStore(tmp_path).load(session.id).is_finalized()


def test_default_vault_path_is_expanded():
    from confmap.config import Settings

    settings = Settings()
    assert "~" not in str(settings.paths.vault)
    assert settings.paths.vault.is_absolute()

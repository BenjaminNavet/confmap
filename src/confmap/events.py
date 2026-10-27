"""Schéma des événements du journal de session (source unique de vérité)."""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter
from ulid import ULID


def new_id() -> str:
    """Identifiant triable dans le temps."""
    return str(ULID())


class BaseEvent(BaseModel):
    """Champs communs à tous les événements."""

    id: str = Field(default_factory=new_id)
    session_id: str = ""
    ts: float = 0.0  # secondes depuis le début de la session
    wall: float = Field(default_factory=time.time)


class ContextEvent(BaseEvent):
    """Titre et orateur saisis par l'utilisateur."""

    type: Literal["context"] = "context"
    title: str = ""
    speaker: str = ""


class SegmentEvent(BaseEvent):
    """Segment transcrit par Whisper."""

    type: Literal["segment"] = "segment"
    t0: float
    t1: float
    lang: str
    text: str
    final: bool = False


class TranslationEvent(BaseEvent):
    """Traduction française d'un segment."""

    type: Literal["translation"] = "translation"
    segment_id: str
    text_fr: str


class NoteEvent(BaseEvent):
    """Note libre de l'utilisateur."""

    type: Literal["note"] = "note"
    text: str
    origin: Literal["mac", "iphone"] = "mac"


class SlideEvent(BaseEvent):
    """Analyse d'une photo (le plus souvent une slide)."""

    type: Literal["slide"] = "slide"
    photo_id: str
    text_fr: str = ""
    status: Literal["pending", "done", "error"] = "pending"


class MapUpdateEvent(BaseEvent):
    """Instantané complet de la carte après une mise à jour."""

    type: Literal["map_update"] = "map_update"
    topics: list[dict[str, Any]]
    added_node_ids: list[str] = []
    source_ids: list[str] = []
    source_text: str = ""


class MapPositionsEvent(BaseEvent):
    """Positions des nœuds telles qu'affichées (pour l'export canvas)."""

    type: Literal["map_positions"] = "map_positions"
    positions: dict[str, tuple[float, float]]


class StatusEvent(BaseEvent):
    """État d'un composant (audio, whisper, réseau, llm)."""

    type: Literal["status"] = "status"
    component: Literal["audio", "whisper", "network", "llm", "session"]
    state: str
    detail: str = ""
    pending: int = 0


class LlmUsageEvent(BaseEvent):
    """Un appel LLM et son coût équivalent API."""

    type: Literal["llm_usage"] = "llm_usage"
    purpose: str
    model: str
    cost_usd: float = 0.0
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    ok: bool = True


class FinalizeStepEvent(BaseEvent):
    """Progression de la finalisation."""

    type: Literal["finalize_step"] = "finalize_step"
    step: Literal["retranscribe", "retranslate", "summary", "write"]
    state: Literal["running", "done", "error"]
    detail: str = ""
    output_path: str = ""
    data: dict[str, Any] = {}


Event = Annotated[
    ContextEvent
    | SegmentEvent
    | TranslationEvent
    | NoteEvent
    | SlideEvent
    | MapUpdateEvent
    | MapPositionsEvent
    | StatusEvent
    | LlmUsageEvent
    | FinalizeStepEvent,
    Field(discriminator="type"),
]

EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(raw: str | bytes | dict[str, Any]) -> Event:
    """Reconstruit un événement depuis du JSON ou un dict."""
    if isinstance(raw, dict):
        return EVENT_ADAPTER.validate_python(raw)
    return EVENT_ADAPTER.validate_json(raw)

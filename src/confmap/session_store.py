"""Stockage des sessions sur disque : `sessions/<id>/events.jsonl` + métadonnées."""

from __future__ import annotations

import json
import logging
import secrets
import time
from pathlib import Path

from pydantic import BaseModel, ValidationError

from confmap.bus import EventBus
from confmap.events import Event, FinalizeStepEvent, new_id, parse_event

log = logging.getLogger(__name__)


class SessionMeta(BaseModel):
    """Métadonnées d'une session (`session.json`)."""

    id: str
    token: str
    created_at: float
    started_monotonic_offset: float = (
        0.0  # durée cumulée des enregistrements précédents
    )
    audio_files: list[str] = []


class SessionLog:
    """Journal d'une session : ajout seulement, relecture, diffusion."""

    def __init__(self, directory: Path, meta: SessionMeta) -> None:
        """Ouvre le journal d'une session existante."""
        self.directory = directory
        self.meta = meta
        self.bus = EventBus()
        self._events_path = directory / "events.jsonl"
        self._events: list[Event] = self._read_all()

    @property
    def id(self) -> str:
        """Identifiant de la session."""
        return self.meta.id

    @property
    def events(self) -> list[Event]:
        """Tous les événements, dans l'ordre d'ajout."""
        return list(self._events)

    def append(self, event: Event) -> Event:
        """Ajoute un événement sur disque puis le diffuse."""
        event.session_id = self.id
        with self._events_path.open("a", encoding="utf-8") as events_file:
            events_file.write(event.model_dump_json() + "\n")
        self._events.append(event)
        self.bus.publish(event)
        return event

    def save_meta(self) -> None:
        """Réécrit `session.json`."""
        (self.directory / "session.json").write_text(
            self.meta.model_dump_json(indent=2)
        )

    def is_finalized(self) -> bool:
        """Vrai si l'étape d'écriture dans le vault a réussi."""
        return any(
            isinstance(e, FinalizeStepEvent) and e.step == "write" and e.state == "done"
            for e in self._events
        )

    def _read_all(self) -> list[Event]:
        if not self._events_path.exists():
            return []
        events: list[Event] = []
        for line_number, line in enumerate(
            self._events_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                events.append(parse_event(line))
            except (ValidationError, json.JSONDecodeError):
                # Une ligne tronquée (crash pendant l'écriture) est ignorée.
                log.warning(
                    "ligne %d illisible dans %s", line_number, self._events_path
                )
        return events


class SessionStore:
    """Création, liste et ouverture des sessions."""

    def __init__(self, root: Path) -> None:
        """Utilise `root` comme dossier des sessions."""
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._open: dict[str, SessionLog] = {}

    def create(self) -> SessionLog:
        """Crée une nouvelle session vide."""
        session_id = new_id()
        directory = self.root / session_id
        directory.mkdir(parents=True)
        meta = SessionMeta(
            id=session_id, token=secrets.token_urlsafe(16), created_at=time.time()
        )
        session = SessionLog(directory, meta)
        session.save_meta()
        self._open[session_id] = session
        return session

    def load(self, session_id: str) -> SessionLog:
        """Ouvre une session existante (mise en cache)."""
        if session_id in self._open:
            return self._open[session_id]
        directory = self.root / session_id
        meta_path = directory / "session.json"
        if not meta_path.exists():
            raise KeyError(session_id)
        session = SessionLog(
            directory, SessionMeta.model_validate_json(meta_path.read_text())
        )
        self._open[session_id] = session
        return session

    def list_ids(self) -> list[str]:
        """Identifiants des sessions, la plus récente en premier."""
        ids = [p.name for p in self.root.iterdir() if (p / "session.json").exists()]
        return sorted(ids, reverse=True)

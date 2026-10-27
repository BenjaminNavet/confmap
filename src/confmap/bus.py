"""Diffusion asyncio des événements d'une session vers ses abonnés."""

from __future__ import annotations

import asyncio
import contextlib

from confmap.events import Event


class EventBus:
    """Pub/sub en mémoire : chaque abonné reçoit sa propre file."""

    def __init__(self) -> None:
        """Crée un bus sans abonné."""
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> asyncio.Queue[Event]:
        """Retourne une nouvelle file qui recevra les événements suivants."""
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=10_000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        """Désabonne une file."""
        self._subscribers.discard(queue)

    def publish(self, event: Event) -> None:
        """Envoie l'événement à tous les abonnés (un abonné saturé perd l'événement)."""
        for queue in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

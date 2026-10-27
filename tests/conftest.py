"""Faux objets et fixtures partagés (aucun réseau, micro, whisper ni sous-processus claude)."""

from __future__ import annotations

import asyncio
import io
import re
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile
from PIL import Image

from confmap.audio import SAMPLE_RATE, FileSource
from confmap.config import Settings
from confmap.llm import LlmResult
from confmap.runtime import SessionRuntime
from confmap.session_store import SessionStore
from confmap.transcriber import Transcription

ITEM_PATTERN = re.compile(r"^\[(?P<id>[^\]]+)\] \((?P<lang>\w+)\) (?P<text>.*)$")


class FakeLlm:
    """Client LLM factice routé selon le schéma demandé.

    Args:
        cost_usd: Coût renvoyé pour chaque appel.
    """

    def __init__(self, cost_usd: float = 0.01) -> None:
        """Crée un faux client sans panne programmée."""
        self.cost_usd = cost_usd
        self.calls: list[dict] = []
        self.failures: dict[str, list[Exception]] = {}
        self.id_mode = "plain"  # "plain", "brackets" ou "wrong"
        self.map_calls = 0

    def kind_of(self, schema: dict | None) -> str:
        """Nom de l'appel selon les clés du schéma."""
        keys = set((schema or {}).get("properties", {}))
        if "translations" in keys:
            return "translate"
        if "add" in keys:
            return "map"
        if {"title", "content"} <= keys:
            return "vision"
        if "overview" in keys:
            return "summary"
        return "other"

    def prompts(self, kind: str) -> list[str]:
        """Prompts reçus pour un type d'appel."""
        return [call["prompt"] for call in self.calls if call["kind"] == kind]

    async def complete(
        self, model, system, prompt, schema=None, images=None, timeout=60
    ) -> LlmResult:
        """Répond selon le type d'appel ou lève la panne programmée."""
        kind = self.kind_of(schema)
        self.calls.append(
            {
                "kind": kind,
                "model": model,
                "system": system,
                "prompt": prompt,
                "images": images,
            }
        )
        await asyncio.sleep(0)
        queued = self.failures.get(kind)
        if queued:
            raise queued.pop(0)
        return LlmResult(text="", data=self._data(kind, prompt), cost_usd=self.cost_usd)

    def _data(self, kind: str, prompt: str) -> dict:
        if kind == "translate":
            items = [
                m.groupdict()
                for line in prompt.splitlines()
                if (m := ITEM_PATTERN.match(line))
            ]
            translations = []
            for index, item in enumerate(items):
                if self.id_mode == "brackets":
                    item_id = f"[{item['id']}]"
                elif self.id_mode == "wrong":
                    item_id = f"x{index}"
                else:
                    item_id = item["id"]
                translations.append({"id": item_id, "fr": f"FR {item['text']}"})
            return {"translations": translations}
        if kind == "map":
            self.map_calls += 1
            number = self.map_calls
            return {
                "add": {"nodes": [], "edges": []},
                "new_topic_title": f"Sujet {number}",
                "new_topic_kind": "process",
                "new_topic": {
                    "nodes": [
                        {"id": "a", "label": f"Idée {number}A", "emoji": ""},
                        {"id": "b", "label": f"Idée {number}B", "emoji": ""},
                    ],
                    "edges": [{"from": "a", "to": "b", "label": "produit"}],
                },
            }
        if kind == "vision":
            return {"title": "Titre slide", "content": "- point clé"}
        if kind == "summary":
            return {
                "overview": "Aperçu de test.",
                "key_points": ["Point 1"],
                "open_questions": [],
                "suggested_title": "Titre suggéré",
            }
        return {}


class FakeTranscriber:
    """Transcripteur factice : textes et langues cycliques."""

    def __init__(self, languages=("en", "fr")) -> None:
        """Prépare la séquence de langues."""
        self.languages = languages
        self.count = 0

    async def transcribe(self, samples, language=None) -> Transcription:
        """Retourne un texte distinct par appel."""
        lang = self.languages[self.count % len(self.languages)]
        self.count += 1
        return Transcription(lang=lang, text=f"Segment numéro {self.count} ({lang}).")


class FakeDetector:
    """VAD factice : parole si la RMS du bloc dépasse 0,01."""

    def probability(self, block: np.ndarray) -> float:
        """1.0 pour de la parole, 0.0 sinon."""
        return 1.0 if float(np.sqrt(np.mean(np.square(block)))) > 0.01 else 0.0


def write_speech_wav(path: Path, cycles: int = 4) -> Path:
    """WAV 16 kHz mono : par cycle 3 s de sinus puis 1 s de silence."""
    time_axis = np.arange(3 * SAMPLE_RATE) / SAMPLE_RATE
    tone = (0.5 * np.sin(2 * np.pi * 220 * time_axis)).astype(np.float32)
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    signal = np.concatenate([tone, silence] * cycles)
    soundfile.write(str(path), signal, SAMPLE_RATE)
    return path


def png_bytes() -> bytes:
    """Petite image PNG."""
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format="PNG")
    return buffer.getvalue()


async def wait_until(condition, timeout: float = 5.0) -> None:
    """Attend qu'une condition devienne vraie."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition non atteinte à temps")
        await asyncio.sleep(0.01)


def fast_settings() -> Settings:
    """Réglages à cadence rapide pour les tests."""
    settings = Settings()
    settings.map.interval_seconds = 0.2
    settings.map.min_gap_seconds = 0
    return settings


@pytest.fixture
def fake_llm() -> FakeLlm:
    return FakeLlm()


@pytest.fixture
def speech_wav(tmp_path: Path) -> Path:
    return write_speech_wav(tmp_path / "speech.wav")


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions")


@pytest.fixture
def make_runtime(store, fake_llm):
    """Fabrique de runtimes (nettoyés à la fin du test)."""
    created: list[SessionRuntime] = []

    def factory(session=None, llm=None, transcriber=None) -> SessionRuntime:
        runtime = SessionRuntime(
            session or store.create(),
            fast_settings(),
            llm or fake_llm,
            transcriber or FakeTranscriber(),
            FakeDetector,
        )
        created.append(runtime)
        return runtime

    yield factory
    for runtime in created:
        for task in list(runtime._tasks):
            task.cancel()


@pytest.fixture
def file_source_factory(speech_wav):
    return lambda: FileSource(speech_wav, speed=0)

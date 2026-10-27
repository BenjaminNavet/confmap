"""Transcription locale avec mlx-whisper (un seul thread : mlx n'aime pas la concurrence)."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)

# Phrases que Whisper invente sur du silence ou de la musique.
HALLUCINATIONS = (
    "sous-titres réalisés par",
    "sous-titrage",
    "amara.org",
    "thank you for watching",
    "thanks for watching",
    "merci d'avoir regardé",
    "subscribe",
    "abonnez-vous",
    "untertitel",
    "ご視聴ありがとうございました",
)


@dataclass
class Transcription:
    """Texte reconnu dans un segment."""

    lang: str
    text: str


@dataclass
class TimedText:
    """Morceau horodaté d'une transcription complète."""

    t0: float
    t1: float
    text: str


class Transcriber(Protocol):
    """Interface d'un moteur de transcription."""

    async def transcribe(
        self, samples: np.ndarray, language: str | None = None
    ) -> Transcription:
        """Transcrit un segment court."""
        ...


def is_hallucination(text: str) -> bool:
    """Vrai pour un texte vide, une hallucination connue ou une boucle de répétitions."""
    lowered = text.strip().lower()
    if len(re.sub(r"[\W_]+", "", lowered)) < 2:
        return True
    if any(marker in lowered for marker in HALLUCINATIONS):
        return True
    words = lowered.split()
    return len(words) >= 8 and len(set(words)) <= len(words) / 4


class MlxWhisperTranscriber:
    """mlx-whisper avec stabilisation de la langue et bascule vers un modèle léger.

    Args:
        model: Dépôt Hugging Face du modèle principal.
        fallback_model: Modèle plus léger utilisé si le retard devient trop grand.
    """

    def __init__(self, model: str, fallback_model: str) -> None:
        """Prépare le thread de transcription."""
        self.model = model
        self.fallback_model = fallback_model
        self.active_model = model
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
        self._languages: Counter[str] = Counter()

    def use_fallback(self) -> bool:
        """Passe au modèle léger ; retourne False si c'est déjà le cas."""
        if self.active_model == self.fallback_model:
            return False
        self.active_model = self.fallback_model
        return True

    @property
    def dominant_language(self) -> str | None:
        """Langue majoritaire une fois 3 segments reconnus."""
        if sum(self._languages.values()) < 3:
            return None
        return self._languages.most_common(1)[0][0]

    async def warm_up(self) -> None:
        """Charge le modèle (téléchargement au premier lancement)."""
        await self.transcribe(np.zeros(16_000, dtype=np.float32), language="en")

    async def transcribe(
        self, samples: np.ndarray, language: str | None = None
    ) -> Transcription:
        """Transcrit un segment ; la langue est figée sur la langue dominante."""
        language = language or self.dominant_language
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor, self._run, samples, language, self.active_model
        )
        detected = str(result.get("language") or language or "und")
        text = str(result.get("text") or "").strip()
        if text and not is_hallucination(text):
            self._languages[detected] += 1
        return Transcription(lang=detected, text=text)

    async def transcribe_file(
        self, path: Path, model: str, language: str | None
    ) -> tuple[str, list[TimedText]]:
        """Transcription complète d'un fichier (finalisation)."""
        loop = asyncio.get_running_loop()

        def run() -> dict:
            import mlx_whisper

            return mlx_whisper.transcribe(
                str(path),
                path_or_hf_repo=model,
                language=language,
                condition_on_previous_text=False,
                verbose=None,
            )

        result = await loop.run_in_executor(self._executor, run)
        pieces = [
            TimedText(float(s["start"]), float(s["end"]), str(s["text"]).strip())
            for s in result.get("segments", [])
            if str(s.get("text", "")).strip() and not is_hallucination(str(s["text"]))
        ]
        return str(result.get("language") or language or "und"), pieces

    @staticmethod
    def _run(samples: np.ndarray, language: str | None, model: str) -> dict:
        import mlx_whisper

        return mlx_whisper.transcribe(
            samples.astype(np.float32),
            path_or_hf_repo=model,
            language=language,
            condition_on_previous_text=False,
            verbose=None,
            temperature=0.0,
            no_speech_threshold=0.6,
        )

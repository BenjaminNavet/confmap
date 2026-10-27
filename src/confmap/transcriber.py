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


GLOSSARY_MAX_TERMS = 30
_WORD = re.compile(r"[A-Za-zÀ-ÿ0-9][\w'’-]*")


def glossary_terms(text: str) -> list[str]:
    """Noms propres et sigles d'un texte fiable (slides, notes), sans les phrases.

    Whisper recopie la langue de son amorce : on ne lui passe que des termes
    (Huawei, ISWC, IKEA...), jamais de phrases traduites en français.
    Retient les mots avec un chiffre ou deux majuscules, et les mots à majuscule
    qui ne commencent pas une phrase ou une puce.
    """
    terms: list[str] = []
    for sentence in re.split(r"[.!?:;\n]+|\s[-•]\s", text):
        for index, word in enumerate(_WORD.findall(sentence)):
            capitals = sum(char.isupper() for char in word)
            proper = word[0].isupper() and index > 0
            if (
                capitals >= 2 or proper or (any(c.isdigit() for c in word) and capitals)
            ) and word not in terms:
                terms.append(word)
    return terms[:GLOSSARY_MAX_TERMS]


def build_initial_prompt(title: str, speaker: str, glossary: str = "") -> str | None:
    """Amorce Whisper avec le contexte de la conférence (None si le titre est vide).

    L'amorce ne contient que le titre, l'orateur et des termes isolés, sans libellés
    en français, pour ne pas pousser Whisper à écrire en français.

    Args:
        title: Titre de la conférence.
        speaker: Orateur.
        glossary: Texte fiable (slides, notes) dont on extrait noms propres et sigles.
    """
    title = title.strip()
    if not title:
        return None
    parts = [title]
    if speaker.strip():
        parts.append(speaker.strip())
    terms = glossary_terms(glossary)
    if terms:
        parts.append(", ".join(terms))
    return ". ".join(parts) + "."


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
        self.initial_prompt: str | None = None

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
            self._executor,
            self._run,
            samples,
            language,
            self.active_model,
            self.initial_prompt,
        )
        detected = str(result.get("language") or language or "und")
        text = str(result.get("text") or "").strip()
        if text and not is_hallucination(text):
            self._languages[detected] += 1
        return Transcription(lang=detected, text=text)

    async def transcribe_file(
        self,
        path: Path,
        model: str,
        language: str | None,
        initial_prompt: str | None = None,
    ) -> tuple[str, list[TimedText]]:
        """Transcription complète d'un fichier (finalisation)."""
        loop = asyncio.get_running_loop()

        def run() -> dict:
            import mlx_whisper

            return mlx_whisper.transcribe(
                str(path),
                path_or_hf_repo=model,
                language=language,
                initial_prompt=initial_prompt,
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
    def _run(
        samples: np.ndarray,
        language: str | None,
        model: str,
        initial_prompt: str | None = None,
    ) -> dict:
        import mlx_whisper

        return mlx_whisper.transcribe(
            samples.astype(np.float32),
            path_or_hf_repo=model,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            verbose=None,
            temperature=0.0,
            no_speech_threshold=0.6,
        )

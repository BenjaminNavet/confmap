"""Transcription locale avec Whisper : mlx-whisper sur Mac Apple Silicon, faster-whisper ailleurs."""

from __future__ import annotations

import asyncio
import logging
import platform
import re
import sys
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


class WhisperTranscriber:
    """Whisper local avec stabilisation de la langue et bascule vers un modèle léger.

    Un seul thread de calcul : les moteurs n'aiment pas la concurrence. Les
    sous-classes fournissent `_run` (segment) et `_run_file` (fichier entier),
    qui retournent un dict au format de whisper (`language`, `text`, `segments`).

    Args:
        model: Modèle principal.
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
            samples.astype(np.float32),
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
        result = await loop.run_in_executor(
            self._executor, self._run_file, path, model, language, initial_prompt
        )
        pieces = [
            TimedText(float(s["start"]), float(s["end"]), str(s["text"]).strip())
            for s in result.get("segments", [])
            if str(s.get("text", "")).strip() and not is_hallucination(str(s["text"]))
        ]
        return str(result.get("language") or language or "und"), pieces

    def _run(
        self,
        samples: np.ndarray,
        language: str | None,
        model: str,
        initial_prompt: str | None,
    ) -> dict:
        raise NotImplementedError

    def _run_file(
        self,
        path: Path,
        model: str,
        language: str | None,
        initial_prompt: str | None,
    ) -> dict:
        raise NotImplementedError


class MlxWhisperTranscriber(WhisperTranscriber):
    """Moteur mlx-whisper (Mac Apple Silicon, GPU Metal)."""

    def _run(self, samples, language, model, initial_prompt):  # noqa: D102
        import mlx_whisper

        return mlx_whisper.transcribe(
            samples,
            path_or_hf_repo=model,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            verbose=None,
            temperature=0.0,
            no_speech_threshold=0.6,
        )

    def _run_file(self, path, model, language, initial_prompt):  # noqa: D102
        import mlx_whisper

        return mlx_whisper.transcribe(
            str(path),
            path_or_hf_repo=model,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            verbose=None,
        )


class FasterWhisperTranscriber(WhisperTranscriber):
    """Moteur faster-whisper (Windows, Linux, Mac Intel ; GPU CUDA si disponible).

    Les modèles se nomment `large-v3-turbo`, `small`, `large-v3`… (téléchargés
    depuis Hugging Face au premier usage) et restent chargés en mémoire.
    """

    def __init__(self, model: str, fallback_model: str) -> None:
        """Prépare le thread et le cache des modèles chargés."""
        super().__init__(model, fallback_model)
        self._models: dict[str, object] = {}

    def _load(self, name: str):
        if name not in self._models:
            from faster_whisper import WhisperModel

            # "auto" : CUDA si présent, sinon CPU, avec le type de calcul le plus rapide (int8 sur CPU).
            self._models[name] = WhisperModel(name, device="auto", compute_type="auto")
        return self._models[name]

    def _transcribe(self, audio, model, language, initial_prompt, **options) -> dict:
        segments, info = self._load(model).transcribe(
            audio,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            **options,
        )
        pieces = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
        return {
            "language": info.language,
            "text": "".join(piece["text"] for piece in pieces),
            "segments": pieces,
        }

    def _run(self, samples, language, model, initial_prompt):  # noqa: D102
        return self._transcribe(
            samples,
            model,
            language,
            initial_prompt,
            temperature=0.0,
            no_speech_threshold=0.6,
        )

    def _run_file(self, path, model, language, initial_prompt):  # noqa: D102
        from confmap.audio import load_audio_16k

        return self._transcribe(load_audio_16k(path), model, language, initial_prompt)


def mlx_available() -> bool:
    """Vrai sur un Mac Apple Silicon (seule plateforme de mlx)."""
    return sys.platform == "darwin" and platform.machine() == "arm64"


def create_transcriber(model: str, fallback_model: str) -> WhisperTranscriber:
    """Choisit le moteur adapté à la machine."""
    if mlx_available():
        return MlxWhisperTranscriber(model, fallback_model)
    return FasterWhisperTranscriber(model, fallback_model)

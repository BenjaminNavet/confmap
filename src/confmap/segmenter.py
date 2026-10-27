"""Découpage de la parole en segments de 2 à 8 s avec le VAD Silero (ONNX)."""

from __future__ import annotations

import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from confmap.audio import BLOCK_SIZE, SAMPLE_RATE

SILERO_URL = "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx"
SILERO_PATH = Path("~/.cache/confmap/silero_vad.onnx").expanduser()


class SpeechDetector(Protocol):
    """Donne une probabilité de parole pour un bloc de 512 échantillons."""

    def probability(self, block: np.ndarray) -> float:
        """Probabilité de parole entre 0 et 1."""
        ...


class SileroDetector:
    """VAD Silero v5 exécuté avec onnxruntime (sans torch)."""

    CONTEXT = 64  # échantillons du bloc précédent attendus par le modèle

    def __init__(self, model_path: Path = SILERO_PATH) -> None:
        """Charge le modèle (téléchargé au premier usage)."""
        import onnxruntime

        if not model_path.exists():
            model_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(SILERO_URL, model_path)  # noqa: S310
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            str(model_path), sess_options=options
        )
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(self.CONTEXT, dtype=np.float32)
        self._sample_rate = np.array(SAMPLE_RATE, dtype=np.int64)

    def probability(self, block: np.ndarray) -> float:
        """Probabilité de parole du bloc."""
        model_input = np.concatenate([self._context, block.astype(np.float32)])[None, :]
        output, self._state = self._session.run(
            None, {"input": model_input, "state": self._state, "sr": self._sample_rate}
        )
        self._context = block[-self.CONTEXT :].astype(np.float32)
        return float(output[0][0])


@dataclass
class SpeechSegment:
    """Morceau de parole prêt à transcrire."""

    t0: float  # secondes depuis le début de l'enregistrement courant
    t1: float
    samples: np.ndarray


class Segmenter:
    """Accumule les blocs et émet un segment à chaque pause (ou à la durée max).

    Args:
        detector: VAD.
        threshold: Probabilité au-dessus de laquelle un bloc est de la parole.
        min_seconds: Durée minimale avant de couper sur une pause.
        max_seconds: Coupure forcée.
        pause_seconds: Silence qui termine un segment.
        padding_seconds: Audio gardé avant le début détecté.
    """

    def __init__(
        self,
        detector: SpeechDetector,
        threshold: float = 0.5,
        min_seconds: float = 2.0,
        max_seconds: float = 8.0,
        pause_seconds: float = 0.5,
        padding_seconds: float = 0.2,
    ) -> None:
        """Crée un segmenteur vide."""
        self.detector = detector
        self.threshold = threshold
        self.min_samples = int(min_seconds * SAMPLE_RATE)
        self.max_samples = int(max_seconds * SAMPLE_RATE)
        self.pause_blocks = max(1, int(pause_seconds * SAMPLE_RATE / BLOCK_SIZE))
        self._padding: deque[np.ndarray] = deque(
            maxlen=max(1, int(padding_seconds * SAMPLE_RATE / BLOCK_SIZE))
        )
        self._current: list[np.ndarray] = []
        self._current_start = 0
        self._speech_blocks = 0
        self._silent_run = 0
        self._position = 0  # échantillons reçus

    def feed(self, block: np.ndarray) -> SpeechSegment | None:
        """Ajoute un bloc ; retourne un segment s'il vient de se terminer."""
        is_speech = self.detector.probability(block) >= self.threshold
        block_start = self._position
        self._position += len(block)
        if not self._current:
            if is_speech:
                padding = list(self._padding)
                self._current = [*padding, block]
                self._current_start = block_start - sum(len(b) for b in padding)
                self._speech_blocks = 1
                self._silent_run = 0
            else:
                self._padding.append(block)
            return None
        self._current.append(block)
        if is_speech:
            self._speech_blocks += 1
            self._silent_run = 0
        else:
            self._silent_run += 1
        length = sum(len(b) for b in self._current)
        if (
            self._silent_run >= self.pause_blocks and length >= self.min_samples
        ) or length >= self.max_samples:
            return self._emit()
        if (
            self._silent_run >= self.pause_blocks * 4
        ):  # longue pause sur un segment court
            return self._emit()
        return None

    def flush(self) -> SpeechSegment | None:
        """Termine le segment en cours (fin d'enregistrement)."""
        return self._emit() if self._current else None

    def _emit(self) -> SpeechSegment | None:
        samples = np.concatenate(self._current)
        start = self._current_start
        speech_seconds = self._speech_blocks * BLOCK_SIZE / SAMPLE_RATE
        self._current = []
        self._padding.clear()
        self._speech_blocks = 0
        self._silent_run = 0
        if speech_seconds < 0.4:
            return None
        return SpeechSegment(
            t0=start / SAMPLE_RATE,
            t1=(start + len(samples)) / SAMPLE_RATE,
            samples=samples,
        )

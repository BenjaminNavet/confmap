"""Sources audio (micro ou fichier) et enregistrement WAV continu."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
BLOCK_SIZE = 512  # 32 ms : taille de trame attendue par Silero


class AudioSource(Protocol):
    """Flux de blocs float32 mono 16 kHz."""

    def blocks(self) -> AsyncIterator[np.ndarray]:
        """Itère sur les blocs audio jusqu'à `stop()`."""
        ...

    def stop(self) -> None:
        """Arrête la source."""
        ...


class MicrophoneSource:
    """Micro par défaut du Mac via `sounddevice`."""

    def __init__(self, device: int | str | None = None) -> None:
        """Prépare la capture (démarrée à la première itération)."""
        self.device = device
        self._stopped = asyncio.Event()

    async def blocks(self) -> AsyncIterator[np.ndarray]:
        """Itère sur les blocs du micro."""
        import sounddevice  # import tardif : absent du chemin de test

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

        def callback(
            indata: np.ndarray, _frames: int, _time: object, status: object
        ) -> None:
            if status:
                log.debug("statut micro : %s", status)
            loop.call_soon_threadsafe(queue.put_nowait, indata[:, 0].copy())

        stream, input_rate = open_input_stream(sounddevice, self.device, callback)
        rechunker = Rechunker(input_rate)
        with stream:
            while not self._stopped.is_set():
                getter = asyncio.ensure_future(queue.get())
                stopper = asyncio.ensure_future(self._stopped.wait())
                done, _ = await asyncio.wait(
                    {getter, stopper}, return_when=asyncio.FIRST_COMPLETED
                )
                if getter in done:
                    stopper.cancel()
                    for block in rechunker.push(getter.result()):
                        yield block
                else:
                    getter.cancel()

    def stop(self) -> None:
        """Arrête la capture."""
        self._stopped.set()


def open_input_stream(sounddevice_module, device, callback):
    """Ouvre le micro en 16 kHz, ou à son taux natif si le pilote refuse."""
    try:
        stream = sounddevice_module.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            device=device,
            callback=callback,
        )
        return stream, SAMPLE_RATE
    except sounddevice_module.PortAudioError:
        native_rate = int(
            sounddevice_module.query_devices(device, kind="input")["default_samplerate"]
        )
        log.info("micro ouvert à %d Hz, rééchantillonné en 16 kHz", native_rate)
        stream = sounddevice_module.InputStream(
            samplerate=native_rate,
            channels=1,
            dtype="float32",
            blocksize=int(native_rate * BLOCK_SIZE / SAMPLE_RATE),
            device=device,
            callback=callback,
        )
        return stream, native_rate


class Rechunker:
    """Rééchantillonne en 16 kHz (interpolation linéaire) et redécoupe en blocs de 512."""

    def __init__(self, input_rate: int) -> None:
        """Prépare la conversion depuis `input_rate`."""
        self.input_rate = input_rate
        self._pending = np.zeros(0, dtype=np.float32)
        self._phase = (
            0.0  # position (en échantillons d'entrée) du prochain échantillon de sortie
        )
        self._previous = np.zeros(0, dtype=np.float32)

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        """Ajoute des échantillons ; retourne les blocs complets disponibles."""
        if self.input_rate != SAMPLE_RATE:
            samples = self._resample(samples.astype(np.float32))
        self._pending = np.concatenate([self._pending, samples.astype(np.float32)])
        blocks = []
        while len(self._pending) >= BLOCK_SIZE:
            blocks.append(self._pending[:BLOCK_SIZE])
            self._pending = self._pending[BLOCK_SIZE:]
        return blocks

    def _resample(self, samples: np.ndarray) -> np.ndarray:
        source = np.concatenate([self._previous, samples])
        step = self.input_rate / SAMPLE_RATE
        positions = np.arange(self._phase, len(source) - 1, step)
        output = np.interp(positions, np.arange(len(source)), source).astype(np.float32)
        next_position = self._phase + len(positions) * step
        keep_from = int(np.floor(next_position))
        self._previous = source[keep_from:]
        self._phase = next_position - keep_from
        return output


class FileSource:
    """Rejoue un fichier audio comme un micro (tests et démonstrations).

    Args:
        path: Fichier lisible par `soundfile` (WAV, FLAC...) ou par ffmpeg.
        speed: 1.0 = temps réel ; 0 = aussi vite que possible.
    """

    def __init__(self, path: Path, speed: float = 1.0) -> None:
        """Charge et rééchantillonne le fichier en 16 kHz mono."""
        self.path = path
        self.speed = speed
        self._stopped = False

    async def blocks(self) -> AsyncIterator[np.ndarray]:
        """Itère sur les blocs du fichier au rythme demandé."""
        samples = await asyncio.to_thread(load_audio_16k, self.path)
        block_duration = BLOCK_SIZE / SAMPLE_RATE
        loop = asyncio.get_running_loop()
        start = loop.time()
        for index, offset in enumerate(range(0, len(samples), BLOCK_SIZE)):
            if self._stopped:
                return
            block = samples[offset : offset + BLOCK_SIZE]
            if len(block) < BLOCK_SIZE:
                block = np.pad(block, (0, BLOCK_SIZE - len(block)))
            if self.speed > 0:
                target = start + index * block_duration / self.speed
                delay = target - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
            elif index % 64 == 0:
                await asyncio.sleep(0)
            yield block

    def stop(self) -> None:
        """Arrête la lecture."""
        self._stopped = True


def load_audio_16k(path: Path) -> np.ndarray:
    """Charge un fichier audio en float32 mono 16 kHz (ffmpeg si nécessaire)."""
    try:
        data, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
        mono = data.mean(axis=1)
        if rate == SAMPLE_RATE:
            return mono.astype(np.float32)
    except (RuntimeError, soundfile.LibsndfileError):
        pass
    import subprocess

    completed = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-f",
            "f32le",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return np.frombuffer(completed.stdout, dtype=np.float32).copy()


class WavRecorder:
    """Écrit les blocs reçus dans un WAV 16 kHz mono, avec flush régulier."""

    def __init__(self, path: Path) -> None:
        """Ouvre le fichier en écriture."""
        self.path = path
        self._file = soundfile.SoundFile(
            str(path), mode="w", samplerate=SAMPLE_RATE, channels=1, subtype="PCM_16"
        )
        self._blocks_since_flush = 0
        self.samples_written = 0

    def write(self, block: np.ndarray) -> None:
        """Ajoute un bloc."""
        self._file.write(block)
        self.samples_written += len(block)
        self._blocks_since_flush += 1
        if self._blocks_since_flush >= 150:  # ~5 s
            self._file.flush()
            self._blocks_since_flush = 0

    def close(self) -> None:
        """Ferme le fichier."""
        with contextlib.suppress(Exception):
            self._file.close()

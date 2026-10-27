import numpy as np
import pytest
import soundfile
from conftest import FakeDetector

from confmap.audio import BLOCK_SIZE, SAMPLE_RATE
from confmap.segmenter import Segmenter
from confmap.transcriber import is_hallucination

TONE = (0.5 * np.sin(2 * np.pi * 220 * np.arange(BLOCK_SIZE) / SAMPLE_RATE)).astype(
    np.float32
)
SILENCE = np.zeros(BLOCK_SIZE, dtype=np.float32)


def seconds_to_blocks(seconds):
    return int(seconds * SAMPLE_RATE / BLOCK_SIZE)


def run(blocks):
    segmenter = Segmenter(FakeDetector())
    segments = [s for s in map(segmenter.feed, blocks) if s is not None]
    trailing = segmenter.flush()
    return segments, trailing


def test_cuts_on_pauses(speech_wav):
    signal, _ = soundfile.read(str(speech_wav), dtype="float32")
    blocks = [
        signal[i : i + BLOCK_SIZE]
        for i in range(0, len(signal) - BLOCK_SIZE, BLOCK_SIZE)
    ]
    segments, trailing = run(blocks)
    assert trailing is None
    assert len(segments) == 4
    for index, segment in enumerate(segments):
        assert 2 <= segment.t1 - segment.t0 <= 8
        assert segment.t0 == pytest.approx(4 * index, abs=0.3)
        assert segment.t1 == pytest.approx(4 * index + 3.5, abs=0.3)
        assert len(segment.samples) == round((segment.t1 - segment.t0) * SAMPLE_RATE)


def test_forced_cut_at_eight_seconds():
    blocks = [TONE] * seconds_to_blocks(20)
    segments, trailing = run(blocks)
    assert [round(s.t1 - s.t0, 2) for s in segments] == [8.0, 8.0]
    assert segments[1].t0 == pytest.approx(8.0, abs=0.05)
    assert trailing is not None
    assert trailing.t0 == pytest.approx(16.0, abs=0.05)
    assert trailing.t1 == pytest.approx(20.0, abs=0.05)


def test_short_blips_are_dropped():
    blip = [TONE] * seconds_to_blocks(0.2)
    blocks = [SILENCE] * 20 + blip + [SILENCE] * 80
    segments, trailing = run(blocks)
    assert segments == []
    assert trailing is None


def test_flush_emits_trailing_segment():
    blocks = [SILENCE] * 10 + [TONE] * seconds_to_blocks(1.5)
    segments, trailing = run(blocks)
    assert segments == []
    assert trailing is not None
    assert trailing.t0 == pytest.approx(10 * BLOCK_SIZE / SAMPLE_RATE - 0.19, abs=0.05)
    assert trailing.t1 == pytest.approx(
        (10 + seconds_to_blocks(1.5)) * BLOCK_SIZE / SAMPLE_RATE, abs=0.05
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", True),
        ("   ", True),
        (" . ", True),
        ("Sous-titres réalisés par la communauté d'Amara.org", True),
        ("Thanks for watching!", True),
        ("merci merci merci merci merci merci merci merci merci", True),
        ("Aujourd'hui nous présentons une méthode de transcription robuste.", False),
        ("Hello everyone, welcome to the talk.", False),
    ],
)
def test_is_hallucination(text, expected):
    assert is_hallucination(text) is expected

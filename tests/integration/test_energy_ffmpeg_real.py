"""IT-002: the energy meter on real ffmpeg output, over two generated WAVs."""
import shutil
import subprocess
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.energy_ffmpeg import FfmpegEnergyMeter
from teams_recorder.domain import Segment, Transcript, label_segments

pytestmark = pytest.mark.slow
ffmpeg_missing = shutil.which("ffmpeg") is None


def _wav(path: Path, parts: list[str], channels: int) -> None:
    """3 s at 16 kHz made of `parts` (lavfi sources of 1.5 s each, joined)."""
    inputs = [arg for part in parts for arg in ("-f", "lavfi", "-i", part)]
    joined = "".join(f"[{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *inputs, "-filter_complex", joined,
                    "-map", "[out]", "-ac", str(channels), "-ar", "16000", "-t", "3", str(path)], check=True)


TONE = "sine=frequency=440:sample_rate=16000:duration=1.5"
SILENCE = "anullsrc=r=16000:cl=mono:d=1.5"


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_it002_levels_follow_the_tones_and_the_user_line_is_the_microphone_one(tmp_path: Path):
    tap, mic = tmp_path / "tap.wav", tmp_path / "mic.wav"
    _wav(tap, [TONE, SILENCE], channels=2)    # Teams: a tone over 0-1.5 s, digital silence after
    _wav(mic, [SILENCE, TONE], channels=1)    # microphone: silence, then a tone over 1.5-3 s
    meter = FfmpegEnergyMeter()

    tap_levels, mic_levels = meter.measure(tap), meter.measure(mic)

    assert tap_levels.step == mic_levels.step == 0.1
    assert len(tap_levels.levels) == len(mic_levels.levels) == 30
    # Inside each tone: well above -30 dBFS (the measured run reads about -21). Outside it: at or below -80, with the
    # window next to each edge reading a finite level rather than the floor.
    assert all(level > -30 for level in tap_levels.levels[0:14]) and all(level > -30 for level in mic_levels.levels[16:30])
    assert all(level <= -80 for level in tap_levels.levels[16:30]) and all(level <= -80 for level in mic_levels.levels[0:14])

    transcript = Transcript([Segment(0.0, 1.4, "fala remota"), Segment(1.6, 3.0, "fala do usuario")])
    labelled = label_segments(transcript, None, mic_levels, tap_levels, "Felipe")
    assert [s.speaker for s in labelled.segments] == [None, "Felipe"]

"""EnergyMeter via ffmpeg: the RMS level of a track per 100 ms window (the user's own lines are found from it, ADR-002)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from teams_recorder.adapters.outbound.process_control import NO_WINDOW
from teams_recorder.constants import Bin, Parse, Proc, Speakers
from teams_recorder.domain import SILENCE_DB, CaptureError, EnergyTimeline
from teams_recorder.messages import Err

_TIME = re.compile(Parse.ENERGY_TIME)
_LEVEL = re.compile(Parse.ENERGY_LEVEL)


def parse_levels(output: str) -> EnergyTimeline:
    """Reads ametadata's stdout: a `pts_time:` line then a `RMS_level=` line per window. `-inf` (digital silence) becomes
    SILENCE_DB; windows are ordered by their time. Output without a level gives an empty timeline."""
    windows: list[tuple[float, float]] = []
    at: float | None = None
    for line in output.splitlines():
        time_match = _TIME.search(line)
        if time_match:
            at = float(time_match.group(1))
            continue
        level_match = _LEVEL.search(line)
        if level_match and at is not None:
            raw = level_match.group(1)
            windows.append((at, SILENCE_DB if raw.endswith("inf") else max(float(raw), SILENCE_DB)))
            at = None
    return EnergyTimeline(step=Speakers.ENERGY_STEP, levels=tuple(level for _, level in sorted(windows, key=lambda w: w[0])))


class FfmpegEnergyMeter:
    def __init__(self, ffmpeg: str = Bin.FFMPEG, timeout: float = Proc.FFMPEG_TIMEOUT) -> None:
        self.ffmpeg = ffmpeg
        self.timeout = timeout

    def command(self, track: Path) -> list[str]:
        return [self.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(track),
                "-af", Speakers.ENERGY_FILTER, "-f", "null", "-"]

    def measure(self, track: Path) -> EnergyTimeline:
        try:
            result = subprocess.run(self.command(track), capture_output=True, text=True, timeout=self.timeout, check=False, creationflags=NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CaptureError(Err.ENERGY_FAILED.format(track=track.name, error=exc)) from exc
        if result.returncode != 0:
            raise CaptureError(Err.ENERGY_FAILED_CODE.format(track=track.name, code=result.returncode, tail=result.stderr.strip()[-500:]))
        timeline = parse_levels(result.stdout)
        if not timeline.levels:
            raise CaptureError(Err.ENERGY_NO_LEVELS.format(track=track.name))
        return timeline

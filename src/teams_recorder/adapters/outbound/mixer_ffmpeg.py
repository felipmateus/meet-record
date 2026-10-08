"""AudioMixer via ffmpeg: sums the tracks, normalizes loudness and encodes mono AAC."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from teams_recorder.adapters.outbound.process_control import NO_WINDOW
from teams_recorder.constants import Audio, Bin, Files, Parse, Proc
from teams_recorder.domain import CaptureError
from teams_recorder.messages import Err, Log

log = logging.getLogger(__name__)

# Module-level aliases kept for callers and tests.
MIN_TRACK_BYTES = Audio.MIN_TRACK_BYTES
ANOMALY_RATIO = Audio.ANOMALY_RATIO
DEBUG_DIR = Files.DEBUG_DIR


@dataclass(frozen=True)
class TrackInfo:
    """What ffmpeg's volumedetect reports about one track; None when a value could not be read."""

    duration: float | None = None
    mean_db: float | None = None
    max_db: float | None = None


def probe(path: Path, ffmpeg: str = Bin.FFMPEG) -> TrackInfo:
    """Duration (s) and mean/peak volume (dB) of a track, via ffmpeg volumedetect."""
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, timeout=Proc.FFMPEG_TIMEOUT, check=False, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return TrackInfo()
    out = r.stderr
    duration = mean_db = max_db = None
    m = re.search(Parse.FFMPEG_DURATION, out)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(Parse.FFMPEG_MEAN_VOLUME, out)
    if m:
        mean_db = float(m.group(1))
    m = re.search(Parse.FFMPEG_MAX_VOLUME, out)
    if m:
        max_db = float(m.group(1))
    return TrackInfo(duration=duration, mean_db=mean_db, max_db=max_db)


class FfmpegMixer:
    def __init__(
        self,
        ffmpeg: str = Bin.FFMPEG,
        bitrate_kbps: int = Audio.DEFAULT_BITRATE_KBPS,
        sample_rate: int = Audio.SAMPLE_RATE,
        timeout: float = Proc.FFMPEG_TIMEOUT,
        denoise: bool = True,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.bitrate_kbps = bitrate_kbps
        self.sample_rate = sample_rate  # loudnorm resamples internally; we pin the output rate
        self.timeout = timeout
        self.denoise = denoise

    # Per track: removes hum/low-frequency noise (fan, desk) and reduces background noise
    # by continuously estimating the noise floor. After summing: normalizes loudness and
    # limits peaks to -1 dBTP, because summing two tracks (user's voice close to the
    # microphone + Teams) was clipping the final file (measured peak: +1.5 dB).
    TRACK_FILTER = Audio.TRACK_FILTER
    MASTER_FILTER = Audio.MASTER_FILTER

    @staticmethod
    def usable_tracks(tracks: list[Path]) -> list[Path]:
        return [t for t in tracks if t.exists() and t.stat().st_size >= MIN_TRACK_BYTES]

    def command(self, tracks: list[Path], out: Path) -> list[str]:
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        for t in tracks:
            cmd += ["-i", str(t)]
        pre = f"{self.TRACK_FILTER}," if self.denoise else ""
        if len(tracks) > 1:
            chains = "".join(f"[{i}:a]{pre}anull[t{i}];" for i in range(len(tracks)))
            inputs = "".join(f"[t{i}]" for i in range(len(tracks)))
            filt = f"{chains}{inputs}amix=inputs={len(tracks)}:duration=longest:dropout_transition=0:normalize=0,{self.MASTER_FILTER}[a]"
            cmd += ["-filter_complex", filt, "-map", "[a]"]
        else:
            cmd += ["-af", f"{pre}{self.MASTER_FILTER}"]
        cmd += ["-ac", "1", "-ar", str(self.sample_rate), "-c:a", "aac", "-b:a", f"{self.bitrate_kbps}k", str(out)]
        return cmd

    def _preserve_if_anomalous(self, tracks: list[Path], durations: dict[Path, float], meeting_dir: Path) -> None:
        """If one track is much shorter than the other (a recorder died), keep copies for diagnosis."""
        if len(durations) < 2:
            anomalous = len(tracks) >= 2  # a whole track missing/empty is also an anomaly
        else:
            longest = max(durations.values())
            anomalous = longest > 0 and min(durations.values()) / longest < ANOMALY_RATIO
        if not anomalous:
            return
        debug = meeting_dir / DEBUG_DIR
        debug.mkdir(exist_ok=True)
        for t in tracks:
            if t.exists():
                shutil.copy2(t, debug / t.name)
        log.warning(Log.TRACK_ANOMALY, ", ".join(f"{t.name}={durations.get(t, 0):.1f}s" for t in tracks), debug)

    def mix(self, tracks: list[Path], out: Path) -> Path:
        usable = self.usable_tracks(tracks)
        durations: dict[Path, float] = {}
        for t in tracks:
            size = t.stat().st_size if t.exists() else 0
            if t in usable:
                info = probe(t, self.ffmpeg)
                if info.duration is not None:
                    durations[t] = info.duration
                log.info(Log.TRACK_INFO, t.name, size / 1e6, info.duration or 0.0, info.mean_db, info.max_db)
            else:
                log.info(Log.TRACK_DISCARDED, t.name, size / 1e6)
        self._preserve_if_anomalous(tracks, durations, out.parent)
        if not usable:
            raise CaptureError(Err.NO_USABLE_TRACK.format(tracks=", ".join(str(t) for t in tracks)))
        timeout = self.timeout_for(max(durations.values(), default=0.0))
        log.info(Log.MIX_TIMEOUT, round(max(durations.values(), default=0.0)), timeout)
        # Write to a temporary name and rename on success: a killed ffmpeg leaves an m4a with no
        # index (unplayable), which must never look like a finished audio.m4a.
        partial = self.partial_path(out)
        try:
            result = subprocess.run(self.command(usable, partial), capture_output=True, text=True, timeout=timeout, check=False, creationflags=NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as exc:
            partial.unlink(missing_ok=True)
            raise CaptureError(Err.MIX_FAILED.format(error=exc)) from exc
        if result.returncode != 0 or not partial.exists():
            partial.unlink(missing_ok=True)
            raise CaptureError(Err.MIX_FAILED_CODE.format(code=result.returncode, tail=result.stderr.strip()[-500:]))
        partial.replace(out)
        return out

    def timeout_for(self, seconds_of_audio: float) -> float:
        """Long meetings need long mixes: an 86-minute call did not mix within a fixed 10 minutes."""
        return max(self.timeout, seconds_of_audio * Audio.MIX_TIMEOUT_FACTOR)

    @staticmethod
    def partial_path(out: Path) -> Path:
        return out.with_name(f"{out.stem}{Audio.PARTIAL_INFIX}{out.suffix}")

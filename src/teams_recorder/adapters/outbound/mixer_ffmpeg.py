"""AudioMixer via ffmpeg: sums the tracks, normalizes loudness and encodes mono AAC."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from teams_recorder.domain import CaptureError

log = logging.getLogger(__name__)

MIN_TRACK_BYTES = 1024  # a WAV header without samples is 44 bytes; under 1 KB is garbage
ANOMALY_RATIO = 0.5     # a track shorter than half the longest one is an anomaly
DEBUG_DIR = "debug"     # raw tracks are preserved here when there is an anomaly


def probe(path: Path, ffmpeg: str = "ffmpeg") -> dict:
    """Duration (s) and mean/peak volume (dB) of a track, via ffmpeg volumedetect."""
    info: dict = {"duration": None, "mean_db": None, "max_db": None}
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return info
    out = r.stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"mean_volume: (-?[\d.]+) dB", out)
    if m:
        info["mean_db"] = float(m.group(1))
    m = re.search(r"max_volume: (-?[\d.]+) dB", out)
    if m:
        info["max_db"] = float(m.group(1))
    return info


class FfmpegMixer:
    def __init__(self, ffmpeg: str = "ffmpeg", bitrate_kbps: int = 64, sample_rate: int = 48000, timeout: float = 600.0, denoise: bool = True) -> None:
        self.ffmpeg = ffmpeg
        self.bitrate_kbps = bitrate_kbps
        self.sample_rate = sample_rate  # loudnorm resamples internally; we pin the output rate
        self.timeout = timeout
        self.denoise = denoise

    # Per track: removes hum/low-frequency noise (fan, desk) and reduces background noise
    # by continuously estimating the noise floor. After summing: normalizes loudness and
    # limits peaks to -1 dBTP, because summing two tracks (user's voice close to the
    # microphone + Teams) was clipping the final file (measured peak: +1.5 dB).
    TRACK_FILTER = "highpass=f=80,afftdn=nf=-25:tn=1"
    MASTER_FILTER = "loudnorm=I=-18:TP=-2:LRA=11,alimiter=limit=0.891:level=0"

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
        log.warning("track anomaly (%s); raw copies kept in %s", ", ".join(f"{t.name}={durations.get(t, 0):.1f}s" for t in tracks), debug)

    def mix(self, tracks: list[Path], out: Path) -> Path:
        usable = self.usable_tracks(tracks)
        durations: dict[Path, float] = {}
        for t in tracks:
            size = t.stat().st_size if t.exists() else 0
            if t in usable:
                info = probe(t, self.ffmpeg)
                if info["duration"] is not None:
                    durations[t] = info["duration"]
                log.info("track %s: %.1f MB, %.1f s, mean %s dB, peak %s dB", t.name, size / 1e6, info["duration"] or 0.0, info["mean_db"], info["max_db"])
            else:
                log.info("track %s: %.1f MB (discarded)", t.name, size / 1e6)
        self._preserve_if_anomalous(tracks, durations, out.parent)
        if not usable:
            raise CaptureError("no usable audio track to mix: " + ", ".join(str(t) for t in tracks))
        try:
            result = subprocess.run(self.command(usable, out), capture_output=True, text=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CaptureError(f"ffmpeg failed to mix: {exc}") from exc
        if result.returncode != 0 or not out.exists():
            raise CaptureError(f"ffmpeg failed to mix (code {result.returncode}): {result.stderr.strip()[-500:]}")
        return out

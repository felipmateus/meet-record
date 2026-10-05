"""AudioMixer via ffmpeg: soma as trilhas, normaliza loudness e codifica AAC mono."""
from __future__ import annotations

import subprocess
from pathlib import Path

from teams_recorder.domain import CaptureError

MIN_TRACK_BYTES = 1024  # cabeçalho WAV sem amostras tem 44 bytes; menos de 1 KB é lixo


class FfmpegMixer:
    def __init__(self, ffmpeg: str = "ffmpeg", bitrate_kbps: int = 64, sample_rate: int = 48000, timeout: float = 600.0) -> None:
        self.ffmpeg = ffmpeg
        self.bitrate_kbps = bitrate_kbps
        self.sample_rate = sample_rate  # loudnorm reamostra internamente; fixamos a saída
        self.timeout = timeout

    @staticmethod
    def usable_tracks(tracks: list[Path]) -> list[Path]:
        return [t for t in tracks if t.exists() and t.stat().st_size >= MIN_TRACK_BYTES]

    def command(self, tracks: list[Path], out: Path) -> list[str]:
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        for t in tracks:
            cmd += ["-i", str(t)]
        if len(tracks) > 1:
            inputs = "".join(f"[{i}:a]" for i in range(len(tracks)))
            filt = f"{inputs}amix=inputs={len(tracks)}:duration=longest:dropout_transition=0:normalize=0,loudnorm=I=-18:TP=-2:LRA=11[a]"
            cmd += ["-filter_complex", filt, "-map", "[a]"]
        else:
            cmd += ["-af", "loudnorm=I=-18:TP=-2:LRA=11"]
        cmd += ["-ac", "1", "-ar", str(self.sample_rate), "-c:a", "aac", "-b:a", f"{self.bitrate_kbps}k", str(out)]
        return cmd

    def mix(self, tracks: list[Path], out: Path) -> Path:
        usable = self.usable_tracks(tracks)
        if not usable:
            raise CaptureError("nenhuma trilha de áudio utilizável para mixar: " + ", ".join(str(t) for t in tracks))
        try:
            result = subprocess.run(self.command(usable, out), capture_output=True, text=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CaptureError(f"ffmpeg falhou ao mixar: {exc}") from exc
        if result.returncode != 0 or not out.exists():
            raise CaptureError(f"ffmpeg falhou ao mixar (código {result.returncode}): {result.stderr.strip()[-500:]}")
        return out

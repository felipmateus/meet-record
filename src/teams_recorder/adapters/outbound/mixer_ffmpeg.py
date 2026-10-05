"""AudioMixer via ffmpeg: soma as trilhas, normaliza loudness e codifica AAC mono."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from teams_recorder.domain import CaptureError

log = logging.getLogger(__name__)

MIN_TRACK_BYTES = 1024  # cabeçalho WAV sem amostras tem 44 bytes; menos de 1 KB é lixo
ANOMALY_RATIO = 0.5     # trilha com menos da metade da duração da mais longa é anomalia
DEBUG_DIR = "debug"     # trilhas brutas preservadas aqui quando há anomalia


def probe(path: Path, ffmpeg: str = "ffmpeg") -> dict:
    """Duração (s) e volume médio/máximo (dB) de uma trilha, via ffmpeg volumedetect."""
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
        self.sample_rate = sample_rate  # loudnorm reamostra internamente; fixamos a saída
        self.timeout = timeout
        self.denoise = denoise

    # Por trilha: remove zumbido/ruído grave (ventilador, mesa) e reduz ruído de fundo
    # estimando o piso de ruído continuamente. Depois da soma: normaliza loudness e limita
    # picos a -1 dBTP, porque a soma de duas trilhas (voz do usuário perto do microfone +
    # Teams) saturava o arquivo final (pico medido: +1,5 dB).
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
        """Se uma trilha é muito mais curta que a outra (gravador morreu), guarda cópias para diagnóstico."""
        if len(durations) < 2:
            anomalous = len(tracks) >= 2  # uma trilha inteira faltando/vazia também é anomalia
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
        log.warning("anomalia nas trilhas (%s); cópias brutas preservadas em %s", ", ".join(f"{t.name}={durations.get(t, 0):.1f}s" for t in tracks), debug)

    def mix(self, tracks: list[Path], out: Path) -> Path:
        usable = self.usable_tracks(tracks)
        durations: dict[Path, float] = {}
        for t in tracks:
            size = t.stat().st_size if t.exists() else 0
            if t in usable:
                info = probe(t, self.ffmpeg)
                if info["duration"] is not None:
                    durations[t] = info["duration"]
                log.info("trilha %s: %.1f MB, %.1f s, média %s dB, pico %s dB", t.name, size / 1e6, info["duration"] or 0.0, info["mean_db"], info["max_db"])
            else:
                log.info("trilha %s: %.1f MB (descartada)", t.name, size / 1e6)
        self._preserve_if_anomalous(tracks, durations, out.parent)
        if not usable:
            raise CaptureError("nenhuma trilha de áudio utilizável para mixar: " + ", ".join(str(t) for t in tracks))
        try:
            result = subprocess.run(self.command(usable, out), capture_output=True, text=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CaptureError(f"ffmpeg falhou ao mixar: {exc}") from exc
        if result.returncode != 0 or not out.exists():
            raise CaptureError(f"ffmpeg falhou ao mixar (código {result.returncode}): {result.stderr.strip()[-500:]}")
        return out

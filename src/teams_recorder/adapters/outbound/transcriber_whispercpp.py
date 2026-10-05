"""Transcriber via whisper.cpp (binário `whisper-cli` do Homebrew).

Fluxo: converte o áudio para WAV 16 kHz mono com ffmpeg (formato que o whisper-cli
aceita sem depender de decodificadores), roda o whisper-cli com saída JSON e converte
os segmentos para o domínio. Tudo local; nada sai do Mac.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from teams_recorder.domain import Segment, Transcript, TranscriptionError


class WhisperCppTranscriber:
    def __init__(
        self,
        model_path: Path,
        whisper_cli: str = "whisper-cli",
        ffmpeg: str = "ffmpeg",
        threads: int = 0,
        timeout: float = 3 * 3600,
        vad_model_path: Path | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.whisper_cli = whisper_cli
        self.ffmpeg = ffmpeg
        self.threads = threads or max(1, (os.cpu_count() or 4) // 2)
        self.timeout = timeout
        self.vad_model_path = Path(vad_model_path) if vad_model_path else None

    # --- comandos (públicos para teste) -----------------------------------
    def convert_command(self, audio: Path, wav: Path) -> list[str]:
        return [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(audio), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]

    def whisper_command(self, wav: Path, language: str, out_prefix: Path) -> list[str]:
        cmd = [
            self.whisper_cli,
            "-m", str(self.model_path),
            "-f", str(wav),
            "-l", language,
            "-t", str(self.threads),
            "-oj",                 # escreve <prefix>.json
            "-of", str(out_prefix),
            "-np",                 # sem prints de progresso
        ]
        if self.vad_model_path is not None and self.vad_model_path.exists():
            # Detecção de voz (Silero): só transcreve trechos com fala; reduz alucinações em silêncio.
            cmd += ["--vad", "-vm", str(self.vad_model_path), "-vt", "0.5", "-vsd", "300", "-vp", "150"]
        return cmd

    # --- porta Transcriber ------------------------------------------------
    def transcribe(self, audio: Path, language: str) -> Transcript:
        if not self.model_path.exists():
            raise TranscriptionError(
                f"modelo não encontrado em {self.model_path}. Baixe com scripts/download-model.sh"
            )
        if not audio.exists():
            raise TranscriptionError(f"áudio não encontrado: {audio}")
        with tempfile.TemporaryDirectory(prefix="trec-whisper-") as tmp:
            wav = Path(tmp) / "audio16k.wav"
            prefix = Path(tmp) / "out"
            self._run(self.convert_command(audio, wav), "conversão para WAV 16 kHz")
            self._run(self.whisper_command(wav, language, prefix), "whisper-cli")
            json_path = prefix.with_suffix(".json")
            if not json_path.exists():
                raise TranscriptionError("whisper-cli terminou sem gerar o JSON de saída")
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise TranscriptionError(f"JSON do whisper inválido: {exc}") from exc
        return parse_whisper_json(data, language)

    def _run(self, command: list[str], what: str) -> None:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        except FileNotFoundError as exc:
            raise TranscriptionError(f"{what}: executável não encontrado ({command[0]}). Instale com: brew install whisper-cpp") from exc
        except subprocess.TimeoutExpired as exc:
            raise TranscriptionError(f"{what}: tempo esgotado após {self.timeout:.0f}s") from exc
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip()[-800:]
            raise TranscriptionError(f"{what} falhou (código {result.returncode}): {tail}")


def parse_whisper_json(data: dict, language: str) -> Transcript:
    """Converte o JSON do whisper-cli (`-oj`) em Transcript.

    Formato: {"transcription": [{"timestamps": {...}, "offsets": {"from": ms, "to": ms}, "text": "..."}], ...}
    """
    segments: list[Segment] = []
    for item in data.get("transcription", []):
        offsets = item.get("offsets") or {}
        text = (item.get("text") or "").strip()
        if not text:
            continue
        start = float(offsets.get("from", 0)) / 1000.0
        end = float(offsets.get("to", offsets.get("from", 0))) / 1000.0
        segments.append(Segment(start=start, end=end, text=text))
    detected = (data.get("result") or {}).get("language") or language
    return Transcript(segments=segments, language=detected)

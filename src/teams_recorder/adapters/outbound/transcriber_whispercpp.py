"""Transcriber via whisper.cpp (Homebrew's `whisper-cli` binary).

Flow: converts the audio to 16 kHz mono WAV with ffmpeg (a format whisper-cli accepts
without depending on decoders), runs whisper-cli with JSON output and converts the
segments to the domain. Everything is local; nothing leaves the Mac.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from teams_recorder.adapters.outbound.process_control import NO_WINDOW
from teams_recorder.constants import Audio, Bin, Files, Proc
from teams_recorder.domain import Segment, Transcript, TranscriptionError
from teams_recorder.messages import Err


class WhisperCppTranscriber:
    def __init__(
        self,
        model_path: Path,
        whisper_cli: str = Bin.WHISPER_CLI,
        ffmpeg: str = Bin.FFMPEG,
        threads: int = 0,
        timeout: float = Proc.WHISPER_TIMEOUT,
        vad_model_path: Path | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.whisper_cli = whisper_cli
        self.ffmpeg = ffmpeg
        self.threads = threads or max(1, (os.cpu_count() or 4) // 2)
        self.timeout = timeout
        self.vad_model_path = Path(vad_model_path) if vad_model_path else None

    # --- commands (public for testing) ------------------------------------
    def convert_command(self, audio: Path, wav: Path) -> list[str]:
        return [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(audio), "-ac", "1", "-ar", str(Audio.WHISPER_SAMPLE_RATE), "-c:a", "pcm_s16le", str(wav)]

    def whisper_command(self, wav: Path, language: str, out_prefix: Path) -> list[str]:
        cmd = [
            self.whisper_cli,
            "-m", str(self.model_path),
            "-f", str(wav),
            "-l", language,
            "-t", str(self.threads),
            "-oj",                 # writes <prefix>.json
            "-of", str(out_prefix),
            "-np",                 # no progress prints
        ]
        if self.vad_model_path is not None and self.vad_model_path.exists():
            # Voice activity detection (Silero): only transcribes speech segments; reduces hallucinations in silence.
            cmd += ["--vad", "-vm", str(self.vad_model_path), *Audio.VAD_ARGS]
        return cmd

    # --- Transcriber port -------------------------------------------------
    def transcribe(self, audio: Path, language: str) -> Transcript:
        if not self.model_path.exists():
            raise TranscriptionError(Err.MODEL_MISSING.format(path=self.model_path, script=Files.DOWNLOAD_MODEL_SCRIPT))
        if not audio.exists():
            raise TranscriptionError(Err.AUDIO_MISSING.format(path=audio))
        with tempfile.TemporaryDirectory(prefix="trec-whisper-") as tmp:
            wav = Path(tmp) / "audio16k.wav"
            prefix = Path(tmp) / "out"
            self._run(self.convert_command(audio, wav), Err.STEP_CONVERT_WAV)
            self._run(self.whisper_command(wav, language, prefix), Bin.WHISPER_CLI)
            json_path = prefix.with_suffix(".json")
            if not json_path.exists():
                raise TranscriptionError(Err.WHISPER_NO_JSON)
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise TranscriptionError(Err.WHISPER_BAD_JSON.format(error=exc)) from exc
        return parse_whisper_json(data, language)

    def _run(self, command: list[str], what: str) -> None:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, check=False, creationflags=NO_WINDOW)
        except FileNotFoundError as exc:
            raise TranscriptionError(Err.EXECUTABLE_MISSING.format(what=what, command=command[0])) from exc
        except subprocess.TimeoutExpired as exc:
            raise TranscriptionError(Err.TIMED_OUT.format(what=what, seconds=self.timeout)) from exc
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip()[-800:]
            raise TranscriptionError(Err.STEP_FAILED_CODE.format(what=what, code=result.returncode, tail=tail))


def parse_whisper_json(data: dict[str, Any], language: str) -> Transcript:
    """Converts whisper-cli's JSON (`-oj`) into a Transcript.

    Format: {"transcription": [{"timestamps": {...}, "offsets": {"from": ms, "to": ms}, "text": "..."}], ...}
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

"""Language detector via whisper.cpp (docs/tasks/language-detection).

Flow: cuts one 16 kHz mono WAV per sample offset out of the audio with ffmpeg (a temporary directory, removed on exit), runs
one `whisper-cli -l auto -dl` over all of them (the model loads once) and reads the `auto-detected language` line printed for
each file. Everything is local; nothing is written to the meeting's folder.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import wave
from collections.abc import Sequence
from pathlib import Path

from teams_recorder.adapters.outbound.process_control import NO_WINDOW
from teams_recorder.constants import Audio, Bin, Files, Parse, Proc
from teams_recorder.domain import LanguageSample, TranscriptionError
from teams_recorder.messages import Err

_TAIL_CHARS = 800


class WhisperCppLanguageDetector:
    def __init__(
        self,
        model_path: Path,
        whisper_cli: str = Bin.WHISPER_CLI,
        ffmpeg: str = Bin.FFMPEG,
        threads: int = 0,
        timeout: float = Proc.LANGUAGE_DETECT_TIMEOUT,
    ) -> None:
        self.model_path = Path(model_path)
        self.whisper_cli = whisper_cli
        self.ffmpeg = ffmpeg
        self.threads = threads or max(1, (os.cpu_count() or 4) // 2)
        self.timeout = timeout

    # --- commands (public for testing) ------------------------------------
    def clip_command(self, audio: Path, offset: float, window: float, wav: Path) -> list[str]:
        """`-ss` before `-i`: a fast seek, so cutting a sample deep into a long meeting costs about the same as at its start."""
        return [
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-ss", _seconds(offset), "-t", _seconds(window), "-i", str(audio),
            "-ac", "1", "-ar", str(Audio.WHISPER_SAMPLE_RATE), "-c:a", "pcm_s16le", str(wav),
        ]

    def detect_command(self, wavs: Sequence[Path]) -> list[str]:
        """Never `-np`: it suppresses the `auto-detected language` line this adapter reads."""
        cmd = [self.whisper_cli, "-m", str(self.model_path), "-l", "auto", "-dl", "-t", str(self.threads)]
        for wav in wavs:
            cmd += ["-f", str(wav)]
        return cmd

    # --- LanguageDetector port --------------------------------------------
    def detect(self, audio: Path, offsets: Sequence[float], window_seconds: float) -> list[LanguageSample]:
        if not self.model_path.exists():
            raise TranscriptionError(Err.MODEL_MISSING.format(path=self.model_path, script=Files.DOWNLOAD_MODEL_SCRIPT))
        if not audio.exists():
            raise TranscriptionError(Err.AUDIO_MISSING.format(path=audio))
        samples = [LanguageSample(at=offset, language=None) for offset in offsets]
        with tempfile.TemporaryDirectory(prefix="trec-lang-") as tmp:
            clips: dict[int, Path] = {}   # offset index -> its WAV, for the clips that hold audio
            for i, offset in enumerate(offsets):
                wav = Path(tmp) / f"c{i}.wav"
                self._run(self.clip_command(audio, offset, window_seconds, wav), Err.STEP_CUT_SAMPLE)
                if _seconds_of_audio(wav) >= Audio.MIN_LANGUAGE_CLIP_SECONDS:
                    clips[i] = wav
            if not clips:
                return samples
            wavs = list(clips.values())
            output = self._run(self.detect_command(wavs), Bin.WHISPER_CLI)
        answers = parse_detection(output, wavs)
        if all(language is None for language, _ in answers):
            raise TranscriptionError(Err.WHISPER_NO_LANGUAGE.format(count=len(wavs), tail=output.strip()[-_TAIL_CHARS:]))
        for i, (language, probability) in zip(clips, answers):
            samples[i] = LanguageSample(at=offsets[i], language=language, probability=probability)
        return samples

    def _run(self, command: list[str], what: str) -> str:
        """Runs one command and returns its stdout and stderr (whisper-cli prints what we read to stderr)."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, check=False, creationflags=NO_WINDOW)
        except FileNotFoundError as exc:
            raise TranscriptionError(Err.EXECUTABLE_MISSING.format(what=what, command=command[0])) from exc
        except subprocess.TimeoutExpired as exc:
            raise TranscriptionError(Err.TIMED_OUT.format(what=what, seconds=self.timeout)) from exc
        output = f"{result.stderr or ''}\n{result.stdout or ''}"
        if result.returncode != 0:
            raise TranscriptionError(Err.STEP_FAILED_CODE.format(what=what, code=result.returncode, tail=output.strip()[-_TAIL_CHARS:]))
        return output


def _seconds(value: float) -> str:
    """`134.7`, `30`: no trailing zeros, never an exponent."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _seconds_of_audio(wav: Path) -> float:
    """Length of a PCM WAV; 0 when ffmpeg wrote nothing (an offset past the end of the audio)."""
    try:
        with wave.open(str(wav), "rb") as clip:
            return clip.getnframes() / float(clip.getframerate() or 1)
    except FileNotFoundError:
        return 0.0
    except (wave.Error, EOFError) as exc:
        raise TranscriptionError(Err.CLIP_BAD_WAV.format(wav=wav, error=exc)) from exc


def parse_detection(output: str, wavs: Sequence[Path]) -> list[tuple[str | None, float]]:
    """Answers per wav, in order, from whisper-cli's combined stdout+stderr: each `processing '<path>' (` line opens a file,
    identified by its basename (`c<i>.wav`, a name the adapter chose), and the next `auto-detected language: <code> (p = <float>)`
    line answers it; a file with no answer gets (None, 0.0).

    Binding by basename, not by position or by full path: a skipped file shifts every later answer, and a temporary
    directory may hold an apostrophe that cuts a pattern stopping at the first quote."""
    index = {wav.name: i for i, wav in enumerate(wavs)}
    answers: list[tuple[str | None, float]] = [(None, 0.0)] * len(wavs)
    current: int | None = None
    for line in output.splitlines():
        opened = re.search(Parse.WHISPER_PROCESSING, line)
        if opened:
            current = index.get(opened.group(1))
            continue
        heard = re.search(Parse.WHISPER_LANGUAGE, line)
        if heard and current is not None:
            try:
                answers[current] = (heard.group(1), float(heard.group(2)))
            except ValueError:
                pass   # a malformed probability is no answer
            current = None
    return answers

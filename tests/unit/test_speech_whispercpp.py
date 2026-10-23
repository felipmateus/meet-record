"""The whisper.cpp speech adapter, without running anything real: docs/tasks/speech-check/_tests.md UT-030 to UT-036."""
from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.audio_convert import wav_convert_command
from teams_recorder.adapters.outbound.process_control import NO_WINDOW
from teams_recorder.adapters.outbound.speech_whispercpp import WhisperCppSpeechDetector, parse_speech_segments
from teams_recorder.constants import Audio, Bin, Files, Proc
from teams_recorder.domain import SpeechActivity, TranscriptionError
from teams_recorder.messages import Err

TOOL = "whisper-vad-speech-segments"
OUTPUT = (
    "\nDetected 2 speech segments:\n"
    "Speech segment 0: start = 0.00, end = 419.00\n"
    "Speech segment 1: start = 458.00, end = 720.00\n\n"
)


@pytest.fixture
def model(tmp_path: Path) -> Path:
    m = tmp_path / "ggml-silero.bin"
    m.write_bytes(b"\x00")
    return m


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    a = tmp_path / "audio.m4a"
    a.write_bytes(b"x")
    return a


@pytest.fixture
def own_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The directory `tempfile` uses, so a test can see whether the adapter left anything in it."""
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _detector(model: Path, **kwargs) -> WhisperCppSpeechDetector:
    return WhisperCppSpeechDetector(model, vad_tool=TOOL, ffmpeg="ffmpeg", threads=4, **kwargs)


def _write_wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(Audio.WHISPER_SAMPLE_RATE)
        clip.writeframes(b"\x00\x00" * round(seconds * Audio.WHISPER_SAMPLE_RATE))


class Spawns:
    """A stand-in for `subprocess.run`: ffmpeg writes a WAV of `seconds`, the VAD tool prints `output`; `failing` is the step
    ("convert" or "vad") that raises or returns `failure` instead. Every call is recorded."""

    def __init__(self, seconds: float = 27.3, output: str = OUTPUT, failing: str | None = None,
                 failure: Exception | subprocess.CompletedProcess | None = None) -> None:
        self.seconds, self.output, self.failing, self.failure = seconds, output, failing, failure
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command: list[str], **kwargs) -> subprocess.CompletedProcess:
        self.calls.append((command, kwargs))
        step = "convert" if command[0] == "ffmpeg" else "vad"
        if step == self.failing:
            if isinstance(self.failure, Exception):
                raise self.failure
            assert self.failure is not None
            return self.failure
        if step == "convert":
            _write_wav(Path(command[-1]), self.seconds)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout=self.output, stderr="ggml_metal_device_init: GPU name:   MTL0\n")


@pytest.fixture
def spawns(monkeypatch: pytest.MonkeyPatch):
    def install(**kwargs) -> Spawns:
        fake = Spawns(**kwargs)
        monkeypatch.setattr(subprocess, "run", fake)
        return fake
    return install


# --- UT-030 -------------------------------------------------------------------------------
def test_ut030_the_vad_command_is_the_tool_the_model_the_wav_no_prints_the_threads_and_the_project_vad_arguments():
    cmd = _detector(Path("/models/ggml-silero.bin")).vad_command(Path("/tmp/x/audio16k.wav"))

    assert cmd == [TOOL, "-vm", "/models/ggml-silero.bin", "-f", "/tmp/x/audio16k.wav", "-np", "-t", "4",
                   "-vt", "0.5", "-vsd", "300", "-vp", "150"]
    assert cmd[-6:] == Audio.VAD_ARGS


def test_ut030_the_defaults_are_the_real_tool_ffmpeg_a_positive_thread_count_and_the_speech_check_timeout(model: Path):
    detector = WhisperCppSpeechDetector(model)

    assert (detector.vad_tool, detector.ffmpeg, detector.timeout) == (Bin.WHISPER_VAD, Bin.FFMPEG, Proc.SPEECH_CHECK_TIMEOUT)
    assert detector.threads >= 1 and detector.vad_command(Path("a.wav"))[0] == TOOL


def test_the_conversion_is_the_shared_one(model: Path):
    assert _detector(model).convert_command(Path("a.m4a"), Path("a.wav")) == wav_convert_command("ffmpeg", Path("a.m4a"), Path("a.wav"))


# --- UT-031 / UT-032: the parser ------------------------------------------------------------
def test_ut031_segments_are_read_in_seconds_from_centiseconds():
    assert parse_speech_segments(OUTPUT) == ((0.0, 4.19), (4.58, 7.2))


def test_ut031_lines_around_the_list_are_ignored():
    noisy = (
        "ggml_metal_device_init: GPU name:   MTL0 (Apple M1)\n"
        "read_audio_data: reading audio data from 'audio16k.wav' ...\n"
        "Speech segment 7: this is not a segment line\n"
        f"{OUTPUT}"
        "whisper_free: done\n"
    )

    assert parse_speech_segments(noisy) == ((0.0, 4.19), (4.58, 7.2))


def test_ut031_the_unit_is_centiseconds_a_27_3_second_file_ends_at_2067():
    """Verified on 2026-10-22 on the real tool (spec › Assumptions): `2067.00` is 20.67 s, not 2067 s and not 2.067 s."""
    output = "Detected 1 speech segments:\nSpeech segment 0: start = 1854.00, end = 2067.00\n"

    assert parse_speech_segments(output) == ((18.54, 20.67),)


def test_ut031_windows_line_endings_and_indentation_are_read():
    assert parse_speech_segments(OUTPUT.replace("\n", "\r\n")) == ((0.0, 4.19), (4.58, 7.2))
    assert parse_speech_segments("  Detected 1 speech segments:  \n\tSpeech segment 0: start = 5.00, end = 10.00 \n") == ((0.05, 0.1),)


def test_ut032_a_count_of_zero_is_no_segments():
    assert parse_speech_segments("Detected 0 speech segments:\n") == ()
    assert parse_speech_segments("\nDetected 0 speech segments:\n\n") == ()


# --- UT-033 / UT-034: a format change is a failed check, never "no speech" --------------------
def test_ut033_segment_lines_without_a_count_line_are_bad_output_with_the_tail():
    output = "Speech segment 0: start = 0.00, end = 419.00\nSpeech segment 1: start = 458.00, end = 720.00\n"

    with pytest.raises(TranscriptionError) as raised:
        parse_speech_segments(output)

    assert str(raised.value) == Err.VAD_BAD_OUTPUT.format(tail=output.strip())


@pytest.mark.parametrize("output", [
    "",                                                          # the tool printed nothing at all
    "\n\n",
    "Detected: 0 speech segments\n",                             # the count line reworded: must not read as zero segments
    "Found 2 speech segments:\nSpeech segment 0: start = 0.00, end = 419.00\n",
    "Detected 0 speech segment(s):\n",
    "Detected two speech segments:\n",
])
def test_ut033_an_output_with_no_readable_count_line_is_bad_output_never_no_speech(output: str):
    with pytest.raises(TranscriptionError) as raised:
        parse_speech_segments(output)

    assert str(raised.value) == Err.VAD_BAD_OUTPUT.format(tail=output.strip())


def test_ut033_the_tail_is_the_last_800_characters():
    output = "ggml log line to push the tail out\n" * 100 + "Detected 5 speech segments:\n"

    with pytest.raises(TranscriptionError) as raised:
        parse_speech_segments(output)

    assert str(raised.value) == Err.VAD_BAD_OUTPUT.format(tail=output.strip()[-800:])
    assert str(raised.value).endswith("Detected 5 speech segments:")


@pytest.mark.parametrize("output", [
    "Detected 3 speech segments:\nSpeech segment 0: start = 0.00, end = 419.00\nSpeech segment 1: start = 458.00, end = 720.00\n",
    "Detected 1 speech segments:\nSpeech segment 0: start = 0.00, end = 419.00\nSpeech segment 1: start = 458.00, end = 720.00\n",
    "Detected 2 speech segments:\nSpeech segment 0: start = 0.00, end = 419.00\nSpeech segment 1: start = 458.00\n",   # a segment line cut short
    "Detected 2 speech segments:\nSpeech segment 0: start = 0.00, end = 419.00\nSpeech segment 1: begin = 458.00, end = 720.00\n",
])
def test_ut034_a_count_that_differs_from_the_segment_lines_read_is_bad_output(output: str):
    with pytest.raises(TranscriptionError) as raised:
        parse_speech_segments(output)

    assert str(raised.value) == Err.VAD_BAD_OUTPUT.format(tail=output.strip())


# --- UT-035: the inputs are checked before any process starts ----------------------------------
def test_ut035_a_missing_model_raises_before_anything_is_spawned(spawns, tmp_path: Path, audio: Path):
    fake = spawns()
    missing = tmp_path / "ggml-silero.bin"

    with pytest.raises(TranscriptionError) as raised:
        _detector(missing).activity(audio)

    assert str(raised.value) == Err.MODEL_MISSING.format(path=missing, script=Files.DOWNLOAD_MODEL_SCRIPT)
    assert fake.calls == []


def test_ut035_a_missing_audio_raises_before_anything_is_spawned(spawns, model: Path, tmp_path: Path):
    fake = spawns()

    with pytest.raises(TranscriptionError) as raised:
        _detector(model).activity(tmp_path / "gone.m4a")

    assert str(raised.value) == Err.AUDIO_MISSING.format(path=tmp_path / "gone.m4a")
    assert fake.calls == []


def test_ut035_the_model_is_reported_before_the_audio(spawns, tmp_path: Path):
    fake = spawns()

    with pytest.raises(TranscriptionError, match="model not found"):
        _detector(tmp_path / "no-model.bin").activity(tmp_path / "no-audio.m4a")

    assert fake.calls == []


# --- UT-036: process errors map like the language adapter ---------------------------------------
STEPS = [
    pytest.param("convert", Err.STEP_CONVERT_WAV, "ffmpeg", id="ffmpeg"),
    pytest.param("vad", Bin.WHISPER_VAD, TOOL, id="vad-tool"),
]


@pytest.mark.parametrize("step, what, command", STEPS)
def test_ut036_a_missing_executable_names_the_step_and_the_command(spawns, model: Path, audio: Path, own_tmp: Path,
                                                                   step: str, what: str, command: str):
    spawns(failing=step, failure=FileNotFoundError("no such file"))

    with pytest.raises(TranscriptionError) as raised:
        _detector(model).activity(audio)

    assert str(raised.value) == Err.EXECUTABLE_MISSING.format(what=what, command=command)
    assert list(own_tmp.iterdir()) == []


@pytest.mark.parametrize("step, what, command", STEPS)
def test_ut036_a_timeout_names_the_step_and_the_seconds(spawns, model: Path, audio: Path, own_tmp: Path,
                                                        step: str, what: str, command: str):
    spawns(failing=step, failure=subprocess.TimeoutExpired(command, 300.0))

    with pytest.raises(TranscriptionError) as raised:
        _detector(model, timeout=300.0).activity(audio)

    assert str(raised.value) == Err.TIMED_OUT.format(what=what, seconds=300.0)
    assert str(raised.value) == f"{what}: timed out after 300s"
    assert list(own_tmp.iterdir()) == []


@pytest.mark.parametrize("step, what, command", STEPS)
def test_ut036_a_non_zero_exit_carries_the_code_and_the_output_tail(spawns, model: Path, audio: Path, own_tmp: Path,
                                                                    step: str, what: str, command: str):
    spawns(failing=step, failure=subprocess.CompletedProcess([command], 1, stdout="", stderr="boom"))

    with pytest.raises(TranscriptionError) as raised:
        _detector(model).activity(audio)

    assert str(raised.value) == Err.STEP_FAILED_CODE.format(what=what, code=1, tail="boom")
    assert list(own_tmp.iterdir()) == []


def test_ut036_the_tool_that_fails_after_the_conversion_is_not_asked_twice(spawns, model: Path, audio: Path):
    fake = spawns(failing="convert", failure=subprocess.CompletedProcess(["ffmpeg"], 1, stdout="", stderr="boom"))

    with pytest.raises(TranscriptionError):
        _detector(model).activity(audio)

    assert [command[0] for command, _ in fake.calls] == ["ffmpeg"]   # the VAD tool never ran


def test_ut036_bad_output_removes_the_temporary_directory_too(spawns, model: Path, audio: Path, own_tmp: Path):
    spawns(output="Detected 2 speech segments:\nSpeech segment 0: start = 0.00, end = 419.00\n")

    with pytest.raises(TranscriptionError, match="no readable segment list"):
        _detector(model).activity(audio)

    assert list(own_tmp.iterdir()) == []


# --- the success path with the spawns faked: what reaches the tools, and where the length comes from -----
def test_the_activity_has_the_segments_of_the_tool_and_the_length_of_the_converted_wav(spawns, model: Path, audio: Path, own_tmp: Path):
    fake = spawns(seconds=27.3)

    activity = _detector(model).activity(audio)

    assert activity == SpeechActivity(audio_seconds=27.3, segments=((0.0, 4.19), (4.58, 7.2)))
    (convert, _), (vad, _) = fake.calls
    wav = Path(convert[-1])
    assert wav.parent.name.startswith("trec-speech-") and wav.parent.parent == own_tmp
    assert convert == wav_convert_command("ffmpeg", audio, wav)
    assert vad == _detector(model).vad_command(wav)
    assert list(own_tmp.iterdir()) == []   # Safety Invariant 3: the WAV is gone


def test_every_spawn_hides_the_console_window_and_has_the_timeout(spawns, model: Path, audio: Path):
    fake = spawns()

    _detector(model, timeout=123.0).activity(audio)

    assert len(fake.calls) == 2
    assert all(kwargs["creationflags"] == NO_WINDOW and kwargs["timeout"] == 123.0 for _, kwargs in fake.calls)


def test_the_check_writes_nothing_next_to_the_audio(spawns, model: Path, audio: Path):
    spawns()
    before = sorted(p.name for p in audio.parent.iterdir())

    _detector(model).activity(audio)

    assert sorted(p.name for p in audio.parent.iterdir()) == before


def test_no_segments_still_report_the_audio_length(spawns, model: Path, audio: Path):
    spawns(seconds=10.0, output="\nDetected 0 speech segments:\n\n")

    assert _detector(model).activity(audio) == SpeechActivity(audio_seconds=10.0, segments=())


def test_a_converted_file_that_is_not_a_wav_is_a_failed_check(monkeypatch: pytest.MonkeyPatch, model: Path, audio: Path, own_tmp: Path):
    def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"this is not a wav file")
        return subprocess.CompletedProcess(command, 0, stdout=OUTPUT, stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(TranscriptionError, match="not a readable WAV"):
        _detector(model).activity(audio)

    assert list(own_tmp.iterdir()) == []


def test_a_conversion_that_wrote_no_file_is_a_failed_check(monkeypatch: pytest.MonkeyPatch, model: Path, audio: Path, own_tmp: Path):
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout=OUTPUT, stderr=""))

    with pytest.raises(TranscriptionError, match="not a readable WAV"):
        _detector(model).activity(audio)

    assert list(own_tmp.iterdir()) == []

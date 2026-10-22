"""The whisper.cpp language adapter, without running anything: docs/tasks/language-detection/_tests.md UT-013 to UT-017."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.language_whispercpp import WhisperCppLanguageDetector, parse_detection
from teams_recorder.constants import Files
from teams_recorder.domain import TranscriptionError
from teams_recorder.messages import Err

MODEL = Path("/models/ggml-fake.bin")


def _detector(**kwargs) -> WhisperCppLanguageDetector:
    return WhisperCppLanguageDetector(MODEL, whisper_cli="whisper-cli", ffmpeg="ffmpeg", threads=4, **kwargs)


def _output(directory: str, answers: list[tuple[str, str] | None], quote: str = "'") -> str:
    """whisper-cli's stderr for files c0.wav..: each `processing` line, then its answer line when there is one."""
    lines = ["whisper_init_from_file_with_params_no_state: loading model"]
    for i, answer in enumerate(answers):
        lines.append(f"main: processing {quote}{directory}c{i}.wav{quote} (480000 samples, 30.0 sec), 4 threads, 1 processors, lang = auto")
        lines.append("whisper_full_with_state: kv self size = 1 MB")
        if answer:
            lines.append(f"whisper_full_with_state: auto-detected language: {answer[0]} (p = {answer[1]})")
    return "\n".join(lines) + "\n"


WAVS = [Path(f"/tmp/trec-lang-x/c{i}.wav") for i in range(3)]
THREE = [("en", "0.993000"), ("is", "0.965000"), ("en", "0.997000")]
EXPECTED = [("en", 0.993), ("is", 0.965), ("en", 0.997)]


def test_ut013_the_clip_command_seeks_before_the_input_and_writes_a_16k_mono_wav():
    cmd = _detector().clip_command(Path("a.m4a"), 134.7, 30.0, Path("c0.wav"))

    assert cmd[cmd.index("-ss"):cmd.index("-i") + 2] == ["-ss", "134.7", "-t", "30", "-i", "a.m4a"]
    assert cmd[-7:] == ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "c0.wav"]


def test_ut014_the_detect_command_lists_every_clip_with_its_full_path_and_never_hides_the_answer():
    cmd = _detector().detect_command(WAVS)

    assert cmd[:9] == ["whisper-cli", "-m", str(MODEL), "-l", "auto", "-dl", "-t", "4", "-f"]
    assert [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-f"] == [str(wav) for wav in WAVS]
    assert "-np" not in cmd


def test_ut015_the_answers_are_read_in_order():
    assert parse_detection(_output("/tmp/trec-lang-x/", THREE), WAVS) == EXPECTED


@pytest.mark.parametrize("directory", ["/tmp/O'Brien/trec-lang-x/", "", "C:\\Users\\O'Brien\\AppData\\Local\\Temp\\trec-lang-x\\"])
def test_ut015a_the_answers_are_bound_by_basename_whatever_the_directory_holds(directory: str):
    assert parse_detection(_output(directory, THREE), WAVS) == EXPECTED


def test_ut016_no_answer_line_gives_no_answers():
    assert parse_detection(_output("/tmp/trec-lang-x/", [None, None, None]), WAVS) == [(None, 0.0)] * 3


def test_ut016_a_clip_whisper_skipped_leaves_its_neighbours_with_their_own_answers():
    output = _output("/tmp/trec-lang-x/", [("en", "0.990000"), None, ("pt", "0.980000")])
    skipped = "\n".join(line for line in output.splitlines() if "c1.wav" not in line)   # its processing line is gone too

    assert parse_detection(skipped, WAVS) == [("en", 0.99), (None, 0.0), ("pt", 0.98)]


def test_ut016_an_answer_of_a_file_the_detector_did_not_send_is_ignored():
    output = _output("/tmp/trec-lang-x/", THREE)

    assert parse_detection(output, WAVS[:2]) == EXPECTED[:2]


def test_ut017_a_missing_model_raises_before_anything_is_spawned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    spawned: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: spawned.append(a))
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"x")

    with pytest.raises(TranscriptionError, match="model not found") as raised:
        _detector().detect(audio, [0.0], 30.0)

    assert str(raised.value) == Err.MODEL_MISSING.format(path=MODEL, script=Files.DOWNLOAD_MODEL_SCRIPT)
    assert spawned == []


def test_a_missing_audio_is_a_detection_failure_not_a_crash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    spawned: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: spawned.append(a))
    model = tmp_path / "ggml-fake.bin"
    model.write_bytes(b"\x00")

    with pytest.raises(TranscriptionError) as raised:
        WhisperCppLanguageDetector(model).detect(tmp_path / "gone.m4a", [0.0], 30.0)

    assert str(raised.value) == Err.AUDIO_MISSING.format(path=tmp_path / "gone.m4a")
    assert spawned == []


def test_no_offsets_need_no_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    spawned: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: spawned.append(a))
    model, audio = tmp_path / "ggml-fake.bin", tmp_path / "audio.m4a"
    model.write_bytes(b"\x00")
    audio.write_bytes(b"x")

    assert WhisperCppLanguageDetector(model).detect(audio, [], 30.0) == []
    assert spawned == []


@pytest.mark.parametrize("raised, message", [
    (FileNotFoundError("no such file"), Err.EXECUTABLE_MISSING.format(what=Err.STEP_CUT_SAMPLE, command="ffmpeg")),
    (subprocess.TimeoutExpired("ffmpeg", 300.0), Err.TIMED_OUT.format(what=Err.STEP_CUT_SAMPLE, seconds=300.0)),
])
def test_a_missing_executable_and_a_timeout_are_transcription_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                                     raised: Exception, message: str):
    def run(*args, **kwargs):
        raise raised

    monkeypatch.setattr(subprocess, "run", run)
    model, audio = tmp_path / "ggml-fake.bin", tmp_path / "audio.m4a"
    model.write_bytes(b"\x00")
    audio.write_bytes(b"x")

    with pytest.raises(TranscriptionError) as error:
        WhisperCppLanguageDetector(model, ffmpeg="ffmpeg", timeout=300.0).detect(audio, [0.0], 30.0)

    assert str(error.value) == message

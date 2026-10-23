"""The language lines of `trec transcribe`, `trec status` and `trec doctor`: docs/tasks/language-detection/_tests.md UT-060 to UT-068.

The expected texts are written out here, character for character, from the frozen lines of `_dx.md`, so a wording change in
messages.py fails these tests on purpose."""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from teams_recorder.adapters.inbound import cli
from teams_recorder.adapters.inbound.cli import app
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.config import ENV_PROJECT_DIR
from teams_recorder.domain import (
    LanguageDetection, LanguageReason, LanguageSample, Meeting, Segment, Transcript, TranscriptionError,
)
from teams_recorder.domain.status import AUDIO
from teams_recorder.messages import Err, Log
from tests.fakes import FakeLanguageDetector, FakeTranscriber

runner = CliRunner()
ALLOWED = ("pt", "en")


def _samples(*answers: str | None) -> tuple[LanguageSample, ...]:
    return tuple(LanguageSample(float(i * 60), code, 0.99 if code else 0.0) for i, code in enumerate(answers))


def _line(language: str, detection: LanguageDetection | None, allowed: tuple[str, ...] = ALLOWED) -> str:
    return cli._language_line(Transcript([Segment(0, 1, "oi")], language, language_detection=detection), allowed)


# --- UT-060 to UT-064: the six forms of the `Language:` line -------------------------------------------------------------

def test_ut060_a_detected_language_says_how_many_counted_samples_heard_it():
    detection = LanguageDetection("en", LanguageReason.MAJORITY, 3, 3, _samples("en", "is", "en", "is", "en", "is", "is", None))
    assert _line("en", detection) == "  Language: en (heard in 3 of 3 counted samples; 8 taken)"


def test_ut061_no_usable_sample_names_the_allowed_languages():
    detection = LanguageDetection("pt", LanguageReason.NO_USABLE_SAMPLE, 0, 0, _samples(*["is"] * 8))
    assert _line("pt", detection) == "  Language: pt (fallback: no sample heard pt or en clearly; 8 taken)"


def test_ut061_the_allowed_languages_read_as_a_list_for_three_and_alone_for_one():
    detection = LanguageDetection("pt", LanguageReason.NO_USABLE_SAMPLE, 0, 0, _samples(None))
    assert _line("pt", detection, ("pt", "en", "es")) == "  Language: pt (fallback: no sample heard pt, en or es clearly; 1 taken)"
    assert _line("pt", detection, ("pt",)) == "  Language: pt (fallback: no sample heard pt clearly; 1 taken)"


def test_ut062_no_majority_shows_the_counted_tally_in_allowed_order():
    detection = LanguageDetection("pt", LanguageReason.NO_MAJORITY, 4, 0, _samples("en", "pt", "pt", "en", "is"))
    assert _line("pt", detection) == "  Language: pt (fallback: no majority among 4 counted samples: pt 2, en 2)"


def test_ut062a_too_few_votes_names_the_one_counted_sample():
    detection = LanguageDetection("pt", LanguageReason.TOO_FEW_VOTES, 1, 0, _samples("en", "is", None))
    assert _line("pt", detection) == "  Language: pt (fallback: only one counted sample (en); 2 needed; 3 taken)"


def test_ut063_a_failed_detection_points_to_the_warning():
    detection = LanguageDetection("pt", LanguageReason.DETECTION_FAILED)
    assert _line("pt", detection) == "  Language: pt (fallback: language detection failed; see the warning above)"


def test_ut064_a_transcript_without_a_record_was_made_with_a_fixed_language():
    assert _line("pt", None) == "  Language: pt (fixed by [transcription] language)"
    assert _line("en", None) == "  Language: en (fixed by [transcription] language)"


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: str = "") -> FsMeetingRepository:
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if config:
        (tmp_path / "config.toml").write_text(config)
    return FsMeetingRepository(tmp_path / "data")


def _with_container(monkeypatch: pytest.MonkeyPatch, **fields) -> None:
    build = cli.build_container
    monkeypatch.setattr(cli, "build_container", lambda settings, **kw: replace(build(settings, **kw), **fields))


def test_ut063_through_the_cli_a_failing_detector_gives_the_fallback_line_and_the_warning_it_points_to(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    # The warning is asserted with caplog: pytest's logging plugin captures the record, so it never reaches the last-resort
    # handler (stderr) here. That the handler prints it in a real run is stdlib behavior.
    repo = _project(tmp_path, monkeypatch)
    meeting = Meeting.start(datetime(2026, 10, 21, 9, 30, 28))
    repo.create(meeting)
    repo.path(meeting.id, AUDIO).write_bytes(b"\x00")
    failure = TranscriptionError(Err.WHISPER_NO_LANGUAGE.format(count=8, tail="main: processing"))
    _with_container(monkeypatch, transcriber=FakeTranscriber(), retry_transcriber=None, language_detector=FakeLanguageDetector(error=failure))
    caplog.set_level(logging.WARNING)

    result = runner.invoke(app, ["transcribe", meeting.id])

    assert result.exit_code == 0, result.output
    assert "  Language: pt (fallback: language detection failed; see the warning above)\n" in result.output
    (warning,) = [r for r in caplog.records if r.msg == Log.LANGUAGE_DETECTION_FAILED]
    assert warning.levelno == logging.WARNING and warning.args is not None
    assert warning.args[:2] == (meeting.id, "pt") and warning.args[2] is failure
    assert meeting.id in warning.getMessage() and str(failure) in warning.getMessage()


# --- UT-065, UT-066: the status marker -----------------------------------------------------------------------------------

def _transcribed(repo: FsMeetingRepository, minute: int, language: str | None) -> str:
    meeting = Meeting.start(datetime(2026, 10, 8, 10, minute, 0), title=f"M{minute}")
    repo.create(meeting)
    if language is not None:
        repo.save_transcript(meeting.id, Transcript([Segment(0, 1, "oi")], language))
    return meeting.id


def test_ut065_an_english_transcript_gets_the_marker_after_the_other_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _project(tmp_path, monkeypatch)
    _transcribed(repo, 0, "en")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "  2026-10-08_10-00-00 M0  [transcribed] → next: analyze  · en\n" in result.output


def test_ut066_portuguese_and_untranscribed_meetings_get_no_marker_and_another_code_is_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _project(tmp_path, monkeypatch)
    _transcribed(repo, 0, "pt")
    _transcribed(repo, 10, None)
    _transcribed(repo, 20, "es")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "  2026-10-08_10-00-00 M0  [transcribed] → next: analyze" in lines
    untranscribed = next(line for line in lines if "M10" in line)   # no transcript.json: no marker
    assert "·" not in untranscribed
    assert "  2026-10-08_10-20-00 M20  [transcribed] → next: analyze  · es" in lines


def test_ut066_a_marker_follows_the_degraded_and_unconfirmed_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from teams_recorder.domain import TranscriptHealth
    repo = _project(tmp_path, monkeypatch)
    meeting = Meeting.start(datetime(2026, 10, 8, 10, 0, 0))
    repo.create(meeting)
    repo.save_transcript(meeting.id, Transcript([Segment(0, 1, "oi")], "en", TranscriptHealth(0.668, 28, 86, True, ((0, 14),))))

    result = runner.invoke(app, ["status"])

    assert "⚠ degraded transcript (67% in repetition loops)  · en\n" in result.output


# --- UT-067, UT-068: the doctor line -------------------------------------------------------------------------------------

def _doctor_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: str = "") -> tuple[int, list[str]]:
    _project(tmp_path, monkeypatch, config)
    result = runner.invoke(app, ["doctor"])
    return result.exit_code, result.output.splitlines()


def test_ut067_doctor_names_the_detection_mode_after_the_retry_and_speech_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _, lines = _doctor_lines(tmp_path, monkeypatch, '[transcription]\nlanguage = "auto"\n')
    retry = next(i for i, line in enumerate(lines) if "retry of a degraded transcript:" in line)
    assert "speech check:" in lines[retry + 1]   # the speech check's line (docs/tasks/speech-check) sits between the two; its form depends on the machine
    assert lines[retry + 2] == "[info] language: detected per meeting among pt, en (fallback pt)"
    assert lines[retry - 1].startswith("[info] transcription: whisper -mc 0;")   # the two loop-guard lines stay together


def test_ut067_the_fallback_is_the_first_allowed_language(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _, lines = _doctor_lines(tmp_path, monkeypatch, '[transcription]\nlanguages = ["en", "pt"]\n')
    assert "[info] language: detected per meeting among en, pt (fallback en)" in lines


def test_ut068_doctor_names_a_fixed_language_and_its_exit_code_is_unaffected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auto_code, _ = _doctor_lines(tmp_path, monkeypatch, '[transcription]\nlanguage = "auto"\n')
    code, lines = _doctor_lines(tmp_path, monkeypatch, '[transcription]\nlanguage = "pt"\n')
    retry = next(i for i, line in enumerate(lines) if "retry of a degraded transcript:" in line)
    assert "speech check:" in lines[retry + 1] and lines[retry + 2] == "[info] language: pt for every meeting ([transcription] language)"
    assert code == auto_code

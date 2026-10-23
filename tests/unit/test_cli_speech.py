"""The speech check in the CLI: the `Speech:` line and the no-speech block of `trec transcribe` (docs/tasks/speech-check/_tests.md
UT-060 to UT-062), the marker and the count of `trec status` (UT-063) and the `speech check:` line of `trec doctor` (UT-064).

The expected lines are written out here, character for character, from the frozen lines of `_dx.md`, so a wording change in
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
from teams_recorder.constants import Bin, Platform
from teams_recorder.config import load_settings
from teams_recorder.domain import (
    Analysis, Decision, LabelSummary, Meeting, Segment, SpeechActivity, SpeechCheck, Transcript, TranscriptHealth, TranscriptionError, Verification,
    VerificationStatus,
)
from teams_recorder.domain.status import AUDIO
from teams_recorder.messages import Cli, Log, Notify
from tests.fakes import FakeSpeechDetector, FakeTranscriber, speech_transcript

runner = CliRunner()
CONFIG_PT = '[transcription]\nlanguage = "pt"\n'   # a fixed language: no language detector in the container
SPEECH = SpeechActivity(3138.0, ((0.0, 2676.4),))
SILENT = SpeechActivity(309.6, ())


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: str = CONFIG_PT) -> FsMeetingRepository:
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "config.toml").write_text(config)
    return FsMeetingRepository(tmp_path / "data")


def _with_container(monkeypatch: pytest.MonkeyPatch, **fields) -> None:
    build = cli.build_container
    monkeypatch.setattr(cli, "build_container", lambda settings, **kw: replace(build(settings, **kw), **fields))


def _recorded(repo: FsMeetingRepository, stamp: datetime = datetime(2026, 10, 23, 14, 0, 5)) -> Meeting:
    meeting = Meeting.start(stamp)
    repo.create(meeting)
    repo.path(meeting.id, AUDIO).write_bytes(b"\x00")
    return meeting


def _lines(output: str, meeting: Meeting) -> list[str]:
    """The lines of one `trec transcribe` run, from `Transcribing <id>…` on."""
    lines = output.splitlines()
    return lines[next(i for i, line in enumerate(lines) if line.startswith(f"Transcribing {meeting.id}")):]


def test_ut060_a_recording_with_speech_prints_the_speech_line_right_after_ok_and_before_health(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _project(tmp_path, monkeypatch)
    meeting = _recorded(repo)
    transcriber = FakeTranscriber(speech_transcript(minutes=52))
    _with_container(monkeypatch, transcriber=transcriber, retry_transcriber=None, speech_detector=FakeSpeechDetector(SPEECH))

    result = runner.invoke(app, ["transcribe", meeting.id])

    assert result.exit_code == 0, result.output
    lines = _lines(result.output, meeting)
    assert lines[0].startswith(f"Transcribing {meeting.id}… ok (") and lines[0].endswith(" min)")
    assert lines[1] == "  Speech: 44.6 of 52.3 min (85%)"
    assert lines[2].startswith("  Health: ")
    assert [line.split(":")[0].strip() for line in lines[1:5]] == ["Speech", "Health", "Language", "Speakers"]
    assert repo.load_transcript(meeting.id).speech == SpeechCheck(True, 2676.4, 3138.0, 1)


def test_ut060_the_share_is_capped_at_100_percent_when_the_last_segment_ends_past_the_audio():
    """VAD segment ends can run a few centiseconds past the WAV (27.23 s against a 27.21 s file)."""
    line = cli._speech_line(Transcript([Segment(0, 1, "oi")], speech=SpeechCheck(True, 27.3, 27.2, 1)), True)
    assert line == "  Speech: 0.5 of 0.5 min (100%)"


def test_ut061_a_recording_with_no_speech_prints_the_no_speech_block_and_nothing_whisper_made(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    repo = _project(tmp_path, monkeypatch)
    meeting = _recorded(repo, datetime(2026, 10, 17, 10, 15, 32))
    transcriber, retry = FakeTranscriber(speech_transcript()), FakeTranscriber(speech_transcript())
    _with_container(monkeypatch, transcriber=transcriber, retry_transcriber=retry, speech_detector=FakeSpeechDetector(SILENT))

    result = runner.invoke(app, ["transcribe", meeting.id])

    assert result.exit_code == 0, result.output
    assert transcriber.calls == [] and retry.calls == []
    assert _lines(result.output, meeting) == [
        f"Transcribing {meeting.id}… ok (0 segments, 0.0 min)",
        "  Speech: none (0.0 s of speech in 5.2 min); whisper did not run",
        f"  WARNING: the transcript is empty. If this was a meeting, check the capture with `trec doctor`. To transcribe it anyway, "
        f"set [transcription] speech_check = false, run `trec transcribe {meeting.id}` and `trec analyze {meeting.id}`, then set it back to true.",
        f"  Text: {repo.path(meeting.id, 'transcript.txt')}",
        Cli.ANALYZE_HINT,
    ]
    assert not any(line.startswith(("  Health:", "  Language:", "  Speakers:")) for line in result.output.splitlines())
    (warning,) = [r for r in caplog.records if r.msg == Log.NO_SPEECH]   # stderr in a real run, as the language-detection warning
    assert warning.levelno == logging.WARNING and warning.getMessage() == Log.NO_SPEECH % (meeting.id, 0.0, 309.6 / 60, 2.0)
    saved = repo.load_transcript(meeting.id)
    assert saved.segments == [] and saved.speech == SpeechCheck(False, 0.0, 309.6, 0)


def test_ut061_the_headless_notifier_logs_the_notification_of_a_recording_of_a_minute_or_more(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    """A CLI run has no desktop notifier: the `LogNotifier` logs it at info level, which the CLI does not show."""
    caplog.set_level(logging.INFO)
    repo = _project(tmp_path, monkeypatch)
    meeting = _recorded(repo)
    _with_container(monkeypatch, transcriber=FakeTranscriber(), retry_transcriber=None, speech_detector=FakeSpeechDetector(SILENT))

    result = runner.invoke(app, ["transcribe", meeting.id])

    assert result.exit_code == 0, result.output
    body = Notify.NO_SPEECH_BODY.format(meeting_id=meeting.id, minutes=309.6 / 60)
    assert Log.LOG_NOTIFICATION % (Notify.NO_SPEECH, body) in caplog.messages
    assert Notify.NO_SPEECH not in result.output   # the CLI shows the WARNING line instead


def test_ut062_with_the_check_off_the_speech_line_names_the_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _project(tmp_path, monkeypatch, CONFIG_PT + "speech_check = false\n")
    meeting = _recorded(repo)
    _with_container(monkeypatch, transcriber=FakeTranscriber(speech_transcript(minutes=10)), retry_transcriber=None)

    result = runner.invoke(app, ["transcribe", meeting.id])

    assert result.exit_code == 0, result.output
    lines = _lines(result.output, meeting)
    assert lines[1] == "  Speech: not checked ([transcription] speech_check = false)" and lines[2].startswith("  Health: ")
    assert repo.load_transcript(meeting.id).speech is None


def test_ut062_a_check_that_failed_points_to_its_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    # The warning is asserted with caplog, as the language-detection one is: pytest's logging plugin captures the record, so it never
    # reaches the last-resort handler (stderr) here. That the handler prints it in a real run is stdlib behavior.
    repo = _project(tmp_path, monkeypatch)
    meeting = _recorded(repo, datetime(2026, 10, 21, 9, 30, 28))
    failure = TranscriptionError("whisper-vad-speech-segments: timed out after 300s")
    _with_container(monkeypatch, transcriber=FakeTranscriber(speech_transcript(minutes=38)), retry_transcriber=None,
                    speech_detector=FakeSpeechDetector(error=failure))
    caplog.set_level(logging.WARNING)

    result = runner.invoke(app, ["transcribe", meeting.id])

    assert result.exit_code == 0, result.output
    lines = _lines(result.output, meeting)
    assert lines[1] == "  Speech: not checked (the speech check failed; see the warning above)" and lines[2].startswith("  Health: ")
    (warning,) = [r for r in caplog.records if r.msg == Log.SPEECH_CHECK_FAILED]
    assert warning.levelno == logging.WARNING and warning.args is not None and warning.args == (meeting.id, failure)
    assert warning.getMessage() == f"speech check of {meeting.id} failed; transcribing without it: {failure}"
    assert repo.load_transcript(meeting.id).speech is None


# --- UT-063: the status marker and the count ---------------------------------------------------------------------------------
NO_SPEECH = SpeechCheck(False, 0.0, 309.6, 0)


def _saved(repo: FsMeetingRepository, minute: int, transcript: Transcript, title: str = "") -> str:
    meeting = Meeting.start(datetime(2026, 10, 17, 10, minute, 0), title=title)
    repo.create(meeting)
    repo.save_transcript(meeting.id, transcript)
    return meeting.id


def _status(runner_args: list[str] | None = None) -> list[str]:
    result = runner.invoke(app, runner_args or ["status"])
    assert result.exit_code == 0, result.output
    return result.output.splitlines()


def test_ut063_status_marks_each_recording_with_no_speech_and_counts_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _project(tmp_path, monkeypatch)
    _saved(repo, 0, Transcript([], "pt", speech=NO_SPEECH), "M0")
    _saved(repo, 10, Transcript([], "en", speech=NO_SPEECH), "M10")   # a fallback that is not Portuguese (US-006.EC-4): no `· en`
    _saved(repo, 20, Transcript([Segment(0, 1, "oi")], "pt", speech=SpeechCheck(True, 2676.4, 3138.0, 612)), "M20")
    _saved(repo, 30, Transcript([Segment(0, 1, "oi")], "pt"), "M30")   # made before the feature: no record

    lines = _status()

    assert "  2026-10-17_10-00-00 M0  [transcribed] → next: analyze  · no speech" in lines
    assert "  2026-10-17_10-10-00 M10  [transcribed] → next: analyze  · no speech" in lines   # and not `  · en  · no speech`
    assert "  2026-10-17_10-20-00 M20  [transcribed] → next: analyze" in lines   # speech found: no marker
    assert "  2026-10-17_10-30-00 M30  [transcribed] → next: analyze" in lines   # no record: no marker
    degraded, count, unconfirmed = (lines.index(line) for line in ("Degraded transcripts: 0", "Recordings without speech: 2",
                                                                    "Unconfirmed claims: 0 in 0 meeting(s)"))
    assert degraded < count < unconfirmed


def test_ut063_the_count_line_follows_the_rate_mismatch_line_and_precedes_the_unconfirmed_claims(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _project(tmp_path, monkeypatch)
    _saved(repo, 0, Transcript([], "pt", speech=NO_SPEECH))
    _saved(repo, 10, Transcript([Segment(0, 1, "oi")], "pt", TranscriptHealth(0.0, 30, 30, False, rate_mismatch=True, short_padding_share=0.6)))

    lines = _status()

    summary = [line for line in lines if line.startswith(("Degraded transcripts:", "Teams tracks recorded", "Recordings without speech:", "Unconfirmed claims:"))]
    assert summary == ["Degraded transcripts: 0", "Teams tracks recorded at the wrong sample rate: 1", "Recordings without speech: 1",
                       "Unconfirmed claims: 0 in 0 meeting(s)"]


def test_ut063_without_a_recording_with_no_speech_there_is_no_count_line_and_no_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _project(tmp_path, monkeypatch)
    _saved(repo, 0, Transcript([Segment(0, 1, "oi")], "en", speech=SpeechCheck(True, 2676.4, 3138.0, 612)), "M0")
    _saved(repo, 10, Transcript([Segment(0, 1, "oi")], "pt"), "M10")
    _saved(repo, 20, Transcript([Segment(0, 1, "oi")], "pt"), "M20")   # `speech_check = false` and a failed check both leave no record too

    output = "\n".join(_status())

    assert "Recordings without speech" not in output and "no speech" not in output
    assert "  2026-10-17_10-00-00 M0  [transcribed] → next: analyze  · en" in output   # the language marker of a meeting with speech is unchanged


def test_ut063_the_marker_comes_after_the_other_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No recording with no speech carries a speaker summary or health today, but the order is part of the contract: the marker is the last."""
    repo = _project(tmp_path, monkeypatch)
    meeting_id = _saved(repo, 0, Transcript([], "en", TranscriptHealth(0.668, 28, 86, True, ((0, 14),)), labels=LabelSummary(5, 10, None), speech=NO_SPEECH))
    repo.save_analysis(meeting_id, Analysis(meeting_id=meeting_id, summary="s", decisions=[Decision("A", verification=Verification(VerificationStatus.UNCONFIRMED, "no"))]))

    (line,) = [line for line in _status() if line.startswith(f"  {meeting_id}")]

    assert line == (f"  {meeting_id}  [analyzed]  · speakers 50%" + Cli.MEETING_DEGRADED.format(loop=0.668)
                    + Cli.MEETING_UNCONFIRMED.format(count=1) + "  · no speech")


# --- UT-064: the doctor line -------------------------------------------------------------------------------------------------
TOOL = f"/opt/homebrew/bin/{Bin.WHISPER_VAD}"
SPEECH_LINE_TAIL = "speech check: "


def _ready_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, tool: str | None, model: bool, config: str = "") -> Path:
    """A project where every other check of `trec doctor` passes (exit 0), so the speech line is all that varies. `tool` is where the
    speech check's tool is found (None: not found) and `model` whether the Silero model is in the models folder."""
    _project(tmp_path, monkeypatch, "[speakers]\nenabled = false\n" + config)
    monkeypatch.setenv("TREC_LLM_PROVIDER", "claude-code")
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cli, "_tool_path", lambda name, project_dir: tool if name == Bin.WHISPER_VAD else f"/usr/bin/{name}")
    monkeypatch.setattr(cli, "_teams_tap_path", lambda settings: "/usr/bin/teams-tap")
    models = tmp_path / "data" / "models"
    models.mkdir(parents=True)
    (models / "ggml-large-v3-turbo-q5_0.bin").write_bytes(b"\x00")
    if model:
        (models / "ggml-silero-v5.1.2.bin").write_bytes(b"\x00")
    guide = tmp_path / "prompts" / "user_story_guide.md"
    guide.parent.mkdir()
    guide.write_text("x")
    return models / "ggml-silero-v5.1.2.bin"


def _doctor() -> tuple[int, list[str]]:
    result = runner.invoke(app, ["doctor"])
    return result.exit_code, result.output.splitlines()


def _speech_check_line(lines: list[str]) -> str:
    (line,) = [line for line in lines if SPEECH_LINE_TAIL in line]
    return line


def test_ut064_tool_and_model_present_the_check_is_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _ready_project(tmp_path, monkeypatch, tool=TOOL, model=True)

    code, lines = _doctor()

    assert _speech_check_line(lines) == f"[ok ] speech check: on ({TOOL}); a recording with under 2 s of speech is not transcribed"
    assert code == 0


def test_ut064_a_missing_tool_warns_and_says_recordings_go_without_the_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _ready_project(tmp_path, monkeypatch, tool=None, model=True)

    code, lines = _doctor()

    assert _speech_check_line(lines) == "[WARNING] speech check: whisper-vad-speech-segments not found; recordings are transcribed without the check"
    assert code == 0


def test_ut064_a_missing_model_warns_with_the_download_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model = _ready_project(tmp_path, monkeypatch, tool=TOOL, model=False)

    code, lines = _doctor()

    assert _speech_check_line(lines) == (f"[WARNING] speech check: VAD model missing: {model}  → scripts/download-model.sh silero-v5.1.2 "
                                         "(until then recordings are transcribed without the check)")
    assert code == 0


def test_ut064_with_the_check_off_the_line_is_informational(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _ready_project(tmp_path, monkeypatch, tool=None, model=False, config="[transcription]\nspeech_check = false\n")   # nothing to find when it is off

    code, lines = _doctor()

    assert _speech_check_line(lines) == "[info] speech check: off ([transcription] speech_check = false)"
    assert code == 0


@pytest.mark.parametrize("tool, model, config", [
    (TOOL, True, ""), (None, True, ""), (TOOL, False, ""), (None, False, "[transcription]\nspeech_check = false\n"),
], ids=["on", "no-tool", "no-model", "off"])
def test_ut064_the_line_sits_between_the_retry_line_and_the_language_line_and_changes_nothing_else(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str | None, model: bool, config: str):
    _ready_project(tmp_path, monkeypatch, tool=tool, model=model, config=config)
    code, lines = _doctor()
    monkeypatch.setattr(cli, "_check_speech", lambda settings: None)   # the doctor with the line removed
    baseline_code, baseline = _doctor()

    retry = next(i for i, line in enumerate(lines) if "retry of a degraded transcript:" in line)
    assert SPEECH_LINE_TAIL in lines[retry + 1] and lines[retry + 2].startswith("[info] language:")
    assert [line for line in lines if SPEECH_LINE_TAIL not in line] == baseline   # no other line moved or changed
    assert code == baseline_code == 0


def test_ut064_on_a_bare_project_the_line_leaves_the_failing_exit_code_as_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Nothing is installed here, so the doctor fails on its own checks; the speech line (a warning, since its tool and model are missing) adds nothing."""
    _project(tmp_path, monkeypatch)
    code, lines = _doctor()
    monkeypatch.setattr(cli, "_check_speech", lambda settings: None)
    baseline_code, _ = _doctor()

    assert code == baseline_code == 1
    assert _speech_check_line(lines).startswith("[WARNING] speech check: ")


def test_ut064_on_windows_the_hint_names_the_powershell_download_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _ready_project(tmp_path, monkeypatch, tool=r"C:\trec\tools\whisper-vad-speech-segments.exe", model=False)
    windows = replace(load_settings(tmp_path), platform=Platform.WINDOWS)
    monkeypatch.setattr(cli, "_settings", lambda: windows)

    _, lines = _doctor()

    assert _speech_check_line(lines).endswith(r"→ scripts\download-model.ps1 silero-v5.1.2 (until then recordings are transcribed without the check)")

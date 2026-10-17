"""The speaker-label lines of `trec doctor`, `trec status` and `trec transcribe`: docs/tasks/speaker-attribution/_tests.md UT-061 to UT-065.

The expected texts are written out here, character for character, from the frozen lines of `_dx.md` (the reason table and the
doctor lines), so a wording change in messages.py fails these tests on purpose."""
from __future__ import annotations

import stat
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.inbound import cli
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.config import Settings, load_settings
from teams_recorder.constants import Files, Platform
from teams_recorder.domain import LabelSummary, Meeting, Segment, SpeakerReason, Transcript
from teams_recorder.messages import Cli, Err, Notify
from tests.fakes import FakeSpeakerObserver

BINARY = "native/teams-speakers/.build/release/teams-speakers"
LUCAS = "Lucas Huguenin Gurgel de Moura"
LAST = "2026-10-17_09-30-12"


def _project(tmp_path: Path, built: bool = True) -> Settings:
    if built:
        binary = tmp_path / Files.SPEAKERS_BINARY
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\n")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return load_settings(tmp_path)


def _transcribed(tmp_path: Path, meeting_id: str, labels: LabelSummary | None, speakers: tuple[str, ...] = ()) -> None:
    repo = FsMeetingRepository(tmp_path / "data")
    repo.create(Meeting.start(datetime.strptime(meeting_id, "%Y-%m-%d_%H-%M-%S")))
    segments = [Segment(float(i), i + 1.0, "oi", speaker) for i, speaker in enumerate(speakers)] or [Segment(0, 1, "oi")]
    repo.save_transcript(meeting_id, Transcript(segments, "pt", labels=labels))


def _doctor_line(settings: Settings, monkeypatch, capsys, observer: FakeSpeakerObserver | None) -> str:
    monkeypatch.setattr(cli, "build_speaker_observer", lambda s: observer)
    cli._check_speakers(settings)
    return capsys.readouterr().out


# --- UT-061: ready -----------------------------------------------------------------------------------------------------

def test_ut061_a_ready_helper_is_an_ok_line(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path)
    out = _doctor_line(settings, monkeypatch, capsys, FakeSpeakerObserver())
    assert out == f"[ok ] speaker labels: teams-speakers at {BINARY}; Accessibility permission granted\n"


def test_ut061_the_last_recording_is_appended_from_the_latest_transcript(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path)
    _transcribed(tmp_path, "2026-10-16_10-00-00", LabelSummary(0, 40, "no-window"))
    _transcribed(tmp_path, LAST, LabelSummary(167, 214, None), (LUCAS,))
    out = _doctor_line(settings, monkeypatch, capsys, FakeSpeakerObserver())
    assert out == (f"[ok ] speaker labels: teams-speakers at {BINARY}; Accessibility permission granted; "
                   f"last recording {LAST}: observer ran, 78% of lines labelled\n")


# --- UT-062: permission missing ---------------------------------------------------------------------------------------

def test_ut062_a_missing_permission_is_an_info_line_with_the_request_command(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path)
    absolute = tmp_path / Files.SPEAKERS_BINARY
    observer = FakeSpeakerObserver(problem_list=[Err.SPEAKERS_PROBLEM_PERMISSION.format(binary=absolute)])
    out = _doctor_line(settings, monkeypatch, capsys, observer)
    assert out == (f"[info] speaker labels: teams-speakers at {BINARY}; Accessibility permission missing → run `{BINARY} --check --prompt` "
                   f"and allow teams-speakers (add it with the + button: {BINARY}) under System Settings > Privacy & Security > Accessibility\n")
    assert str(tmp_path) not in out   # the project path is relativized


def test_ut062_a_check_that_could_not_run_is_an_info_line(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path)

    class Broken(FakeSpeakerObserver):
        def problems(self) -> list[str]:
            raise OSError("launchctl: not found")

    out = _doctor_line(settings, monkeypatch, capsys, Broken())
    assert out == (f"[info] speaker labels: teams-speakers at {BINARY}; "
                   "the Accessibility permission could not be checked: launchctl: not found\n")


def test_ut062_the_check_runs_once(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path)

    class Counting(FakeSpeakerObserver):
        calls = 0

        def problems(self) -> list[str]:
            Counting.calls += 1
            return []

    _doctor_line(settings, monkeypatch, capsys, Counting())
    assert Counting.calls == 1


# --- UT-063: not built, off -------------------------------------------------------------------------------------------

def test_ut063_a_helper_that_is_not_built_is_an_info_line(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path, built=False)
    observer = FakeSpeakerObserver(problem_list=[Err.SPEAKERS_PROBLEM_NOT_BUILT.format(script=Files.BUILD_NATIVE_SCRIPT)])
    out = _doctor_line(settings, monkeypatch, capsys, observer)
    assert out == "[info] speaker labels: teams-speakers not built → scripts/build-native.sh\n"


def test_ut063_the_feature_off_is_an_info_line_and_starts_no_check(tmp_path: Path, capsys):
    (tmp_path / "config.toml").write_text("[speakers]\nenabled = false\n")
    cli._check_speakers(load_settings(tmp_path))   # the real builder: no observer, so no launchctl
    assert capsys.readouterr().out == ("[info] speaker labels: off ([speakers] enabled = false); "
                                       "only your own lines are labelled, from the microphone track\n")


def test_ut063_no_line_on_windows(tmp_path: Path, monkeypatch, capsys):
    settings = load_settings(tmp_path, platform=Platform.WINDOWS)
    assert _doctor_line(settings, monkeypatch, capsys, FakeSpeakerObserver()) == ""


# --- UT-064: status and transcribe ------------------------------------------------------------------------------------

REASON_TABLE = [
    ("binary-missing", "Speakers: no labels (the observer did not run: teams-speakers not built)"),
    ("permission-missing", "Speakers: no labels (the observer did not run: Accessibility permission missing)"),
    ("start-failed", "Speakers: no labels (the observer did not run: it failed to start; see data/log/speakers.log)"),
    ("observer-died", "Speakers: no labels (the observer died before reading a Teams window; see data/log/speakers.log)"),
    ("no-window", "Speakers: no labels (no Teams meeting window was read during the call)"),
    ("no-match", "Speakers: no labels (speaker events found but no line matched them)"),
    ("no-observer", "Speakers: no labels (no observer data for this meeting)"),
]


def test_ut064_the_seven_reasons_are_the_table_of_the_dx_contract():
    assert [r.value for r in SpeakerReason] == [reason for reason, _ in REASON_TABLE]
    for reason, line in REASON_TABLE:
        assert cli._speakers_line(Transcript([Segment(0, 1, "oi")], labels=LabelSummary(0, 3, reason))) == "  " + line


def test_ut064_the_notice_and_the_cli_share_the_wording_where_they_coincide():
    for reason in ("no-window", "observer-died"):
        assert Notify.NO_SPEAKER_LABELS_REASON[reason].startswith(Cli.SPEAKERS_REASON[reason].split(";")[0])


def test_ut064_the_transcribe_line_names_the_share_the_lines_and_the_speakers():
    segments = [Segment(0, 1, "a", "Felipe"), Segment(1, 2, "b", LUCAS), Segment(2, 3, "c", "Felipe"), Segment(3, 4, "d")]
    transcript = Transcript(segments, labels=LabelSummary(167, 214, None))
    assert cli._speakers_line(transcript) == f"  Speakers: 78% of 214 lines labelled (Felipe, {LUCAS})"


def test_ut064_a_transcript_without_a_summary_prints_no_speakers_line():
    assert cli._speakers_line(Transcript([Segment(0, 1, "oi")])) is None


def test_ut064_the_status_segment():
    assert cli._speakers_segment(LabelSummary(167, 214, None)) == "  · speakers 78%"
    assert cli._speakers_segment(LabelSummary(0, 214, "no-window")) == "  · speakers 0% (no Teams meeting window was read during the call)"
    assert cli._speakers_segment(LabelSummary(0, 214, "permission-missing")) == (
        "  · speakers 0% (the observer did not run: Accessibility permission missing)")
    assert cli._speakers_segment(LabelSummary(0, 0, "no-match")) == "  · speakers 0% (speaker events found but no line matched them)"


def test_ut064_no_status_segment_for_old_transcripts_nor_for_meetings_without_observer_data():
    assert cli._speakers_segment(None) == ""                                      # made before the feature
    assert cli._speakers_segment(LabelSummary(0, 214, "no-observer")) == ""       # feature off, Windows, no observer data
    assert cli._speakers_segment(LabelSummary(0, 214, None)) == ""                # a summary without a reason counts as no observer data


# --- UT-065: the last recording and the mismatch ----------------------------------------------------------------------

@pytest.mark.parametrize("labels, outcome", [
    (LabelSummary(167, 214, None), "observer ran, 78% of lines labelled"),
    (LabelSummary(0, 214, "no-window"), "no Teams meeting window was read during the call"),
    (LabelSummary(0, 214, "no-match"), "speaker events found but no line matched them"),
    (LabelSummary(0, 214, "start-failed"), "the observer did not run: it failed to start; see data/log/speakers.log"),
    (LabelSummary(0, 214, "no-observer"), "no observer data for this meeting"),
])
def test_ut065_the_last_recordings_outcome_follows_its_summary(tmp_path: Path, monkeypatch, capsys, labels, outcome):
    settings = _project(tmp_path)
    _transcribed(tmp_path, LAST, labels, (LUCAS,) if labels.labelled else ())
    out = _doctor_line(settings, monkeypatch, capsys, FakeSpeakerObserver())
    assert out == f"[ok ] speaker labels: teams-speakers at {BINARY}; Accessibility permission granted; last recording {LAST}: {outcome}\n"


def test_ut065_a_transcript_without_a_summary_adds_no_clause(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path)
    _transcribed(tmp_path, LAST, None)
    out = _doctor_line(settings, monkeypatch, capsys, FakeSpeakerObserver())
    assert out == f"[ok ] speaker labels: teams-speakers at {BINARY}; Accessibility permission granted\n"


def test_ut065_a_granted_check_after_a_recording_that_reported_it_missing_is_a_warning(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path)
    _transcribed(tmp_path, LAST, LabelSummary(0, 214, "permission-missing"))
    out = _doctor_line(settings, monkeypatch, capsys, FakeSpeakerObserver())
    assert out == (f"[WARNING] speaker labels: Accessibility permission granted to teams-speakers now, but the last recording {LAST} "
                   "reported it missing → record again to confirm; if it still reports it missing, add teams-speakers again "
                   f"(add it with the + button: {BINARY})\n")


def test_ut065_no_warning_while_the_check_itself_reports_the_permission_missing(tmp_path: Path, monkeypatch, capsys):
    settings = _project(tmp_path)
    _transcribed(tmp_path, LAST, LabelSummary(0, 214, "permission-missing"))
    observer = FakeSpeakerObserver(problem_list=[Err.SPEAKERS_PROBLEM_PERMISSION.format(binary=tmp_path / Files.SPEAKERS_BINARY)])
    out = _doctor_line(settings, monkeypatch, capsys, observer)
    assert out.startswith("[info] speaker labels: teams-speakers at ") and "WARNING" not in out

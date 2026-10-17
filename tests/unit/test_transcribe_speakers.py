"""Labelling at transcription and the daily notice: docs/tasks/speaker-attribution/_tests.md UT-040 to UT-047."""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from teams_recorder.application.use_cases import TranscribeMeeting
from teams_recorder.constants import Speakers
from teams_recorder.domain import EnergyTimeline, RepositoryError, Segment, SpeakerLog, SpeakerReason, SpeakerTurn, Transcript
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK
from teams_recorder.messages import Log, Minutes, Notify
from tests.fakes import FakeNotifier, FakeTranscriber

LUCAS = "Lucas Huguenin Gurgel de Moura"
SEGMENTS = [Segment(30.0, 40.0, "então eu subo o ambiente"), Segment(50.0, 60.0, "pode deixar comigo o relatório"),
            Segment(70.0, 80.0, "a gente combina depois")]


def _flat(level: float, seconds: float = 100.0) -> EnergyTimeline:
    return EnergyTimeline(0.1, tuple([level] * int(seconds * 10)))


def _user_energy() -> dict[str, EnergyTimeline]:
    """The microphone far louder than the Teams track over the second line only."""
    mic = [-60.0] * 1000
    mic[500:600] = [-30.0] * 100
    return {MIC_TRACK: EnergyTimeline(0.1, tuple(mic)), TAP_TRACK: _flat(-60.0)}


def _run(repo, meeting, clock, notifier=None, user_name="", with_clock=True, log=None, energy=None, seeded=True):
    repo.seed(meeting, {AUDIO})
    if seeded:
        repo.seed_speakers(meeting.id, log, energy)
    use_case = TranscribeMeeting(repo, FakeTranscriber(Transcript(segments=list(SEGMENTS))), "pt", notifier=notifier,
                                 clock=clock if with_clock else None, user_name=user_name)
    return use_case.execute(meeting.id)


def _unlabelled(reason: str | None) -> SpeakerLog:
    return SpeakerLog(unavailable=reason) if reason else SpeakerLog(roster=(LUCAS,), ended=True)


def test_ut040_a_labelling_failure_keeps_the_transcript(repo, meeting, clock, caplog):
    class Broken(type(repo)):
        def load_speaker_log(self, meeting_id, fallback_epoch, end):
            raise RepositoryError("speakers.jsonl unreadable")

    broken = Broken()
    broken.seed(meeting, {AUDIO})
    with caplog.at_level(logging.WARNING):
        result = TranscribeMeeting(broken, FakeTranscriber(Transcript(segments=list(SEGMENTS))), "pt", clock=clock).execute(meeting.id)
    saved = broken.load_transcript(meeting.id)
    assert saved is result and saved.labels is None and [s.speaker for s in saved.segments] == [None, None, None]
    assert Log.SPEAKERS_LABEL_FAILED % (meeting.id, "speakers.jsonl unreadable") in caplog.messages


@pytest.mark.parametrize("error", [ZeroDivisionError("division by zero"), OverflowError("Result too large"), RuntimeError("boom"), KeyError("x")])
def test_ut040_any_error_while_labelling_keeps_the_whisper_transcript(repo, meeting, clock, caplog, monkeypatch, error):
    """Review round 2, issue 002: only three exception types were caught, and the label step runs before the transcript is saved."""
    def explode(*args, **kwargs):
        raise error

    monkeypatch.setattr("teams_recorder.application.use_cases.processing.label_segments", explode)
    repo.seed(meeting, {AUDIO})
    repo.seed_speakers(meeting.id, SpeakerLog(roster=(LUCAS,), ended=True), _user_energy())
    with caplog.at_level(logging.WARNING):
        result = TranscribeMeeting(repo, FakeTranscriber(Transcript(segments=list(SEGMENTS))), "pt", clock=clock).execute(meeting.id)

    saved = repo.load_transcript(meeting.id)
    assert saved is result and saved.labels is None and [s.speaker for s in saved.segments] == [None, None, None]
    assert [s.text for s in saved.segments] == [s.text for s in SEGMENTS]
    assert Log.SPEAKERS_LABEL_FAILED % (meeting.id, error) in caplog.messages


@pytest.mark.parametrize("damaged", [
    {"step_seconds": 0, "tracks": {"mic.wav": [-30.0] * 1000, "tap.wav": [-60.0] * 1000}},
    {"step_seconds": 0.1, "tracks": {"mic.wav": [1e5] * 1000, "tap.wav": [-60.0] * 1000}},
])
def test_a_damaged_energy_file_on_disk_costs_the_labels_not_the_transcript(tmp_path, meeting, clock, caplog, damaged):
    """The two inputs of the issue, through the real repository and codec."""
    import json
    from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
    from teams_recorder.domain.status import ENERGY

    fs = FsMeetingRepository(tmp_path)
    fs.create(meeting)
    (tmp_path / "recordings" / meeting.id / AUDIO).write_bytes(b"audio")
    (tmp_path / "recordings" / meeting.id / ENERGY).write_text(json.dumps(damaged))
    with caplog.at_level(logging.WARNING):
        TranscribeMeeting(fs, FakeTranscriber(Transcript(segments=list(SEGMENTS))), "pt", clock=clock).execute(meeting.id)

    saved = fs.load_transcript(meeting.id)
    assert [s.text for s in saved.segments] == [s.text for s in SEGMENTS] and saved.labels is None
    assert any("could not be computed" in m and ENERGY in m for m in caplog.messages)


def test_a_timeline_with_a_zero_step_labels_nobody_instead_of_dividing_by_zero():
    from teams_recorder.domain import label_segments

    broken = EnergyTimeline(0.0, (-30.0,) * 10)
    labelled = label_segments(Transcript(segments=list(SEGMENTS)), SpeakerLog(roster=(LUCAS,), ended=True), broken, broken, "Felipe")
    assert [s.speaker for s in labelled.segments] == [None, None, None]


def test_ut041_turns_and_energy_label_the_lines_and_the_log_reports_them(repo, meeting, clock, caplog):
    log = SpeakerLog(turns=(SpeakerTurn(31.0, 39.0, LUCAS),), roster=("Felipe Mateus de Carvalho", LUCAS), me="Felipe Mateus de Carvalho", ended=True)
    with caplog.at_level(logging.INFO):
        _run(repo, meeting, clock, log=log, energy=_user_energy())
    saved = repo.load_transcript(meeting.id)
    assert [s.speaker for s in saved.segments] == [LUCAS, "Felipe Mateus de Carvalho", None]   # the user's tile name, none configured
    assert saved.labels is not None and (saved.labels.labelled, saved.labels.eligible, saved.labels.reason) == (2, 3, None)
    assert Log.SPEAKERS_LABELLED % (meeting.id, 2, 3, f"{LUCAS}, Felipe Mateus de Carvalho") in caplog.messages
    started, end = repo.speaker_log_calls[0][1:]
    assert started == meeting.started_at.timestamp() and end == 80.0   # no duration yet: the last segment's end


def test_the_configured_name_and_then_the_fallback_label_the_user(repo, meeting, clock):
    _run(repo, meeting, clock, user_name="Felipe", log=_unlabelled(None), energy=_user_energy())
    assert repo.load_transcript(meeting.id).segments[1].speaker == "Felipe"
    other = type(meeting).start(meeting.started_at + timedelta(hours=1), pid=1)
    _run(repo, other, clock, log=_unlabelled(None), energy=_user_energy())
    assert repo.load_transcript(other.id).segments[1].speaker == Minutes.SPEAKER_USER_FALLBACK


def test_relabelling_the_same_meeting_gives_identical_labels(repo, meeting, clock):
    log = SpeakerLog(turns=(SpeakerTurn(31.0, 39.0, LUCAS),), roster=(LUCAS,), ended=True)
    first = _run(repo, meeting, clock, log=log, energy=_user_energy())
    second = TranscribeMeeting(repo, FakeTranscriber(Transcript(segments=list(SEGMENTS))), "pt", clock=clock).execute(meeting.id)
    assert [s.speaker for s in first.segments] == [s.speaker for s in second.segments] and first.labels == second.labels


def test_a_meeting_without_observer_data_transcribes_as_before_and_stays_silent(repo, meeting, clock, notifier, caplog):
    with caplog.at_level(logging.WARNING):
        result = _run(repo, meeting, clock, notifier)
    assert [s.speaker for s in result.segments] == [None, None, None]
    assert result.labels is not None and result.labels.reason == SpeakerReason.NO_OBSERVER.value
    assert notifier.messages == [] and Speakers.NOTICE_KEY not in repo.notice_days
    assert not [m for m in caplog.messages if "speaker" in m]


def test_ut042_the_first_meeting_of_the_day_notifies_with_the_reason(repo, meeting, clock, notifier):
    _run(repo, meeting, clock, notifier, log=_unlabelled("permission-missing"))
    assert notifier.messages == [(Notify.NO_SPEAKER_LABELS, Notify.NO_SPEAKER_LABELS_BODY.format(
        meeting_id=meeting.id, reason=Notify.NO_SPEAKER_LABELS_REASON["permission-missing"]))]
    assert repo.notice_days[Speakers.NOTICE_KEY] == clock.now().date()


def test_ut043_one_notification_per_transcription_day(repo, meeting, clock, notifier, caplog):
    repo.notice_days[Speakers.NOTICE_KEY] = clock.now().date()
    with caplog.at_level(logging.WARNING):
        _run(repo, meeting, clock, notifier, log=_unlabelled("start-failed"))
    assert notifier.messages == [] and Log.NO_SPEAKER_LABELS % (meeting.id, "start-failed") in caplog.messages
    repo.notice_days[Speakers.NOTICE_KEY] = clock.now().date() - timedelta(days=1)   # the day is the transcription's, not the meeting's
    _run(repo, meeting, clock, notifier, log=_unlabelled("start-failed"))
    assert len(notifier.messages) == 1 and repo.notice_days[Speakers.NOTICE_KEY] == clock.now().date()


def test_ut044_an_unreadable_marker_counts_as_absent_and_is_rewritten(tmp_path, meeting, clock, notifier):
    from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository

    fs = FsMeetingRepository(tmp_path)
    fs.create(meeting)
    (tmp_path / "recordings" / meeting.id / AUDIO).write_bytes(b"audio")
    (tmp_path / "notices").mkdir()
    (tmp_path / "notices" / Speakers.NOTICE_KEY).write_text("garbage")
    fs.write_speakers_unavailable(meeting.id, "binary-missing")
    TranscribeMeeting(fs, FakeTranscriber(Transcript(segments=list(SEGMENTS))), "pt", notifier=notifier, clock=clock).execute(meeting.id)
    assert len(notifier.messages) == 1 and fs.last_notice_day(Speakers.NOTICE_KEY) == clock.now().date()


def test_ut045_a_transcript_with_labels_raises_no_notice(repo, meeting, clock, notifier):
    log = SpeakerLog(turns=(SpeakerTurn(31.0, 39.0, LUCAS),), roster=(LUCAS,), ended=True)
    _run(repo, meeting, clock, notifier, log=log)
    assert notifier.messages == [] and Speakers.NOTICE_KEY not in repo.notice_days


@pytest.mark.parametrize("reason", ["binary-missing", "permission-missing", "start-failed", "observer-died", "no-window"])
def test_ut046_every_notifying_reason_sends_its_own_body(repo, meeting, clock, notifier, reason):
    log = _unlabelled(reason) if reason in ("binary-missing", "permission-missing", "start-failed") else SpeakerLog(ended=reason == "no-window")
    _run(repo, meeting, clock, notifier, log=log)
    assert notifier.messages == [(Notify.NO_SPEAKER_LABELS, Notify.NO_SPEAKER_LABELS_BODY.format(
        meeting_id=meeting.id, reason=Notify.NO_SPEAKER_LABELS_REASON[reason]))]


def test_ut046_no_match_only_logs_and_no_observer_stays_silent(repo, meeting, clock, notifier, caplog):
    with caplog.at_level(logging.WARNING):
        _run(repo, meeting, clock, notifier, log=_unlabelled(None))   # tiles read, no line matched
    assert notifier.messages == [] and Speakers.NOTICE_KEY not in repo.notice_days
    assert Log.NO_SPEAKER_LABELS % (meeting.id, "no-match") in caplog.messages


def test_every_notifying_reason_has_a_notification_body():
    assert {r.value for r in SpeakerReason if r.notifies} == set(Notify.NO_SPEAKER_LABELS_REASON)


def test_ut047_without_a_clock_no_notice_is_raised(repo, meeting, clock, notifier):
    _run(repo, meeting, clock, notifier, log=_unlabelled("permission-missing"), with_clock=False)
    assert notifier.messages == [] and repo.notice_days == {}

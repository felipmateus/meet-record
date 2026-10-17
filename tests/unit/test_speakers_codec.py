"""Speaker attribution files (codec and repository): docs/tasks/speaker-attribution/_tests.md UT-020 to UT-027,
plus the repository methods and the active-recording pointer of task 1."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.application.ports import ActiveRecording, CaptureHandle
from teams_recorder.constants import Speakers
from teams_recorder.domain import (
    EnergyTimeline, LabelSummary, Meeting, RepositoryError, Segment, SpeakerLog, SpeakerTurn, Transcript, label_segments,
)
from teams_recorder.domain.status import ENERGY, SPEAKERS

LUCAS, FELIPE = "Lucas Huguenin Gurgel de Moura", "Felipe Mateus de Carvalho"
TITLE = "Planejamento da sprint | RADIX ENGENHARIA E DESENVOLVIMENTO DE SOFTWARE S/A | felipe.mateus@radixeng.com | Microsoft Teams"

DX_EXAMPLE = [  # docs/tasks/speaker-attribution/_dx.md › Files
    {"t": 1760655012.418, "event": "start", "epoch": 1760655010.000, "interval": 0.5, "teams_pid": 15347, "version": 1},
    {"t": 1760655012.931, "event": "window", "kind": "main", "state": "found", "title": TITLE},
    {"t": 1760655012.931, "event": "title", "subject": "Planejamento da sprint"},
    {"t": 1760655012.931, "event": "seen", "name": FELIPE, "me": True, "window": "main"},
    {"t": 1760655012.931, "event": "seen", "name": LUCAS, "me": False, "window": "main"},
    {"t": 1760655201.104, "event": "speaking", "name": LUCAS, "speaking": True, "window": "main"},
    {"t": 1760655209.620, "event": "speaking", "name": LUCAS, "speaking": False, "window": "main"},
    {"t": 1760655340.207, "event": "window", "kind": "main", "state": "lost", "title": TITLE},
    {"t": 1760655340.207, "event": "window", "kind": "compact", "state": "found", "title": "Modo de exibição compacto da reunião | " + TITLE},
    {"t": 1760657530.512, "event": "stop", "reason": "signal", "passes": 5021, "transitions": 388, "ax_errors": 0, "slow_passes": 3},
]


def _lines(records: list[dict]) -> list[str]:
    return [json.dumps(r) for r in records]


def test_ut020_the_dx_example_parses_with_times_from_the_start_event():
    log = codec.speaker_log_from_lines(_lines(DX_EXAMPLE), fallback_epoch=1000.0, end=2600.0)
    (turn,) = log.turns
    assert turn.name == LUCAS and abs(turn.start - 191.104) < 1e-6 and abs(turn.end - 199.620) < 1e-6
    assert log.roster == (FELIPE, LUCAS) and log.me == FELIPE
    assert log.subject == "Planejamento da sprint" and log.ended is True and log.unavailable is None and log.skipped == 0


def test_ut021_transcripts_round_trip_and_old_files_stay_as_they_were():
    old = {"language": "pt", "health": None, "segments": [{"start": 0.0, "end": 2.0, "text": "Olá"}]}
    loaded = codec.transcript_from_dict(old)
    assert loaded.segments == [Segment(0.0, 2.0, "Olá")] and loaded.labels is None and loaded.roster == () and loaded.user_label is None
    assert codec.transcript_to_dict(loaded) == old   # no speaker key, no speakers summary
    labelled = Transcript(segments=[Segment(0.0, 2.0, "Olá", LUCAS), Segment(2.0, 3.0, "sim")], roster=(FELIPE, LUCAS),
                          user_label="Felipe", labels=LabelSummary(1, 2, None))
    data = codec.transcript_to_dict(labelled)
    assert data["segments"] == [{"start": 0.0, "end": 2.0, "text": "Olá", "speaker": LUCAS}, {"start": 2.0, "end": 3.0, "text": "sim"}]
    assert data["speakers"] == {"roster": [FELIPE, LUCAS], "user_label": "Felipe", "labelled": 1, "eligible": 2, "reason": None}
    assert codec.transcript_from_dict(json.loads(json.dumps(data))) == labelled


def test_ut022_malformed_lines_are_skipped_and_counted():
    lines = ["not json", json.dumps({"t": 1.0, "event": "teleport"}), json.dumps([1, 2]), *_lines(DX_EXAMPLE), ""]
    log = codec.speaker_log_from_lines(lines, fallback_epoch=1000.0, end=2600.0)
    assert log.skipped == 3 and log.roster == (FELIPE, LUCAS) and len(log.turns) == 1


def test_ut023_an_unavailable_line_wins():
    only = codec.speakers_unavailable_line("permission-missing", 1760655012.418)
    log = codec.speaker_log_from_lines([only], fallback_epoch=0.0, end=10.0)
    assert (log.turns, log.roster, log.me, log.subject, log.ended, log.unavailable) == ((), (), None, None, False, "permission-missing")
    mixed = codec.speaker_log_from_lines([only.strip(), *_lines(DX_EXAMPLE[:5])], fallback_epoch=0.0, end=10.0)
    assert mixed.unavailable == "permission-missing" and mixed.roster == ()


def test_ut024_the_subject_comes_from_either_window_and_the_first_wins():
    compact = [{"t": 5.0, "event": "window", "kind": "compact", "state": "found", "title": "Modo de exibição compacto da reunião | Daily | X"},
               {"t": 6.0, "event": "window", "kind": "main", "state": "found", "title": "Outra | X"}]
    assert codec.speaker_log_from_lines(_lines(compact), 0.0, 10.0).subject == "Daily"
    main = [{"t": 5.0, "event": "window", "kind": "main", "state": "found", "title": "Daily | X"},
            {"t": 6.0, "event": "title", "subject": "Mudou depois"}]
    assert codec.speaker_log_from_lines(_lines(main), 0.0, 10.0).subject == "Daily"


def test_ut025_energy_round_trips_with_the_silence_floor():
    energy = {"tap.wav": EnergyTimeline(0.1, (-120.0, -61.2, -31.4)), "mic.wav": EnergyTimeline(0.1, (-120.0, -70.3, -38.2))}
    data = codec.energy_to_dict(energy)
    assert data == {"step_seconds": 0.1, "tracks": {"tap.wav": [-120.0, -61.2, -31.4], "mic.wav": [-120.0, -70.3, -38.2]}}
    assert codec.energy_from_dict(json.loads(json.dumps(data))) == energy


def test_ut026_an_energy_file_of_the_wrong_shape_is_a_repository_error(tmp_path: Path):
    repo, meeting = _repo_with_meeting(tmp_path)
    (tmp_path / "recordings" / meeting.id / ENERGY).write_text(json.dumps({"step_seconds": 0.1, "tracks": {"tap.wav": "loud"}}))
    with pytest.raises(RepositoryError, match=ENERGY):
        repo.load_energy(meeting.id)


def test_ut027_without_a_start_event_times_use_the_fallback_and_without_stop_it_did_not_end():
    records = [r for r in DX_EXAMPLE if r["event"] not in ("start", "stop")]
    log = codec.speaker_log_from_lines(_lines(records), fallback_epoch=1760655000.0, end=2600.0)
    assert abs(log.turns[0].start - 201.104) < 1e-6 and log.ended is False


T0 = 1760655000.0   # the epoch of the logs below


def _log_of(*records: dict, end: float = 3600.0) -> SpeakerLog:
    return codec.speaker_log_from_lines(_lines([{"t": T0, "event": "start", "epoch": T0, "version": 1}, *records]), T0, end)


def test_ut028_a_helper_that_died_credits_nobody_with_the_lines_after_its_last_sign_of_life():
    """Review round 2, issue 001: the turn stayed open to the meeting's end and swallowed the user's own lines."""
    beats = [{"t": T0 + at, "event": "heartbeat"} for at in (5, 10, 15, 20, 25, 30, 35, 40)]
    log = _log_of({"t": T0 + 10, "event": "seen", "name": "Lucas", "me": False, "window": "main"},
                  {"t": T0 + 12, "event": "speaking", "name": "Lucas", "speaking": True, "window": "main"}, *beats)

    assert log.turns == (SpeakerTurn(12.0, 40.0, "Lucas"),) and log.ended is False   # the meeting lasted 3600 s

    transcript = Transcript(segments=[Segment(30.0, 36.0, "ainda ele fala"), Segment(300.0, 306.0, "eu faço o deploy amanhã"),
                                      Segment(3500.0, 3506.0, "e depois eu reviso")])
    mic = EnergyTimeline(0.1, tuple([-30.0] * 36000))
    tap = EnergyTimeline(0.1, tuple([-70.0] * 36000))
    labelled = label_segments(transcript, log, mic, tap, "Felipe")
    assert [s.speaker for s in labelled.segments] == ["Lucas", "Felipe", "Felipe"]


def test_ut028_the_last_event_of_any_kind_bounds_an_open_turn():
    turn = {"t": T0 + 12, "event": "speaking", "name": "Lucas", "speaking": True, "window": "main"}
    assert _log_of(turn, {"t": T0 + 20, "event": "stop", "reason": "signal"}).turns == (SpeakerTurn(12.0, 20.0, "Lucas"),)
    assert _log_of(turn, {"t": T0 + 33, "event": "seen", "name": "Ana", "me": False, "window": "main"}).turns == (SpeakerTurn(12.0, 33.0, "Lucas"),)
    assert _log_of(turn).turns == ()                      # nothing after the turn opened: a zero-length turn is no turn
    # a line that is not an event (garbage) is no sign of life
    garbage = codec.speaker_log_from_lines([*_lines([{"t": T0, "event": "start", "epoch": T0}, turn]), "not json at 9999"], T0, 3600.0)
    assert garbage.turns == ()


def test_heartbeats_are_not_counted_as_skipped_lines():
    log = _log_of({"t": T0 + 5, "event": "heartbeat"}, {"t": T0 + 10, "event": "heartbeat"})
    assert log.skipped == 0


def test_ut029_a_frozen_window_closes_its_open_turns_like_a_lost_one_and_a_found_after_it_reopens_nothing():
    speaking = {"t": T0 + 12, "event": "speaking", "name": "Lucas", "speaking": True, "window": "main"}
    frozen = {"t": T0 + 20, "event": "window", "kind": "main", "state": "frozen", "title": TITLE}
    found = {"t": T0 + 50, "event": "window", "kind": "main", "state": "found", "title": TITLE}
    lost = {"t": T0 + 20, "event": "window", "kind": "main", "state": "lost", "title": TITLE}
    stop = {"t": T0 + 90, "event": "stop", "reason": "signal"}

    assert _log_of(speaking, frozen, found, stop).turns == (SpeakerTurn(12.0, 20.0, "Lucas"),)   # nothing reopened by the found
    assert _log_of(speaking, frozen, found, stop).turns == _log_of(speaking, lost, found, stop).turns
    reopened = {"t": T0 + 55, "event": "speaking", "name": "Lucas", "speaking": True, "window": "main"}
    assert _log_of(speaking, frozen, found, reopened, stop).turns == (SpeakerTurn(12.0, 20.0, "Lucas"), SpeakerTurn(55.0, 90.0, "Lucas"))


def test_ut029_a_frozen_compact_window_leaves_the_main_windows_turns_open():
    main = {"t": T0 + 10, "event": "speaking", "name": "Lucas", "speaking": True, "window": "main"}
    compact = {"t": T0 + 11, "event": "speaking", "name": "Ana", "speaking": True, "window": "compact"}
    frozen = {"t": T0 + 20, "event": "window", "kind": "compact", "state": "frozen", "title": "Modo de exibição compacto da reunião | X"}
    stop = {"t": T0 + 40, "event": "stop", "reason": "signal"}
    assert _log_of(main, compact, frozen, stop).turns == (SpeakerTurn(10.0, 40.0, "Lucas"), SpeakerTurn(11.0, 20.0, "Ana"))


def test_a_frozen_event_does_not_set_the_subject_a_found_one_does():
    frozen = {"t": T0 + 5, "event": "window", "kind": "main", "state": "frozen", "title": "Daily | X"}
    assert _log_of(frozen).subject is None
    found = {"t": T0 + 6, "event": "window", "kind": "main", "state": "found", "title": "Daily | X"}
    assert _log_of(found).subject == "Daily"


@pytest.mark.parametrize("record", [
    {"t": 10 ** 400, "event": "speaking", "name": "Lucas", "speaking": True, "window": "main"},   # an integer no float can hold
    {"t": float("inf"), "event": "heartbeat"},
    {"t": float("nan"), "event": "heartbeat"},
    {"t": True, "event": "heartbeat"},
])
def test_an_event_time_no_float_can_hold_is_a_skipped_line_not_an_overflow(record):
    line = json.dumps(record)   # json writes Infinity / NaN, which Python reads back
    log = codec.speaker_log_from_lines([json.dumps({"t": T0, "event": "start", "epoch": T0}), line], T0, 3600.0)
    assert log.skipped == 1 and log.turns == ()


def test_a_start_epoch_no_float_can_hold_falls_back_to_the_meeting_start():
    huge = json.dumps({"t": T0, "event": "start", "epoch": 10 ** 400})
    speaking = json.dumps({"t": T0 + 10, "event": "speaking", "name": "Lucas", "speaking": True, "window": "main"})
    stop = json.dumps({"t": T0 + 20, "event": "stop"})
    assert codec.speaker_log_from_lines([huge, speaking, stop], T0, 3600.0).turns == (SpeakerTurn(10.0, 20.0, "Lucas"),)


@pytest.mark.parametrize("step", [0, 0.0, -0.1, float("inf"), float("nan"), 10 ** 400, True, "0.1"])
def test_energy_with_a_step_that_is_not_a_positive_number_is_rejected(step):
    """Review round 2, issue 002: step 0 reached label_segments and raised ZeroDivisionError."""
    with pytest.raises(ValueError, match="step"):
        codec.energy_from_dict({"step_seconds": step, "tracks": {"tap.wav": [-30.0]}})


@pytest.mark.parametrize("level", [1e5, 10 ** 400, float("nan"), float("inf"), Speakers.MAX_LEVEL_DB + 1])
def test_energy_levels_that_overflow_or_are_not_numbers_are_rejected(level):
    with pytest.raises(ValueError, match="tap.wav"):
        codec.energy_from_dict({"step_seconds": 0.1, "tracks": {"tap.wav": [-30.0, level]}})


def test_energy_levels_below_the_floor_and_minus_infinity_read_as_silence_and_the_ceiling_is_allowed():
    energy = codec.energy_from_dict({"step_seconds": 0.1, "tracks": {"tap.wav": [-300.0, float("-inf"), 0.0, Speakers.MAX_LEVEL_DB]}})
    assert energy["tap.wav"].levels == (-120.0, -120.0, 0.0, Speakers.MAX_LEVEL_DB)


def test_a_damaged_energy_file_is_a_repository_error_naming_the_file(tmp_path: Path):
    repo, meeting = _repo_with_meeting(tmp_path)
    path = tmp_path / "recordings" / meeting.id / ENERGY
    for damaged in ({"step_seconds": 0, "tracks": {"tap.wav": [-30.0]}}, {"step_seconds": 0.1, "tracks": {"tap.wav": [1e5]}}):
        path.write_text(json.dumps(damaged))
        with pytest.raises(RepositoryError, match=ENERGY):
            repo.load_energy(meeting.id)


# --- repository methods (task 1 deliverables) ------------------------------------------

def _repo_with_meeting(tmp_path: Path) -> tuple[FsMeetingRepository, Meeting]:
    repo = FsMeetingRepository(tmp_path)
    meeting = Meeting.start(datetime(2026, 10, 17, 9, 30, 12), pid=4242)
    repo.create(meeting)
    return repo, meeting


def test_the_speaker_log_and_energy_files_are_absent_until_written(tmp_path: Path):
    repo, meeting = _repo_with_meeting(tmp_path)
    assert repo.load_speaker_log(meeting.id, 0.0, 10.0) is None and repo.load_energy(meeting.id) == {}
    (tmp_path / "recordings" / meeting.id / SPEAKERS).write_text("\n".join(_lines(DX_EXAMPLE)) + "\n")
    loaded = repo.load_speaker_log(meeting.id, 0.0, 2600.0)
    assert loaded is not None and [t.name for t in loaded.turns] == [LUCAS] and abs(loaded.turns[0].start - 191.104) < 1e-6
    repo.write_speakers_unavailable(meeting.id, "binary-missing")   # replaces whatever the helper left
    assert repo.load_speaker_log(meeting.id, 0.0, 10.0).unavailable == "binary-missing"
    assert (tmp_path / "recordings" / meeting.id / SPEAKERS).read_text().count("\n") == 1
    energy = {"tap.wav": EnergyTimeline(0.1, (-120.0, -30.0))}
    repo.save_energy(meeting.id, energy)
    assert repo.load_energy(meeting.id) == energy


def test_the_notice_day_is_none_when_absent_or_damaged(tmp_path: Path):
    repo, _ = _repo_with_meeting(tmp_path)
    assert repo.last_notice_day("speaker-labels") is None
    repo.save_notice_day("speaker-labels", date(2026, 10, 17))
    assert repo.last_notice_day("speaker-labels") == date(2026, 10, 17)
    (tmp_path / "notices" / "speaker-labels").write_text("garbage")
    assert repo.last_notice_day("speaker-labels") is None


def test_the_active_pointer_keeps_the_observer_handle_and_reads_old_pointers(tmp_path: Path):
    repo, meeting = _repo_with_meeting(tmp_path)
    tap, mic = CaptureHandle(11, tmp_path / "tap.wav"), CaptureHandle(12, tmp_path / "mic.wav")
    repo.save_active(ActiveRecording(meeting, tap, mic, CaptureHandle(13, tmp_path / SPEAKERS)))
    assert repo.load_active().speakers_handle == CaptureHandle(13, tmp_path / SPEAKERS)
    repo.save_active(ActiveRecording(meeting, tap, mic))
    assert "speakers_handle" not in json.loads((tmp_path / "current_recording.json").read_text())
    assert repo.load_active().speakers_handle is None

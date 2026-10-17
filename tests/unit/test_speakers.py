"""Speaker attribution rules (domain/speakers.py): docs/tasks/speaker-attribution/_tests.md UT-001 to UT-019."""
from __future__ import annotations

from teams_recorder.domain import (
    EnergyTimeline, LabelSummary, Segment, SpeakerEvent, SpeakerLog, SpeakerReason, SpeakerTurn, Transcript, label_segments,
    no_label_reason, turns_from_events, user_label,
)
from teams_recorder.domain import health, models

LUCAS, ANA = "Lucas Huguenin Gurgel de Moura", "Ana"


def _log(*turns: SpeakerTurn, roster: tuple[str, ...] = (LUCAS,), ended: bool = True) -> SpeakerLog:
    return SpeakerLog(turns=turns, roster=roster, ended=ended)


def _timeline(*levels: float) -> EnergyTimeline:
    return EnergyTimeline(0.1, tuple(levels))


def _flat(level: float, seconds: float = 100.0) -> EnergyTimeline:
    return _timeline(*[level] * int(round(seconds * 10)))


def _label(segments: list[Segment], log: SpeakerLog | None = None, mic: EnergyTimeline | None = None,
           tap: EnergyTimeline | None = None) -> list[str | None]:
    return [s.speaker for s in label_segments(Transcript(segments=segments), log, mic, tap, "Felipe").segments]


# --- turns_from_events -----------------------------------------------------------

def test_ut001_an_on_and_off_make_one_turn():
    events = [SpeakerEvent(10.0, LUCAS, True, "main"), SpeakerEvent(18.0, LUCAS, False, "main")]
    assert turns_from_events(events, end=100.0) == (SpeakerTurn(10.0, 18.0, LUCAS),)


def test_ut002_a_turn_still_open_closes_at_the_end():
    assert turns_from_events([SpeakerEvent(10.0, LUCAS, True, "main")], end=100.0) == (SpeakerTurn(10.0, 100.0, LUCAS),)


def test_ut003_a_turn_shorter_than_half_a_second_is_kept():
    events = [SpeakerEvent(10.0, LUCAS, True, "main"), SpeakerEvent(10.3, LUCAS, False, "main")]
    (turn,) = turns_from_events(events, end=100.0)
    assert turn.start == 10.0 and abs(turn.end - 10.3) < 1e-9


def test_ut004_a_lost_window_closes_its_open_turns_only():
    events = [SpeakerEvent(10.0, LUCAS, True, "compact"), SpeakerEvent(11.0, ANA, True, "main"),
              SpeakerEvent(14.0, "", False, "compact"), SpeakerEvent(20.0, ANA, False, "main")]
    assert turns_from_events(events, end=100.0) == (SpeakerTurn(10.0, 14.0, LUCAS), SpeakerTurn(11.0, 20.0, ANA))


def test_ut005_turns_of_a_name_in_both_windows_are_merged():
    events = [SpeakerEvent(10.0, LUCAS, True, "main"), SpeakerEvent(15.0, LUCAS, True, "compact"),
              SpeakerEvent(20.0, LUCAS, False, "main"), SpeakerEvent(25.0, LUCAS, False, "compact")]
    assert turns_from_events(events, end=100.0) == (SpeakerTurn(10.0, 25.0, LUCAS),)


def test_ut007_the_same_display_name_in_two_tiles_is_one_name():
    events = [SpeakerEvent(5.0, ANA, True, "main"), SpeakerEvent(8.0, ANA, True, "compact"),
              SpeakerEvent(9.0, ANA, False, "main"), SpeakerEvent(12.0, ANA, False, "compact")]
    assert turns_from_events(events, end=100.0) == (SpeakerTurn(5.0, 12.0, ANA),)


# --- label_segments: remote speakers ----------------------------------------------

def test_ut006_a_covered_line_takes_the_name_and_an_uncovered_one_none():
    labels = _label([Segment(30.0, 40.0, "então eu subo o ambiente"), Segment(50.0, 60.0, "a gente combina depois")],
                    _log(SpeakerTurn(32.0, 39.0, LUCAS)))
    assert labels == [LUCAS, None]


def test_ut008_the_30_percent_boundary_zero_length_lines_and_ties():
    assert _label([Segment(0.0, 10.0, "fala")], _log(SpeakerTurn(5.0, 8.0, LUCAS))) == [LUCAS]   # exactly 3.0 of 10 s
    assert _label([Segment(0.0, 10.0, "fala")], _log(SpeakerTurn(5.0, 7.9, LUCAS))) == [None]    # 2.9 s
    zero = label_segments(Transcript(segments=[Segment(5.0, 5.0, "fala")]), _log(SpeakerTurn(0.0, 10.0, LUCAS)), None, None, "Felipe")
    assert zero.segments[0].speaker is None and zero.labels == LabelSummary(0, 0, SpeakerReason.NO_MATCH.value)
    tie = _log(SpeakerTurn(0.0, 5.0, ANA), SpeakerTurn(5.0, 10.0, LUCAS), roster=(ANA, LUCAS))
    assert _label([Segment(2.5, 7.5, "fala")], tie) == [ANA]   # equal overlap: the turn that started first
    same_start = _log(SpeakerTurn(0.0, 10.0, LUCAS), SpeakerTurn(0.0, 10.0, ANA), roster=(ANA, LUCAS))
    assert _label([Segment(2.0, 4.0, "fala")], same_start) == [ANA]   # then the first name in alphabetical order


def test_ut009_the_largest_overlap_wins():
    log = _log(SpeakerTurn(0.0, 4.0, LUCAS), SpeakerTurn(4.0, 10.0, ANA), roster=(LUCAS, ANA))
    assert _label([Segment(0.0, 10.0, "fala")], log) == [ANA]


# --- label_segments: the user's lines -----------------------------------------------

def test_ut010_a_line_dominated_by_the_microphone_is_the_users():
    assert _label([Segment(1.0, 3.0, "pode deixar comigo")], None, mic=_flat(-30.0), tap=_flat(-45.0)) == ["Felipe"]


def test_ut011_a_qualifying_remote_turn_wins_over_the_microphone():
    assert _label([Segment(0.0, 10.0, "fala")], _log(SpeakerTurn(0.0, 4.0, LUCAS)), mic=_flat(-20.0), tap=_flat(-60.0)) == [LUCAS]


def test_ut012_speaker_leakage_louder_on_the_teams_track_is_not_the_user():
    assert _label([Segment(1.0, 3.0, "fala")], None, mic=_flat(-35.0), tap=_flat(-28.0)) == [None]


def test_ut012b_the_power_mean_keeps_a_half_silent_remote_burst_loud():
    tap = _timeline(*([-25.0, -120.0] * 20))   # a remote speaker talking half the time
    mic = _timeline(*([-40.0, -55.0] * 20))    # their voice leaking into the microphone
    assert _label([Segment(0.0, 4.0, "fala")], None, mic=mic, tap=tap) == [None]


def test_ut013_without_one_of_the_timelines_only_turns_apply():
    segments = [Segment(0.0, 10.0, "fala"), Segment(20.0, 30.0, "outra fala")]
    log = _log(SpeakerTurn(0.0, 10.0, LUCAS))
    assert _label(segments, log, mic=None, tap=_flat(-60.0)) == [LUCAS, None]
    assert _label(segments, log, mic=_flat(-20.0), tap=None) == [LUCAS, None]


def test_ut013b_windows_are_selected_by_their_midpoint():
    mic = _timeline(-120.0, -120.0, -120.0, -20.0, -120.0, -120.0)
    tap = _timeline(*[-120.0] * 6)
    assert _label([Segment(0.31, 0.39, "sim")], None, mic=mic, tap=tap) == ["Felipe"]   # window 3, midpoint 0.35
    assert _label([Segment(0.36, 0.44, "sim")], None, mic=mic, tap=tap) == [None]       # no midpoint inside


def test_ut014_the_margin_and_the_floor_are_inclusive():
    assert _label([Segment(0.0, 1.0, "sim")], None, mic=_flat(-50.0), tap=_flat(-56.0)) == ["Felipe"]
    assert _label([Segment(0.0, 1.0, "sim")], None, mic=_flat(-50.1), tap=_flat(-56.1)) == [None]


def test_ut015_without_any_evidence_the_transcript_is_unlabelled():
    transcript = Transcript(segments=[Segment(0.0, 2.0, "Olá"), Segment(2.0, 4.0, "tudo bem?")])
    labelled = label_segments(transcript, None, None, None, "Felipe")
    assert [(s.start, s.end, s.text, s.speaker) for s in labelled.segments] == [(0.0, 2.0, "Olá", None), (2.0, 4.0, "tudo bem?", None)]
    assert labelled.as_timestamped_text() == transcript.as_timestamped_text()
    assert labelled.labels == LabelSummary(0, 2, SpeakerReason.NO_OBSERVER.value)


def test_ut016_non_speech_markers_are_never_labelled_nor_counted():
    labelled = label_segments(Transcript(segments=[Segment(0.0, 5.0, "[BLANK_AUDIO]"), Segment(5.0, 9.0, "fala")]),
                              _log(SpeakerTurn(0.0, 9.0, LUCAS)), None, None, "Felipe")
    assert [s.speaker for s in labelled.segments] == [None, LUCAS]
    assert labelled.labels is not None and labelled.labels.eligible == 1
    assert models.is_speech is health.is_speech


def test_ut016b_the_copy_carries_roster_user_label_and_summary():
    segments = [Segment(0.0, 5.0, "um"), Segment(5.0, 10.0, "dois"), Segment(20.0, 25.0, "três")]
    log = _log(SpeakerTurn(0.0, 10.0, LUCAS), roster=("Felipe Mateus de Carvalho", LUCAS))
    labelled = label_segments(Transcript(segments=segments), log, None, None, "Felipe")
    assert labelled.roster == ("Felipe Mateus de Carvalho", LUCAS) and labelled.user_label == "Felipe"
    assert labelled.labels == LabelSummary(2, 3, None)
    nothing = label_segments(Transcript(segments=[Segment(20.0, 25.0, "três")]), log, None, None, "Felipe")
    assert nothing.labels == LabelSummary(0, 1, SpeakerReason.NO_MATCH.value)


def test_ut017_the_users_label_falls_back_to_the_own_tile_then_voce():
    log = SpeakerLog(me="Felipe Mateus")
    assert user_label("Felipe", log, "Você") == "Felipe"
    assert user_label("  ", log, "Você") == "Felipe Mateus"
    assert user_label("", None, "Você") == "Você"


def test_ut018_speakers_in_order_and_the_reason_for_every_file_state():
    transcript = Transcript(segments=[Segment(0, 1, "a", "Ana"), Segment(1, 2, "b", "Lucas"), Segment(2, 3, "c", "Ana"), Segment(3, 4, "d")])
    assert transcript.speakers == ["Ana", "Lucas"]
    assert no_label_reason(None, 0) is SpeakerReason.NO_OBSERVER
    assert no_label_reason(SpeakerLog(unavailable="binary-missing"), 0) is SpeakerReason.BINARY_MISSING
    assert no_label_reason(SpeakerLog(ended=False), 0) is SpeakerReason.OBSERVER_DIED
    assert no_label_reason(SpeakerLog(ended=True), 0) is SpeakerReason.NO_WINDOW
    assert no_label_reason(SpeakerLog(roster=(ANA,), ended=True), 0) is SpeakerReason.NO_MATCH
    assert no_label_reason(SpeakerLog(roster=(ANA,)), 3) is None
    assert [r for r in SpeakerReason if r.notifies] == [SpeakerReason.BINARY_MISSING, SpeakerReason.PERMISSION_MISSING,
                                                        SpeakerReason.START_FAILED, SpeakerReason.OBSERVER_DIED, SpeakerReason.NO_WINDOW]


def test_ut019_labelled_lines_render_with_the_name():
    transcript = Transcript(segments=[Segment(192.0, 199.5, " então eu subo o ambiente ", LUCAS), Segment(210.0, 213.2, "a gente combina")])
    assert transcript.as_timestamped_text().splitlines() == [
        f"[00:03:12] {LUCAS}: então eu subo o ambiente",
        "[00:03:30] a gente combina",
    ]

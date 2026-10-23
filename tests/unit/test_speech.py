"""The speech check rules: docs/tasks/speech-check/_tests.md UT-001 to UT-007."""
from __future__ import annotations

import pytest

from teams_recorder.domain import SpeechActivity, SpeechCheck, SpeechRules, check_speech, samples_with_speech, sample_offsets


def test_the_thresholds_are_the_spec_constants():
    assert SpeechRules() == SpeechRules(min_speech_seconds=2.0, min_sample_speech_seconds=3.0, notify_min_audio_seconds=60.0)


# check_speech
def test_ut001_no_segments_is_no_speech_with_the_audio_length_kept():
    assert check_speech(SpeechActivity(309.6, ())) == SpeechCheck(found=False, speech_seconds=0.0, audio_seconds=309.6, segments=0)


@pytest.mark.parametrize("segments, found", [
    (((0.0, 1.99),), False),
    (((0.0, 1.0), (5.0, 5.99)), False),
    (((0.0, 2.0),), True),
    (((0.0, 1.0), (5.0, 6.0)), True),
    (((0.0, 1.0),), False),               # the "alô?" case
    (((0.01, 2.01),), True),              # 2.01 - 0.01 is 1.9999999999999998 in floats: exactly 2.00 s must still be speech
    ((), False),
])
def test_ut002_the_verdict_is_at_two_seconds_of_speech(segments: tuple[tuple[float, float], ...], found: bool):
    assert check_speech(SpeechActivity(60.0, segments)).found is found


def test_ut002_the_verdict_uses_the_measured_value_not_the_rounded_one():
    check = check_speech(SpeechActivity(60.0, ((0.0, 1.99),)))
    assert check.found is False and check.speech_seconds == 2.0   # 1.99 s prints as 2.0 and is still no speech


def test_ut003_the_record_rounds_to_a_tenth_and_counts_the_segments():
    check = check_speech(SpeechActivity(27.3, ((0.0, 4.19), (4.58, 7.2))))
    assert check == SpeechCheck(found=True, speech_seconds=6.8, audio_seconds=27.3, segments=2)


def test_ut003_the_audio_length_is_rounded_too():
    assert check_speech(SpeechActivity(3138.04, ((0.0, 2676.43),))) == SpeechCheck(True, 2676.4, 3138.0, 1)


def test_the_rules_decide_the_threshold():
    activity = SpeechActivity(60.0, ((0.0, 4.0),))
    assert check_speech(activity).found is True
    assert check_speech(activity, SpeechRules(min_speech_seconds=5.0)).found is False


# SpeechActivity
def test_speech_seconds_is_the_sum_of_the_segments():
    assert SpeechActivity(100.0, ((0.0, 4.19), (4.58, 7.2))).speech_seconds == pytest.approx(6.81)
    assert SpeechActivity(100.0).speech_seconds == 0.0


def test_ut004_a_segment_counts_only_its_overlap_with_the_window():
    activity = SpeechActivity(100.0, ((5.0, 15.0),))
    assert activity.speech_between(0.0, 10.0) == 5.0         # straddles the window's end
    assert activity.speech_between(10.0, 20.0) == 5.0        # straddles the window's start
    assert activity.speech_between(6.0, 9.0) == 3.0          # inside the segment
    assert activity.speech_between(0.0, 100.0) == 10.0       # the segment inside the window
    assert activity.speech_between(20.0, 30.0) == 0.0        # nowhere near it


def test_ut004_a_segment_touching_an_edge_adds_nothing():
    activity = SpeechActivity(100.0, ((10.0, 20.0),))
    assert activity.speech_between(0.0, 10.0) == 0.0
    assert activity.speech_between(20.0, 30.0) == 0.0


def test_ut004_an_empty_activity_has_no_speech_in_any_window():
    assert SpeechActivity(100.0).speech_between(0.0, 30.0) == 0.0


def test_ut004_the_overlaps_of_several_segments_add_up():
    activity = SpeechActivity(100.0, ((0.0, 4.0), (8.0, 12.0), (20.0, 40.0)))
    assert activity.speech_between(2.0, 10.0) == 4.0


# samples_with_speech
def test_ut005_the_vans_pattern_keeps_the_fourth_fifth_and_sixth_windows_in_order():
    offsets = sample_offsets(2185.0)
    assert len(offsets) == 8
    speech = [0.0, 0.0, 0.0, 9.0, 14.0, 5.0, 0.0, 0.0]   # seconds of speech in each 30 s window
    segments = tuple((at + 2.0, at + 2.0 + seconds) for at, seconds in zip(offsets, speech) if seconds)
    kept = samples_with_speech(offsets, SpeechActivity(2185.0, segments), 30.0)
    assert kept == [offsets[3], offsets[4], offsets[5]]


@pytest.mark.parametrize("seconds, kept", [(3.0, True), (2.9, False), (3.5, True)])
def test_ut006_a_window_needs_three_seconds_of_speech(seconds: float, kept: bool):
    activity = SpeechActivity(100.0, ((10.0, 10.0 + seconds),))
    assert (samples_with_speech([10.0], activity, 30.0) == [10.0]) is kept


def test_ut006_exactly_three_seconds_is_kept_whatever_the_float_noise():
    activity = SpeechActivity(100.0, ((1.02, 4.02),))   # 4.02 - 1.02 is 2.9999999999999996 in floats
    assert samples_with_speech([0.0], activity, 30.0) == [0.0]


def test_ut006_speech_is_counted_inside_the_window_only():
    activity = SpeechActivity(100.0, ((25.0, 35.0),))   # 5 s fall in [0, 30) and 5 s in [30, 60)
    assert samples_with_speech([0.0, 30.0, 60.0], activity, 30.0) == [0.0, 30.0]
    assert samples_with_speech([0.0, 30.0], activity, 30.0, SpeechRules(min_sample_speech_seconds=6.0)) == []


def test_ut007_no_segments_keeps_no_sample():
    assert samples_with_speech([0.0, 100.0, 200.0], SpeechActivity(300.0), 30.0) == []


def test_ut007_no_offsets_keeps_none():
    assert samples_with_speech([], SpeechActivity(100.0, ((10.0, 20.0), (30.0, 50.0))), 30.0) == []

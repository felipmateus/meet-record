"""The language detection rules: docs/tasks/language-detection/_tests.md UT-001 to UT-012c."""
from __future__ import annotations

import pytest

from teams_recorder.domain import LanguageDetection, LanguageReason, LanguageSample, choose_language, counted_tally, sample_offsets

PT, EN = ("pt", "en")
ALLOWED = (PT, EN)


def _samples(*answers: tuple[str | None, float]) -> list[LanguageSample]:
    return [LanguageSample(float(i * 100), language, p) for i, (language, p) in enumerate(answers)]


# sample_offsets
def test_ut001_offsets_spread_the_samples_and_round_to_a_tenth():
    assert sample_offsets(2185.0) == [134.7, 404.1, 673.4, 942.8, 1212.2, 1481.6, 1750.9, 2020.3]


def test_ut002_a_meeting_up_to_one_window_gets_one_sample_from_its_start():
    assert sample_offsets(20.0) == [0.0]
    assert sample_offsets(30.0) == [0.0]


@pytest.mark.parametrize("duration", [5165.0, 4 * 3600.0])
def test_ut003_the_number_of_samples_is_capped_at_twelve(duration: float):
    assert len(sample_offsets(duration)) == 12


@pytest.mark.parametrize("duration", [None, 0.0])
def test_ut004_an_unknown_length_gets_one_sample_at_the_start(duration: float | None):
    assert sample_offsets(duration) == [0.0]


def test_ut005_the_floor_of_three_never_exceeds_the_whole_windows_the_meeting_holds():
    assert sample_offsets(100.0) == [11.7, 35.0, 58.3]
    assert sample_offsets(60.0) == [7.5, 22.5]


@pytest.mark.parametrize("duration", [45.0, 600.0, 2185.0, 5165.0])
def test_ut006_every_offset_leaves_room_for_a_whole_window(duration: float):
    offsets = sample_offsets(duration)
    assert all(0 <= offset <= duration - 30 for offset in offsets)
    assert offsets == sorted(offsets)


# choose_language
def test_ut007_all_samples_in_one_language_win_it():
    samples = _samples(*[(EN, 0.65 + 0.03 * i) for i in range(12)])
    assert choose_language(samples, ALLOWED, PT) == LanguageDetection(EN, LanguageReason.MAJORITY, 12, 12, tuple(samples))


def test_ut008_answers_outside_the_allow_list_and_missing_ones_do_not_count_but_are_kept():
    samples = _samples((EN, .993), ("is", .965), ("is", .90), (EN, .997), (EN, .987), ("is", .946), ("is", .979), (None, 0.0))
    detection = choose_language(samples, ALLOWED, PT)
    assert (detection.language, detection.reason, detection.counted, detection.votes) == (EN, LanguageReason.MAJORITY, 3, 3)
    assert detection.samples == tuple(samples) and len(detection.samples) == 8 and detection.detected


def test_ut009_a_minority_and_a_disallowed_language_do_not_move_the_winner():
    detection = choose_language(_samples((PT, .99), (PT, .99), (EN, .97), (PT, .99), ("es", .60)), ALLOWED, PT)
    assert (detection.language, detection.reason, detection.counted, detection.votes) == (PT, LanguageReason.MAJORITY, 4, 3)


def test_ut010_no_usable_sample_falls_back():
    detection = choose_language(_samples(("is", .97), ("gl", .80), (EN, .40), (None, 0.0)), ALLOWED, PT)
    assert (detection.language, detection.reason, detection.counted, detection.votes) == (PT, LanguageReason.NO_USABLE_SAMPLE, 0, 0)
    assert not detection.detected


def test_ut011_a_tie_has_no_majority():
    detection = choose_language(_samples((EN, .9), (EN, .9), (PT, .9), (PT, .9)), ALLOWED, PT)
    assert (detection.language, detection.reason, detection.counted, detection.votes) == (PT, LanguageReason.NO_MAJORITY, 4, 0)


def test_ut012_a_single_sample_is_enough_but_one_vote_among_several_samples_is_not():
    one = choose_language(_samples((EN, .9)), ALLOWED, PT)
    assert (one.language, one.reason, one.votes) == (EN, LanguageReason.MAJORITY, 1)
    few = choose_language(_samples((EN, .9), ("is", .9), (None, 0.0)), ALLOWED, PT)
    assert (few.language, few.reason, few.counted, few.votes) == (PT, LanguageReason.TOO_FEW_VOTES, 1, 0)
    split = choose_language(_samples((EN, .9), (PT, .9)), ALLOWED, PT)
    assert (split.language, split.reason) == (PT, LanguageReason.NO_MAJORITY)


def test_ut012a_a_probability_of_exactly_one_half_counts():
    assert choose_language(_samples((EN, 0.5), (EN, 0.5)), ALLOWED, PT).counted == 2
    assert choose_language(_samples((EN, 0.4999), (EN, 0.4999)), ALLOWED, PT).counted == 0


def test_ut012b_the_fallback_is_the_one_passed_in_not_the_first_of_the_allow_list():
    detection = choose_language(_samples(("is", .9)), (EN, PT), EN)
    assert (detection.language, detection.reason) == (EN, LanguageReason.NO_USABLE_SAMPLE)


def test_ut012c_the_tally_counts_per_allowed_language_in_allowed_order():
    detection = choose_language(_samples((EN, .9), (EN, .9), (PT, .9), (PT, .9)), ALLOWED, PT)
    tally = counted_tally(detection, ALLOWED)
    assert tally == {PT: 2, EN: 2} and list(tally) == [PT, EN]
    assert list(counted_tally(detection, (EN, PT))) == [EN, PT]

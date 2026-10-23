"""Transcript health: repetition loops (whisper hallucination) and minutes without text."""
import pytest

from teams_recorder.domain import CaptureStats, Segment, Transcript, TranscriptHealth, loop_flags, rate_mismatch, transcript_health
from tests.fakes import looped_transcript, speech_transcript


def _segments(*texts: str, every: float = 5.0) -> list[Segment]:
    return [Segment(i * every, i * every + every - 1, text) for i, text in enumerate(texts)]


def test_healthy_meeting_has_no_loops_and_text_in_every_minute():
    health = transcript_health(speech_transcript(minutes=20), max_loop_share=0.10)
    assert health == TranscriptHealth(loop_share=0.0, covered_minutes=20, total_minutes=20, degraded=False, uncovered=())


def test_hallucination_loop_is_degraded_with_its_minutes_uncovered():
    health = transcript_health(looped_transcript(minutes=20, loop_minutes=15), max_loop_share=0.10)
    assert health.degraded and health.loop_share == 180 / 210   # 180 loop segments, 30 of speech
    assert (health.covered_minutes, health.total_minutes) == (5, 20)
    assert health.uncovered == ((0, 15),) and health.uncovered_ranges() == ["00:00:00–00:15:00"]


def test_natural_fillers_spread_over_the_meeting_are_not_a_loop():
    # "Entendeu?" and "Tá" 18 and 17 times in a real 29-minute meeting: the same text, but never close together
    texts = [("Entendeu?" if i % 8 == 0 else f"frase {i} da reunião") for i in range(200)]
    assert not any(loop_flags(_segments(*texts)))


def test_a_loop_is_five_copies_within_thirty_segments_ignoring_case_and_punctuation():
    looped = ["A CIDADE NO BRASIL", "a cidade no Brasil.", "yeah", "A CIDADE NO BRASIL", "A cidade no Brasil", "ok", "A CIDADE NO BRASIL"]
    flags = loop_flags(_segments(*looped, "fim"))
    assert flags == [True, True, False, True, True, False, True, False]
    filler = [f"frase {i}" for i in range(26)]
    spread = ["Ok.", *filler, "Ok.", "OK", "ok", "Ok"]   # 5 copies over 31 segments
    assert not any(loop_flags(_segments(*spread)))
    within = ["Ok.", *filler[:-1], "Ok.", "OK", "ok", "Ok"]   # the same 5 copies over 30 segments: the 4 back to back are a loop
    assert [i for i, looped in enumerate(loop_flags(_segments(*within))) if looped] == [26, 27, 28, 29]   # UT-018: the lone "Ok." at 0 is a short line outside a run


def test_loops_cycling_through_up_to_seven_lines_are_caught():
    for lines in (3, 5, 7):
        cycle = [f"linha {i} da alucinação" for i in range(lines)]
        assert transcript_health(Transcript(_segments(*cycle * 20)), max_loop_share=0.10).loop_share == 1.0, lines
    eight = [f"linha {i}" for i in range(8)] * 20   # the limit: a cycle of 8 lines spreads 5 copies over 33 segments
    assert transcript_health(Transcript(_segments(*eight)), max_loop_share=0.10).loop_share == 0.0


def test_a_phrase_written_twice_in_one_segment_counts_as_the_phrase():
    texts = ["A CIDADE NO BRASIL", "A CIDADE NO BRASIL A CIDADE NO BRASIL", "A cidade no Brasil.", "a cidade no brasil a cidade no brasil", "A CIDADE NO BRASIL"]
    assert all(loop_flags(_segments(*texts)))
    assert not any(loop_flags(_segments(*["Tá, tá.", "Tá.", "Sim, sim.", "Sim.", "Ok, ok."])))   # duplicates of different phrases


def test_non_speech_markers_do_not_cover_a_minute():
    # whisper writes [BLANK_AUDIO] (and (música), *risos*) between loop lines: they must not hide the gap
    texts = ["[BLANK_AUDIO]" if i % 10 == 9 else "A CIDADE NO BRASIL" for i in range(240)]
    health = transcript_health(Transcript(_segments(*texts) + [Segment(1200.0, 1205.0, "Bom dia, vamos começar.")]), max_loop_share=0.10)
    assert health.degraded and health.uncovered == ((0, 20),) and health.covered_minutes == 1
    markers = Transcript(_segments("(música)", "*risos*", "♪ ♪", "[ Silence ]", every=60))
    assert transcript_health(markers, max_loop_share=0.10).covered_minutes == 0


def test_two_lines_alternating_are_a_loop_too():
    flags = loop_flags(_segments(*["Obrigado.", "Tchau, tchau."] * 5))
    assert all(flags)


# --- short lines: docs/tasks/speech-check/_tests.md UT-010 to UT-018 ------------------------------------------------------
# A line of at most 2 words ("Okay.", "e aí", "...") is in a loop only when the window rule flags it AND it sits in a run
# of 3 or more consecutive segments that are all short and all flagged. Lines of 3 or more words keep the window rule alone.

def _flagged(*texts: str) -> list[int]:
    return [i for i, looped in enumerate(loop_flags(_segments(*texts))) if looped]


def _lines(total: int, at: dict[int, str]) -> list[str]:
    """`total` segments: the text in `at` at its index, a different 3+ word line everywhere else."""
    return [at.get(i) or f"frase distinta {i} da reunião" for i in range(total)]


def _vans_retry() -> Transcript:
    """The English vans meeting's retry: 77 segments, "Okay." 8 times within 27 segments and never 3 in a row (pairs at most)."""
    return Transcript(_segments(*_lines(77, {i: "Okay." for i in (3, 4, 9, 14, 15, 20, 24, 27)})))


def test_short_replies_spread_through_a_conversation_are_not_a_loop():
    """UT-010: eight "Okay." within 30 segments pass the window rule, but no 3 stand in a row."""
    assert not any(loop_flags(_vans_retry().segments))


def test_the_vans_retry_is_no_longer_degraded():
    """UT-016: the same transcript is 8 of 77 segments (10.4%) under the window rule alone, above the 10% limit."""
    health = transcript_health(_vans_retry(), max_loop_share=0.10)
    assert health.loop_share == 0.0 and not health.degraded


def test_a_short_line_is_flagged_only_in_its_run_of_three_back_to_back():
    """UT-011: "e aí" six times within 30 segments: the three in a row are a loop, the three spread are not."""
    texts = _lines(24, {i: "e aí" for i in (2, 7, 12, 13, 14, 19)})
    assert _flagged(*texts) == [12, 13, 14]


def test_three_short_copies_back_to_back_are_not_enough_for_the_window_rule():
    """UT-012: a run of 3 is not a loop without the 5 copies the window rule needs."""
    assert _flagged(*_lines(20, {i: "e aí" for i in (8, 9, 10)})) == []


def test_lines_of_three_words_keep_the_window_rule_alone():
    """UT-013: "eu estou aberto" five times within 30 segments, never back to back, is a loop as before."""
    positions = (1, 6, 11, 16, 21)
    assert _flagged(*_lines(26, {i: "eu estou aberto" for i in positions})) == list(positions)


def test_a_line_without_words_counts_as_short():
    """UT-014: "..." has no words, so it needs the run like any short line."""
    assert _flagged(*_lines(40, {i: "..." for i in (2, 6, 10, 14, 18, 22)})) == []
    assert _flagged(*_lines(12, {i: "..." for i in range(3, 8)})) == [3, 4, 5, 6, 7]


def test_copies_in_different_case_are_one_short_line_for_the_run_too():
    """UT-015: "Ok.", "OK" and "ok" are one key. Eight spread in pairs at most are no loop; three in a row among five copies are."""
    spread = {i: ("Ok." if i % 2 else "OK") for i in (2, 3, 8, 9, 14, 15, 20, 21)}
    assert _flagged(*_lines(30, spread)) == []
    assert _flagged(*_lines(20, {1: "Ok", 4: "Ok.", 5: "OK", 6: "ok", 12: "Ok"})) == [4, 5, 6]


def test_short_lines_that_differ_are_a_loop_when_they_alternate_back_to_back():
    """UT-017: the existing `test_two_lines_alternating_are_a_loop_too` (Obrigado. / Tchau, tchau. x5) keeps passing unchanged.
    "Okay." / "Yeah." six times each back to back are flagged too; the same lines each followed by a different line are not."""
    alternating = ["Okay.", "Yeah."] * 6
    assert _flagged(*alternating) == list(range(12))
    separated = [text for k, line in enumerate(alternating) for text in (line, f"frase distinta {k}")]
    assert _flagged(*separated) == []   # the window rule flags all 12 copies, but no two of them are next to each other


def test_a_long_line_between_short_ones_ends_the_run():
    """Not a UT: the run is of short lines only. A flagged line of 3 words stays flagged (today's rule) but does not join the run."""
    texts = ["Okay."] * 2 + ["eu estou aberto"] * 5 + ["Okay."] * 3   # 5 copies of "Okay." within the window, split 2 + 3 by the long loop
    assert _flagged(*texts) == [2, 3, 4, 5, 6, 7, 8, 9]   # the long loop and the run of 3; the first two "Okay." are a run of 2


def test_threshold_is_exclusive_and_configurable():
    transcript = Transcript(_segments(*["Legenda por Sônia Ruberti"] * 5, *[f"fala {i}" for i in range(45)]))   # 10% in a loop
    assert not transcript_health(transcript, max_loop_share=0.10).degraded
    assert transcript_health(transcript, max_loop_share=0.05).degraded


def test_segments_without_words_cover_nothing_but_can_loop():
    transcript = Transcript(_segments(*["♪"] * 12, "Bom dia.", every=10))   # music for 2 minutes, then speech
    health = transcript_health(transcript, max_loop_share=0.5)
    assert health.degraded and health.covered_minutes == 1 and health.uncovered == ((0, 2),)


def test_a_segment_covers_every_minute_it_spans_and_total_rounds_up():
    transcript = Transcript([Segment(50.0, 130.0, "uma fala longa que atravessa dois minutos"), Segment(300.0, 330.5, "fim")])
    health = transcript_health(transcript, max_loop_share=0.10)
    assert health.total_minutes == 6 and health.uncovered == ((3, 5),) and health.covered_minutes == 4


def test_empty_transcript_is_not_degraded():
    assert transcript_health(Transcript(), max_loop_share=0.10) == TranscriptHealth(0.0, 0, 0, False, ())


def test_the_meeting_length_counts_the_minutes_after_the_last_segment():
    transcript = speech_transcript(minutes=10)
    health = transcript_health(transcript, max_loop_share=0.10, duration_seconds=86 * 60 + 5)
    assert (health.covered_minutes, health.total_minutes) == (10, 86) and health.uncovered == ((10, 86),)
    assert transcript_health(transcript, 0.10, duration_seconds=600 + 20).total_minutes == 10   # 20 s of tail is not a minute
    assert transcript_health(Transcript(), 0.10, duration_seconds=1800).uncovered == ((0, 30),)


def test_healthier_prefers_a_loop_free_pass_that_keeps_most_of_the_text_then_more_text_then_fewer_loops():
    bad = TranscriptHealth(0.70, 28, 86, True)
    better = TranscriptHealth(0.40, 50, 86, True)
    good = TranscriptHealth(0.04, 84, 86, False)
    assert good.is_healthier_than(better) and better.is_healthier_than(bad)
    assert TranscriptHealth(0.02, 80, 86, False).is_healthier_than(TranscriptHealth(0.30, 86, 86, True))   # 80 >= 85% of 86
    assert TranscriptHealth(0.30, 86, 86, True).is_healthier_than(TranscriptHealth(0.02, 70, 86, False))   # 70 < 85% of 86
    assert TranscriptHealth(0.0, 28, 86, False).is_healthier_than(bad)                                     # same text, no loop
    assert TranscriptHealth(0.03, 84, 86, False).is_healthier_than(TranscriptHealth(0.04, 84, 86, False))
    assert not bad.is_healthier_than(bad)   # a tie keeps the first pass


def test_an_empty_or_cut_short_retry_never_replaces_a_pass_with_text():
    first = TranscriptHealth(0.92, 27, 86, True, ((0, 59),))
    assert not TranscriptHealth(0.0, 0, 86, False, ((0, 86),)).is_healthier_than(first)   # VAD dropped everything
    assert not TranscriptHealth(0.0, 3, 86, False).is_healthier_than(first)                # only 3 minutes came back


# --- sample-rate mismatch in the Teams track ----------------------------------------------------

def _stats(written: float, short: float, gaps: int = 0) -> CaptureStats:
    return CaptureStats(written_seconds=written, padded_seconds=short, short_padded_seconds=short, gaps=gaps)


def test_a_16_khz_device_written_as_48_khz_is_a_rate_mismatch():
    # counters of 2026-10-14_15-38-49: 709.9 s written, 474.9 s padded in 0.2 s pads, 0 gaps
    assert rate_mismatch(_stats(709.9, 474.9), 0.05, 60) is True
    assert _stats(709.9, 474.9).short_padding_share == pytest.approx(0.669, abs=0.001)


def test_healthy_tracks_and_logged_gaps_are_not_a_rate_mismatch():
    assert rate_mismatch(_stats(986.4, 7.4), 0.05, 60) is False   # 2026-10-14_09-31-39: jitter only
    long_gaps = CaptureStats(written_seconds=1621.4, padded_seconds=147.8, short_padded_seconds=0.0, gaps=1)
    assert rate_mismatch(long_gaps, 0.05, 60) is False           # delivery pauses are logged gaps, not short pads


def test_short_tracks_are_not_judged_and_the_threshold_is_exclusive():
    assert rate_mismatch(_stats(23.6, 11.3), 0.05, 60) is False   # start-up weighs too much on a few seconds
    assert rate_mismatch(_stats(100.0, 5.0), 0.05, 60) is False
    assert rate_mismatch(_stats(100.0, 5.1), 0.05, 60) is True
    assert _stats(0.0, 0.0).short_padding_share == 0.0


def test_the_2026_10_14_retry_without_loops_now_wins():
    # 2026-10-14_15-00-56: the first pass had 69% of its segments in loops yet "covered" 35 of 37 minutes, because a
    # minute counts as covered by any line outside a loop; the VAD retry had no loops and text in 31 minutes
    first = TranscriptHealth(0.69, 35, 37, True, ((6, 7), (35, 36)))
    retry = TranscriptHealth(0.0, 31, 37, False)
    assert retry.is_healthier_than(first) and not first.is_healthier_than(retry)
    assert not TranscriptHealth(0.0, 29, 37, False).is_healthier_than(first)   # 29 < 85% of 35: too much text lost

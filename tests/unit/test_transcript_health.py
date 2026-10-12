"""Transcript health: repetition loops (whisper hallucination) and minutes without text."""
from teams_recorder.domain import Segment, Transcript, TranscriptHealth, loop_flags, transcript_health
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
    within = ["Ok.", *filler[:-1], "Ok.", "OK", "ok", "Ok"]   # the same 5 copies over 30 segments are a loop
    assert [i for i, looped in enumerate(loop_flags(_segments(*within))) if looped] == [0, 26, 27, 28, 29]


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


def test_healthier_prefers_more_text_then_not_degraded_then_fewer_loops():
    bad = TranscriptHealth(0.70, 28, 86, True)
    better = TranscriptHealth(0.40, 50, 86, True)
    good = TranscriptHealth(0.04, 84, 86, False)
    assert good.is_healthier_than(better) and better.is_healthier_than(bad)
    assert TranscriptHealth(0.30, 86, 86, True).is_healthier_than(TranscriptHealth(0.02, 80, 86, False))   # more usable text wins
    assert TranscriptHealth(0.0, 28, 86, False).is_healthier_than(bad)                                     # same text, no loop
    assert TranscriptHealth(0.03, 84, 86, False).is_healthier_than(TranscriptHealth(0.04, 84, 86, False))
    assert not bad.is_healthier_than(bad)   # a tie keeps the first pass


def test_an_empty_or_cut_short_retry_never_replaces_a_pass_with_text():
    first = TranscriptHealth(0.92, 27, 86, True, ((0, 59),))
    assert not TranscriptHealth(0.0, 0, 86, False, ((0, 86),)).is_healthier_than(first)   # VAD dropped everything
    assert not TranscriptHealth(0.0, 3, 86, False).is_healthier_than(first)                # only 3 minutes came back

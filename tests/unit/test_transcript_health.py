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


def test_a_loop_is_five_copies_within_ten_segments_ignoring_case_and_punctuation():
    looped = ["A CIDADE NO BRASIL", "a cidade no Brasil.", "yeah", "A CIDADE NO BRASIL", "A cidade no Brasil", "ok", "A CIDADE NO BRASIL"]
    flags = loop_flags(_segments(*looped, "fim"))
    assert flags == [True, True, False, True, True, False, True, False]
    spread = ["Ok."] + [f"x{i}" for i in range(3)] + ["Ok."] + [f"y{i}" for i in range(3)] + ["OK", "ok", "Ok"]   # 5 copies over 11 segments
    assert not any(loop_flags(_segments(*spread)))


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


def test_healthier_prefers_not_degraded_then_more_text_then_fewer_loops():
    bad = TranscriptHealth(0.70, 28, 86, True)
    better = TranscriptHealth(0.40, 50, 86, True)
    good = TranscriptHealth(0.04, 84, 86, False)
    assert good.is_healthier_than(better) and better.is_healthier_than(bad)
    assert TranscriptHealth(0.03, 84, 86, False).is_healthier_than(TranscriptHealth(0.04, 84, 86, False))
    assert not bad.is_healthier_than(bad)   # a tie keeps the first pass
    assert TranscriptHealth(0.02, 80, 86, False).is_healthier_than(TranscriptHealth(0.30, 86, 86, True))

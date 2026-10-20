"""domain.excerpts.excerpt_window, and the verifier's transcript_for that reuses it (UT-028, UT-053)."""
from teams_recorder.adapters.outbound.verifier_claude import Claim, transcript_for
from teams_recorder.domain import ClaimKind, ClaimRef, Segment, Transcript, excerpt_window, timestamped_line
from teams_recorder.messages import Prompt

GAP = "[...]"


def _meeting(minutes: int = 100, speaker: str | None = None) -> Transcript:
    return Transcript([Segment(i * 10.0, i * 10.0 + 8, f"fala {i} da reunião longa", speaker) for i in range(minutes * 6)])


def test_two_times_close_together_make_one_merged_excerpt_with_speaker_labels():
    t = Transcript([Segment(i * 10.0, i * 10.0 + 8, f"fala {i}", "Ana" if i % 2 else None) for i in range(60)])

    text = excerpt_window(t, [300.0, 330.0], 60, GAP)

    lines = text.splitlines()
    assert lines[0] == "[00:04:00] fala 24" and lines[-2] == "[00:06:30] Ana: fala 39" and len(lines) == 17   # 240 s .. 390 s, merged
    assert lines.count(GAP) == 1 and lines[-1] == GAP and "[00:04:10] Ana: fala 25" in lines   # the lines after the window are a gap


def test_separated_windows_have_a_gap_between_them_and_a_gap_is_not_repeated():
    text = excerpt_window(_meeting(), [100.0, 3000.0], 20, GAP).splitlines()

    assert text[0] == "[00:01:20] fala 8 da reunião longa" and text.count(GAP) == 2 and text[-1] == GAP   # between the windows and after the last
    assert text[text.index(GAP) - 1] == "[00:02:00] fala 12 da reunião longa"
    assert text[text.index(GAP) + 1] == "[00:49:40] fala 298 da reunião longa" and text[-2] == "[00:50:20] fala 302 da reunião longa"


def test_head_chars_keeps_the_start_of_the_transcript():
    t = _meeting()
    first = timestamped_line(t.segments[0]), timestamped_line(t.segments[1])

    text = excerpt_window(t, [3000.0], 10, GAP, head_chars=len(first[0]) + len(first[1]) + 2).splitlines()

    assert text[:2] == list(first) and text[2] == GAP and text[3].startswith("[00:49:50]")


def test_no_times_and_no_head_is_empty():
    assert excerpt_window(_meeting(), [], 60, GAP) == ""
    assert excerpt_window(Transcript([]), [10.0], 60, GAP, head_chars=100) == ""


def _before_the_move(transcript: Transcript, times: list[int], max_chars: int, window: int) -> str:
    """transcript_for's windowing as it was written before it moved to domain.excerpts (the oracle of UT-053)."""
    lines = [(s.start, timestamped_line(s)) for s in transcript.segments]
    keep: list[bool] = []
    used = 0
    for start, text in lines:
        used += len(text) + 1
        keep.append(used <= max_chars or any(abs(start - t) <= window for t in times))
    out: list[str] = []
    for (_, text), kept in zip(lines, keep):
        if kept:
            out.append(text)
        elif out and out[-1] != Prompt.EXCERPT_GAP:
            out.append(Prompt.EXCERPT_GAP)
    return "\n".join(out)


def test_transcript_for_gives_what_it_gave_before_the_move():
    t = _meeting(speaker="Ana")
    claims = [Claim(f"c{n}", ClaimRef(ClaimKind.DECISION, str(n)), "x", at=at) for n, at in enumerate(["00:59:55", "01:20:00", None, "00:00:30"])]

    text, excerpt = transcript_for(t, claims, max_chars=500, window=45)

    assert excerpt and text == _before_the_move(t, [3595, 4800, 30], 500, 45)
    assert Prompt.EXCERPT_GAP in text.splitlines()

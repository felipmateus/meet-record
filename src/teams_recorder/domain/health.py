"""Transcript health: how much of a transcript is a whisper hallucination loop, and which minutes have no text.

On long audio whisper conditions each window on the text it just wrote, so one hallucinated line can
repeat for many minutes ("A CIDADE NO BRASIL" 1,761 times in a real 86-minute meeting, 2026-10-08).
A loop is a line repeated close together: `LOOP_REPEATS` copies within `LOOP_WINDOW` consecutive
segments. Counting repeats over the whole meeting instead would also count natural fillers
("Entendeu?", "Tá"): they reached 9.8% of the segments of a healthy real meeting, against 0% with the
window (tasks/prd-fidelity-guard, task 1.0).
"""
from __future__ import annotations

import re
from collections import defaultdict

from .models import Segment, Transcript, TranscriptHealth

LOOP_REPEATS = 5   # copies of the same text that make a loop...
LOOP_WINDOW = 10   # ...within this many consecutive segments

_WORD = re.compile(r"\w+")


def _key(text: str) -> str:
    """Comparison key: lower-case words, so "Ok." and "OK" are the same line; text without words stays as it is."""
    return " ".join(_WORD.findall(text.lower())) or text.strip()


def loop_flags(segments: list[Segment], repeats: int = LOOP_REPEATS, window: int = LOOP_WINDOW) -> list[bool]:
    """For each segment, whether it belongs to a loop: `repeats` copies of its text within `window` consecutive segments."""
    positions: dict[str, list[int]] = defaultdict(list)
    for i, segment in enumerate(segments):
        positions[_key(segment.text)].append(i)
    flags = [False] * len(segments)
    for found in positions.values():
        for j in range(len(found) - repeats + 1):
            if found[j + repeats - 1] - found[j] < window:
                for i in found[j:j + repeats]:
                    flags[i] = True
    return flags


def _minutes(segment: Segment) -> range:
    first = int(segment.start // 60)
    return range(first, max(first, int(max(segment.start, segment.end - 0.001) // 60)) + 1)


def _ranges(minutes: list[int]) -> tuple[tuple[int, int], ...]:
    """Sorted minutes as half-open [start, end) runs: [0, 1, 2, 5] → ((0, 3), (5, 6))."""
    runs: list[tuple[int, int]] = []
    for minute in minutes:
        if runs and runs[-1][1] == minute:
            runs[-1] = (runs[-1][0], minute + 1)
        else:
            runs.append((minute, minute + 1))
    return tuple(runs)


def transcript_health(
    transcript: Transcript, max_loop_share: float, repeats: int = LOOP_REPEATS, window: int = LOOP_WINDOW,
) -> TranscriptHealth:
    """Share of segments in loops and the minutes with speech text outside them; degraded above `max_loop_share`."""
    segments = transcript.segments
    flags = loop_flags(segments, repeats, window)
    covered: set[int] = set()
    for segment, looped in zip(segments, flags):
        if not looped and _WORD.search(segment.text):
            covered.update(_minutes(segment))
    total = int(-(-transcript.duration_seconds // 60))  # ceiling: a meeting of 85.5 min has 86 minutes
    loop_share = sum(flags) / len(segments) if segments else 0.0
    return TranscriptHealth(
        loop_share=loop_share,
        covered_minutes=len(covered & set(range(total))),
        total_minutes=total,
        degraded=loop_share > max_loop_share,
        uncovered=_ranges([m for m in range(total) if m not in covered]),
    )

"""Transcript health: how much of a transcript is a whisper hallucination loop, and which minutes have no text.

On long audio whisper conditions each window on the text it just wrote, so one hallucinated line can
repeat for many minutes ("A CIDADE NO BRASIL" 1,761 times in a real 86-minute meeting, 2026-10-08).
A loop is a line repeated close together: `LOOP_REPEATS` copies within `LOOP_WINDOW` consecutive
segments, which also catches loops cycling through several lines (up to 7 with these values).
Counting repeats over the whole meeting instead would also count natural fillers ("Entendeu?", "Tá"):
they reached 9.8% of the segments of a healthy real meeting, against 0% with the window
(tasks/prd-fidelity-guard, task 1.0).

A track recorded at the wrong sample rate is broken before whisper sees it: when the output device ran at
16 kHz (a Bluetooth headset in a call) and teams-tap wrote its buffers as 48 kHz, the writer fell behind the
clock by 2/3 of every second and padded it with silence 0.2 s at a time, so the Teams speech came out 3x fast
and chopped, and whisper hallucinated over it (three meetings, 2026-10-13/14). The signature is in teams-tap's
counters: padding in pads too short to be logged as gaps, 66% of the track then, under 3% on healthy tracks.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .models import CaptureStats, Segment, Transcript, TranscriptHealth

LOOP_REPEATS = 5   # copies of the same text that make a loop...
LOOP_WINDOW = 30   # ...within this many consecutive segments

_WORD = re.compile(r"\w+")
_ANNOTATION = re.compile(r"^[\[(*♪].*[\])*♪]$")   # whisper's non-speech markers: [BLANK_AUDIO], (música), *risos*, ♪


def _key(text: str) -> str:
    """Comparison key: lower-case words, so "Ok." and "OK" are the same line, and a phrase written twice in one
    segment ("A CIDADE NO BRASIL A CIDADE NO BRASIL") counts as the phrase. Text without words stays as it is."""
    words = _WORD.findall(text.lower())
    for period in range(1, len(words) // 2 + 1):
        if len(words) % period == 0 and words == words[:period] * (len(words) // period):
            words = words[:period]
            break
    return " ".join(words) or text.strip()


def is_speech(text: str) -> bool:
    """Whether a segment carries spoken words: not empty, and not a non-speech marker such as [BLANK_AUDIO]."""
    stripped = text.strip()
    return bool(_WORD.search(stripped)) and not _ANNOTATION.match(stripped)


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


def rate_mismatch(stats: CaptureStats, max_short_pad_share: float, min_seconds: float) -> bool:
    """Whether a track looks recorded at the wrong sample rate: more than `max_short_pad_share` of it padded in
    short pads, on a track of at least `min_seconds` (on a few seconds, start-up jitter weighs too much)."""
    return stats.written_seconds >= min_seconds and stats.short_padding_share > max_short_pad_share


def transcript_health(
    transcript: Transcript, max_loop_share: float, duration_seconds: float | None = None,
    repeats: int = LOOP_REPEATS, window: int = LOOP_WINDOW,
) -> TranscriptHealth:
    """Share of segments in loops and the minutes with speech text outside them; degraded above `max_loop_share`.

    `duration_seconds` is the length of the audio (the meeting): minutes after the last segment then count
    as uncovered, and two transcripts of the same audio are measured against the same total.
    """
    segments = transcript.segments
    flags = loop_flags(segments, repeats, window)
    covered: set[int] = set()
    for segment, looped in zip(segments, flags):
        if not looped and is_speech(segment.text):
            covered.update(_minutes(segment))
    total = int(-(-transcript.duration_seconds // 60))  # ceiling: a transcript ending at 85.5 min has 86 minutes
    if duration_seconds:
        total = max(total, round(duration_seconds / 60))   # rounded: a few seconds of trailing audio are not a minute
    loop_share = sum(flags) / len(segments) if segments else 0.0
    return TranscriptHealth(
        loop_share=loop_share,
        covered_minutes=len(covered & set(range(total))),
        total_minutes=total,
        degraded=loop_share > max_loop_share,
        uncovered=_ranges([m for m in range(total) if m not in covered]),
    )

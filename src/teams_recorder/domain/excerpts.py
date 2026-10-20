"""Transcript excerpts: the lines around given moments of a meeting. Pure; shared by the claim verifier and by the
activities curator, which both show a model the parts of a long transcript that matter."""
from __future__ import annotations

from typing import Sequence

from .models import Transcript, timestamped_line


def clock_seconds(at: str | None) -> int | None:
    """Seconds of a transcript timestamp `HH:MM:SS`; None when `at` is missing or is not one."""
    parts = (at or "").strip().split(":")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    h, m, s = (int(p) for p in parts)
    return h * 3600 + m * 60 + s


def excerpt_window(transcript: Transcript, times: Sequence[float], window: float, gap: str, head_chars: int = 0) -> str:
    """Segment lines (`timestamped_line`) within ±`window` seconds of any of `times`, in order, overlaps merged,
    with `gap` where lines were left out. The lines that fit in the first `head_chars` characters of the transcript
    are kept too (0 = none). No times and no head: an empty string."""
    out: list[str] = []
    used = 0
    for segment in transcript.segments:
        line = timestamped_line(segment)
        used += len(line) + 1
        if used <= head_chars or any(abs(segment.start - t) <= window for t in times):
            out.append(line)
        elif out and out[-1] != gap:
            out.append(gap)
    return "\n".join(out)

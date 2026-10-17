"""Speaker attribution: who said each transcript line, from the Teams window and the two recorded tracks.

Two inputs, both left in the meeting folder during the recording (docs/tasks/speaker-attribution):
- the observer's events (`speakers.jsonl`): a participant tile's frame gains a class set while they speak, read from
  the Teams meeting windows through the Accessibility API (ADR-001); the codec turns them into a `SpeakerLog`;
- the level of each raw track per 100 ms (`energy.json`): the user's own tile has no frame, so the user's lines are
  the ones where the microphone track is clearly louder than the Teams track (ADR-002).

Everything here is pure: the same transcript, events and levels always give the same labels, so a meeting can be
relabelled when the rules change.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Iterable

from .models import LabelSummary, Segment, Transcript, is_speech

SILENCE_DB = -120.0   # the level stored for digital silence (ffmpeg reports -inf)
_EPSILON = 1e-6       # float tolerance on the threshold comparisons


class SpeakerReason(StrEnum):
    """Why a transcript has no label at all; each one decides whether the daily notice fires (docs/tasks/speaker-attribution/_dx.md)."""

    BINARY_MISSING = "binary-missing"          # the helper is not built
    PERMISSION_MISSING = "permission-missing"  # the helper has no Accessibility permission
    START_FAILED = "start-failed"              # the helper exited right after starting
    OBSERVER_DIED = "observer-died"            # the helper stopped before reading any Teams window
    NO_WINDOW = "no-window"                    # the helper ran to the end without reading a Teams meeting window
    NO_MATCH = "no-match"                      # tiles were read but no line matched a speaking turn
    NO_OBSERVER = "no-observer"                # no events file: feature off, Windows, or recorded before this feature

    @property
    def notifies(self) -> bool:
        """Whether the first such meeting of a day raises the notification (the others only log)."""
        return self not in (SpeakerReason.NO_MATCH, SpeakerReason.NO_OBSERVER)


@dataclass(frozen=True)
class SpeakerEvent:
    """A speaking state change, `at` seconds after the recording started. An empty `name` closes every open turn
    of its `window` (the window was lost)."""

    at: float
    name: str
    speaking: bool
    window: str = ""


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    name: str


@dataclass(frozen=True)
class SpeakerLog:
    """What the observer left for one meeting."""

    turns: tuple[SpeakerTurn, ...] = ()
    roster: tuple[str, ...] = ()   # names seen, in order of first appearance, the user's own tile included
    me: str | None = None          # the user's own display name, from their tile
    subject: str | None = None     # the meeting subject read from the window title
    ended: bool = False            # a stop event was read (the helper stopped normally)
    unavailable: str | None = None   # a SpeakerReason when the observer never ran
    skipped: int = 0               # malformed lines left out


@dataclass(frozen=True)
class EnergyTimeline:
    """The level of one track, one value per `step` seconds (window i covers [i·step, (i+1)·step))."""

    step: float
    levels: tuple[float, ...]   # dBFS; SILENCE_DB for digital silence


@dataclass(frozen=True)
class LabelRules:
    """Thresholds of the labelling, tuned by the PRD's gates G1–G2 (docs/tasks/speaker-attribution, decision 6)."""

    min_overlap: float = 0.30      # share of a line a remote speaking turn must cover
    user_margin_db: float = 6.0    # the microphone over the Teams track, for the user's lines
    user_floor_db: float = -50.0   # the microphone must be above this


def turns_from_events(events: Iterable[SpeakerEvent], end: float) -> tuple[SpeakerTurn, ...]:
    """Speaking turns per participant, from state changes in one or more windows.

    A `speaking` event opens a turn of (window, name) and the next non-speaking one closes it; an event without a name
    (a window lost or frozen) closes that window's open turns. A turn still open when the events run out closes at
    `end`, which the caller sets to the time of the last event of the file (the helper's last sign of life), never to
    the meeting's end: a helper that died, or a window that froze, credits nobody with the lines after it. A
    participant speaks while either window says so, so the turns of a name across windows are merged by union.
    """
    open_at: dict[tuple[str, str], float] = {}
    spans: dict[str, list[tuple[float, float]]] = {}

    def close(key: tuple[str, str], at: float) -> None:
        start = open_at.pop(key)
        if at > start:
            spans.setdefault(key[1], []).append((start, at))

    for event in sorted(events, key=lambda e: e.at):
        if not event.name:
            for key in [k for k in open_at if k[0] == event.window]:
                close(key, event.at)
            continue
        key = (event.window, event.name)
        if event.speaking:
            open_at.setdefault(key, event.at)
        elif key in open_at:
            close(key, event.at)
    for key in list(open_at):
        close(key, max(end, open_at[key]))
    turns: list[SpeakerTurn] = []
    for name, intervals in spans.items():
        merged: list[list[float]] = []
        for start, stop in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], stop)
            else:
                merged.append([start, stop])
        turns += [SpeakerTurn(start, stop, name) for start, stop in merged]
    return tuple(sorted(turns, key=lambda t: (t.start, t.name)))


def user_label(configured_name: str, log: SpeakerLog | None, fallback: str) -> str:
    """The label of the user's lines: the configured name, else the user's own tile name, else `fallback`."""
    return configured_name.strip() or (log.me if log and log.me else "") or fallback


def no_label_reason(log: SpeakerLog | None, labelled: int) -> SpeakerReason | None:
    """Why nothing was labelled, over every state of the events file; None when something was."""
    if labelled > 0:
        return None
    if log is None:
        return SpeakerReason.NO_OBSERVER
    if log.unavailable:
        return SpeakerReason(log.unavailable)
    if not log.roster:
        return SpeakerReason.NO_WINDOW if log.ended else SpeakerReason.OBSERVER_DIED
    return SpeakerReason.NO_MATCH


def _remote(segment: Segment, turns: tuple[SpeakerTurn, ...], rules: LabelRules) -> str | None:
    """The participant whose turns cover the segment the most, when that covers at least `min_overlap` of it.
    Ties go to the turn that started first, then to the first name in alphabetical order."""
    duration = segment.end - segment.start
    overlap: dict[str, float] = {}
    first: dict[str, float] = {}
    for turn in turns:
        covered = min(segment.end, turn.end) - max(segment.start, turn.start)
        if covered > 0:
            overlap[turn.name] = overlap.get(turn.name, 0.0) + covered
            first[turn.name] = min(first.get(turn.name, turn.start), turn.start)
    qualified = [n for n, o in overlap.items() if o >= rules.min_overlap * duration - _EPSILON]
    if not qualified:
        return None
    return min(qualified, key=lambda n: (-round(overlap[n], 6), first[n], n))


def _power_mean(timeline: EnergyTimeline, start: float, end: float) -> float | None:
    """The power mean of the windows whose midpoint lies in [start, end], in dBFS; None when no window does.
    A power mean, not a mean of decibels: a silent window weighs almost nothing, so a remote speaker who talks
    half the line still reads near their speaking level (ADR-002)."""
    step = timeline.step
    if not step > 0:   # a damaged timeline (the codec rejects it): no window can be placed, so no energy label
        return None
    first = max(0, math.ceil(start / step - 0.5 - _EPSILON))
    last = min(len(timeline.levels) - 1, math.floor(end / step - 0.5 + _EPSILON))
    levels = timeline.levels[first:last + 1] if last >= first else ()
    if not levels:
        return None
    mean = sum(10 ** (level / 10) for level in levels) / len(levels)
    return 10 * math.log10(mean) if mean > 0 else SILENCE_DB


def _is_user(segment: Segment, mic: EnergyTimeline | None, tap: EnergyTimeline | None, rules: LabelRules) -> bool:
    if mic is None or tap is None:
        return False
    mic_db = _power_mean(mic, segment.start, segment.end)
    tap_db = _power_mean(tap, segment.start, segment.end)
    if mic_db is None or tap_db is None:
        return False
    return mic_db - tap_db >= rules.user_margin_db - _EPSILON and mic_db >= rules.user_floor_db - _EPSILON


def label_segments(transcript: Transcript, log: SpeakerLog | None, mic: EnergyTimeline | None, tap: EnergyTimeline | None,
                   user: str, rules: LabelRules = LabelRules()) -> Transcript:
    """A copy of the transcript with `speaker` on each line someone can be credited with, and `roster`, `user_label`
    and `labels` filled in.

    A line is eligible when it is speech and lasts more than zero seconds. It takes the remote participant whose
    speaking turns cover at least `min_overlap` of it (the largest overlap wins); else the user, when the microphone
    is `user_margin_db` louder than the Teams track over it and above `user_floor_db`; else no label.
    """
    turns = log.turns if log else ()
    labelled = eligible = 0
    segments: list[Segment] = []
    for segment in transcript.segments:
        speaker: str | None = None
        if is_speech(segment.text) and segment.end > segment.start:
            eligible += 1
            speaker = _remote(segment, turns, rules) or (user if _is_user(segment, mic, tap, rules) else None)
            labelled += speaker is not None
        segments.append(replace(segment, speaker=speaker))
    reason = no_label_reason(log, labelled)
    return replace(
        transcript,
        segments=segments,
        roster=log.roster if log else (),
        user_label=user,
        labels=LabelSummary(labelled, eligible, reason.value if reason else None),
    )


def window_subject(title: str, compact: bool) -> str | None:
    """The meeting subject in a Teams window title: its first " | " part, the second for the compact view
    (whose first part names the view). None when there is no such part."""
    parts = [p.strip() for p in title.split(" | ")]  # literal-ok: Teams' title separator
    index = 1 if compact else 0
    return parts[index] if len(parts) > index and parts[index] else None

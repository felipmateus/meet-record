"""Meeting status derived from the files present in its folder.

Architecture decision: pipeline state is the existence of files, not a
database. This module is the single source of the derivation rule.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

META = "meta.json"
TAP_TRACK = "tap.wav"
MIC_TRACK = "mic.wav"
AUDIO = "audio.m4a"
TRANSCRIPT_TXT = "transcript.txt"
TRANSCRIPT_JSON = "transcript.json"
ANALYSIS = "analysis.json"
MINUTES = "minutes.md"  # human-readable minutes rendered from the analysis (not part of status)
ERROR = "error.txt"
LOCK = ".lock"

RAW_TRACKS = (TAP_TRACK, MIC_TRACK)


class MeetingStatus(StrEnum):
    RECORDING = "recording"
    RECORDED = "recorded"
    TRANSCRIBED = "transcribed"
    ANALYZED = "analyzed"
    FAILED = "failed"


def derive_status(files: Iterable[str]) -> MeetingStatus:
    """Derive the status from the file names present in the meeting folder.

    Precedence: explicit failure > analysis > transcript > final audio > recording.
    The audio may have been deleted by retention without affecting later statuses.
    """
    present = set(files)
    if ERROR in present:
        return MeetingStatus.FAILED
    if ANALYSIS in present:
        return MeetingStatus.ANALYZED
    if TRANSCRIPT_JSON in present:
        return MeetingStatus.TRANSCRIBED
    if AUDIO in present:
        return MeetingStatus.RECORDED
    return MeetingStatus.RECORDING


def next_step(status: MeetingStatus) -> str | None:
    """Name of the next pipeline step for the given status, or None when done/failed."""
    return {
        MeetingStatus.RECORDING: "stop",
        MeetingStatus.RECORDED: "transcribe",
        MeetingStatus.TRANSCRIBED: "analyze",
    }.get(status)

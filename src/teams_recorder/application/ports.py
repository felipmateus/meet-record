"""Application-layer ports. Concrete adapters live in adapters/outbound.

Each port is a typing.Protocol: any object with the right methods qualifies,
including the fakes used in tests.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from teams_recorder.domain import Action, Analysis, DailyPlan, Meeting, Transcript


class CallState(StrEnum):
    IN_CALL = "in_call"
    IDLE = "idle"
    UNKNOWN = "unknown"


@runtime_checkable
class CallDetector(Protocol):
    def poll(self) -> CallState: ...
    def teams_pid(self) -> int | None: ...


@dataclass(frozen=True)
class CaptureHandle:
    """Identifies a running capture: the recorder process PID and the output file.

    Deliberately concrete (not a Protocol): it must be serialized to disk so that
    `trec stop`, running in another process, can stop a capture started by `trec start`.
    """

    pid: int
    out: Path


@dataclass
class ActiveRecording:
    meeting: Meeting
    process_handle: CaptureHandle
    mic_handle: CaptureHandle


@runtime_checkable
class ProcessAudioCapture(Protocol):
    def start(self, pid: int, out: Path) -> CaptureHandle: ...
    def stop(self, handle: CaptureHandle) -> Path: ...
    def is_running(self, handle: CaptureHandle) -> bool: ...
    def warmup(self) -> bool:
        """Pre-load the recorder (e.g. trigger the macOS permission prompt); True when it responded."""
        ...


@runtime_checkable
class MicCapture(Protocol):
    def start(self, device: str, out: Path) -> CaptureHandle: ...
    def stop(self, handle: CaptureHandle) -> Path: ...
    def is_running(self, handle: CaptureHandle) -> bool: ...


@runtime_checkable
class AudioMixer(Protocol):
    def mix(self, tracks: list[Path], out: Path) -> Path: ...


@runtime_checkable
class Transcriber(Protocol):
    def transcribe(self, audio: Path, language: str) -> Transcript: ...


class AnalysisContext(Protocol):
    meeting: Meeting


@runtime_checkable
class MeetingAnalyzer(Protocol):
    def analyze(self, transcript: Transcript, meeting: Meeting) -> Analysis: ...


@runtime_checkable
class Planner(Protocol):
    def plan(
        self,
        day: date,
        analyses: list[Analysis],
        previous_plan: DailyPlan | None,
        open_actions: list[Action],
    ) -> DailyPlan: ...


@runtime_checkable
class MeetingRepository(Protocol):
    # meetings
    def create(self, meeting: Meeting) -> None: ...
    def save_meta(self, meeting: Meeting) -> None: ...
    def load_meta(self, meeting_id: str) -> Meeting: ...
    def list_meetings(self) -> list[Meeting]: ...
    def exists(self, meeting_id: str) -> bool: ...
    # meeting files
    def files(self, meeting_id: str) -> set[str]: ...
    def path(self, meeting_id: str, filename: str) -> Path: ...
    def delete_file(self, meeting_id: str, filename: str) -> None: ...
    def delete_meeting(self, meeting_id: str) -> None: ...
    def lock(self, meeting_id: str) -> AbstractContextManager[None]: ...
    # active recording (at most one at a time)
    def save_active(self, active: ActiveRecording) -> None: ...
    def load_active(self) -> ActiveRecording | None: ...
    def clear_active(self) -> None: ...
    # artifacts
    def save_transcript(self, meeting_id: str, transcript: Transcript) -> None: ...
    def load_transcript(self, meeting_id: str) -> Transcript: ...
    def save_analysis(self, meeting_id: str, analysis: Analysis) -> None: ...
    def load_analysis(self, meeting_id: str) -> Analysis: ...
    def mark_failed(self, meeting_id: str, message: str) -> None: ...
    def clear_failed(self, meeting_id: str) -> None: ...
    # plans
    def save_plan(self, plan: DailyPlan) -> None: ...
    def load_plan(self, day: date) -> DailyPlan | None: ...
    def latest_plan_before(self, day: date) -> DailyPlan | None: ...
    def load_open_actions(self) -> list[Action]: ...
    def save_open_actions(self, actions: list[Action]) -> None: ...


@runtime_checkable
class Notifier(Protocol):
    def notify(self, title: str, body: str) -> None: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...

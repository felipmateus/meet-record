"""Portas da camada de aplicação. Adaptadores concretos vivem em adapters/outbound.

Cada porta é um typing.Protocol: qualquer objeto com os métodos certos serve,
inclusive os fakes usados nos testes.
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
    """Identifica uma captura em andamento: o PID do processo gravador e o arquivo de saída.

    Concreto (não Protocol) de propósito: precisa ser serializado em disco para que
    `trec stop` em outro processo consiga encerrar a captura iniciada por `trec start`.
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


@runtime_checkable
class MicCapture(Protocol):
    def start(self, device: str, out: Path) -> CaptureHandle: ...
    def stop(self, handle: CaptureHandle) -> Path: ...


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
    # reuniões
    def create(self, meeting: Meeting) -> None: ...
    def save_meta(self, meeting: Meeting) -> None: ...
    def load_meta(self, meeting_id: str) -> Meeting: ...
    def list_meetings(self) -> list[Meeting]: ...
    def exists(self, meeting_id: str) -> bool: ...
    # arquivos da reunião
    def files(self, meeting_id: str) -> set[str]: ...
    def path(self, meeting_id: str, filename: str) -> Path: ...
    def delete_file(self, meeting_id: str, filename: str) -> None: ...
    def delete_meeting(self, meeting_id: str) -> None: ...
    def lock(self, meeting_id: str) -> AbstractContextManager[None]: ...
    # gravação em andamento (no máximo uma por vez)
    def save_active(self, active: ActiveRecording) -> None: ...
    def load_active(self) -> ActiveRecording | None: ...
    def clear_active(self) -> None: ...
    # artefatos
    def save_transcript(self, meeting_id: str, transcript: Transcript) -> None: ...
    def load_transcript(self, meeting_id: str) -> Transcript: ...
    def save_analysis(self, meeting_id: str, analysis: Analysis) -> None: ...
    def load_analysis(self, meeting_id: str) -> Analysis: ...
    def mark_failed(self, meeting_id: str, message: str) -> None: ...
    def clear_failed(self, meeting_id: str) -> None: ...
    # planos
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

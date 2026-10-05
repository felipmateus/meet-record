"""File-based meeting repository (decision: state = files).

Layout:
  <data_dir>/recordings/<meeting_id>/{meta.json, audio.m4a, transcript.*, analysis.json, error.txt, .lock}
  <data_dir>/plans/{YYYY-MM-DD.md, YYYY-MM-DD.json, open_actions.json}
Writes are atomic (temporary file + os.replace).
"""
from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator, cast

from teams_recorder.adapters.outbound import codec
from teams_recorder.application.ports import ActiveRecording, CaptureHandle
from teams_recorder.constants import Files
from teams_recorder.domain import (
    Action,
    Analysis,
    DailyPlan,
    Meeting,
    MeetingNotFound,
    RepositoryError,
    Transcript,
)
from teams_recorder.domain.status import ANALYSIS, ERROR, LOCK, META, TRANSCRIPT_JSON, TRANSCRIPT_TXT
from teams_recorder.messages import Err


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + Files.TMP_SUFFIX)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_json(path: Path, data: object) -> None:
    _write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RepositoryError(Err.FILE_MISSING.format(path=path)) from exc
    except json.JSONDecodeError as exc:
        raise RepositoryError(Err.BAD_JSON.format(path=path, error=exc)) from exc


def _read_json(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    if not isinstance(data, dict):
        raise RepositoryError(Err.BAD_JSON.format(path=path, error=type(data).__name__))
    return cast(dict[str, Any], data)


def _read_json_list(path: Path) -> list[Any]:
    data = _load_json(path)
    if not isinstance(data, list):
        raise RepositoryError(Err.BAD_JSON.format(path=path, error=type(data).__name__))
    return data


class FsMeetingRepository:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.recordings = self.data_dir / Files.RECORDINGS_DIR
        self.plans = self.data_dir / Files.PLANS_DIR
        self.recordings.mkdir(parents=True, exist_ok=True)
        self.plans.mkdir(parents=True, exist_ok=True)

    # --- meetings -------------------------------------------------------
    def _dir(self, meeting_id: str) -> Path:
        return self.recordings / meeting_id

    def _require(self, meeting_id: str) -> Path:
        d = self._dir(meeting_id)
        if not d.is_dir():
            raise MeetingNotFound(meeting_id)
        return d

    def create(self, meeting: Meeting) -> None:
        d = self._dir(meeting.id)
        if d.exists():
            raise RepositoryError(Err.MEETING_EXISTS.format(meeting_id=meeting.id))
        d.mkdir(parents=True)
        self.save_meta(meeting)

    def save_meta(self, meeting: Meeting) -> None:
        _write_json(self._require(meeting.id) / META, codec.meeting_to_dict(meeting))

    def load_meta(self, meeting_id: str) -> Meeting:
        return codec.meeting_from_dict(_read_json(self._require(meeting_id) / META))

    def list_meetings(self) -> list[Meeting]:
        meetings: list[Meeting] = []
        for d in sorted(self.recordings.iterdir()):
            if d.is_dir() and (d / META).exists():
                meetings.append(self.load_meta(d.name))
        return meetings

    def exists(self, meeting_id: str) -> bool:
        return self._dir(meeting_id).is_dir()

    # --- files ----------------------------------------------------------
    def files(self, meeting_id: str) -> set[str]:
        return {p.name for p in self._require(meeting_id).iterdir() if not p.name.endswith(Files.TMP_SUFFIX)}

    def path(self, meeting_id: str, filename: str) -> Path:
        return self._require(meeting_id) / filename

    def delete_file(self, meeting_id: str, filename: str) -> None:
        p = self._require(meeting_id) / filename
        if p.exists():
            p.unlink()

    def delete_meeting(self, meeting_id: str) -> None:
        d = self._dir(meeting_id)
        if d.exists():
            shutil.rmtree(d)

    @contextmanager
    def lock(self, meeting_id: str) -> Iterator[None]:
        lock = self._require(meeting_id) / LOCK
        if lock.exists():
            raise RepositoryError(Err.MEETING_LOCKED.format(meeting_id=meeting_id))
        lock.write_text(str(os.getpid()))
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    # --- active recording -----------------------------------------------
    @property
    def _active_path(self) -> Path:
        return self.data_dir / Files.ACTIVE_RECORDING

    def save_active(self, active: ActiveRecording) -> None:
        _write_json(self._active_path, {
            "meeting_id": active.meeting.id,
            "process_handle": {"pid": active.process_handle.pid, "out": str(active.process_handle.out)},
            "mic_handle": {"pid": active.mic_handle.pid, "out": str(active.mic_handle.out)},
        })

    def load_active(self) -> ActiveRecording | None:
        if not self._active_path.exists():
            return None
        data = _read_json(self._active_path)
        try:
            meeting = self.load_meta(str(data["meeting_id"]))
        except MeetingNotFound:
            self.clear_active()  # orphan pointer: the meeting folder is gone
            return None
        return ActiveRecording(
            meeting=meeting,
            process_handle=self._handle_from_dict(data["process_handle"]),
            mic_handle=self._handle_from_dict(data["mic_handle"]),
        )

    @staticmethod
    def _handle_from_dict(d: dict[str, Any]) -> CaptureHandle:
        return CaptureHandle(int(d["pid"]), Path(d["out"]))

    def clear_active(self) -> None:
        self._active_path.unlink(missing_ok=True)

    # --- artifacts ------------------------------------------------------
    def save_transcript(self, meeting_id: str, transcript: Transcript) -> None:
        d = self._require(meeting_id)
        _write_json(d / TRANSCRIPT_JSON, codec.transcript_to_dict(transcript))
        _write_atomic(d / TRANSCRIPT_TXT, transcript.as_timestamped_text() + "\n")

    def load_transcript(self, meeting_id: str) -> Transcript:
        return codec.transcript_from_dict(_read_json(self._require(meeting_id) / TRANSCRIPT_JSON))

    def save_analysis(self, meeting_id: str, analysis: Analysis) -> None:
        _write_json(self._require(meeting_id) / ANALYSIS, codec.analysis_to_dict(analysis))

    def load_analysis(self, meeting_id: str) -> Analysis:
        return codec.analysis_from_dict(_read_json(self._require(meeting_id) / ANALYSIS))

    def mark_failed(self, meeting_id: str, message: str) -> None:
        _write_atomic(self._require(meeting_id) / ERROR, message + "\n")

    def clear_failed(self, meeting_id: str) -> None:
        self.delete_file(meeting_id, ERROR)

    # --- plans ----------------------------------------------------------
    def _plan_json(self, day: date) -> Path:
        return self.plans / Files.PLAN_JSON.format(day=day.isoformat())

    def _plan_md(self, day: date) -> Path:
        return self.plans / Files.PLAN_MARKDOWN.format(day=day.isoformat())

    def save_plan(self, plan: DailyPlan) -> None:
        _write_json(self._plan_json(plan.day), codec.plan_to_dict(plan))
        _write_atomic(self._plan_md(plan.day), plan.markdown)

    def load_plan(self, day: date) -> DailyPlan | None:
        p = self._plan_json(day)
        return codec.plan_from_dict(_read_json(p)) if p.exists() else None

    def latest_plan_before(self, day: date) -> DailyPlan | None:
        candidates = sorted(
            (p for p in self.plans.glob(Files.PLAN_GLOB) if date.fromisoformat(p.stem) < day),
            reverse=True,
        )
        return codec.plan_from_dict(_read_json(candidates[0])) if candidates else None

    def load_open_actions(self) -> list[Action]:
        p = self.plans / Files.OPEN_ACTIONS
        if not p.exists():
            return []
        return [codec.action_from_dict(x) for x in _read_json_list(p)]

    def save_open_actions(self, actions: list[Action]) -> None:
        _write_json(self.plans / Files.OPEN_ACTIONS, [codec.action_to_dict(a) for a in actions])

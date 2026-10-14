"""File-based meeting repository (decision: state = files).

Layout:
  <data_dir>/recordings/<meeting_id>/{meta.json, audio.m4a, transcript.*, analysis.json, error.txt, .lock}
  <data_dir>/plans/{YYYY-MM-DD.md, YYYY-MM-DD.json, open_actions.json}
  <data_dir>/plans/{YYYY-MM-DD.stories.md, YYYY-MM-DD.stories.json}  (user story drafts)
Writes are atomic (temporary file + os.replace).
"""
from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar, cast

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.fs_retry import retry_io
from teams_recorder.application.ports import ActiveRecording, CaptureHandle
from teams_recorder.constants import Files
from teams_recorder.domain import (
    Action,
    Analysis,
    CaptureStats,
    DailyPlan,
    Meeting,
    MeetingNotFound,
    RepositoryError,
    StoryDrafts,
    Transcript,
)
from teams_recorder.domain.status import ANALYSIS, ERROR, LOCK, META, MINUTES, TAP_STATS, TRANSCRIPT_JSON, TRANSCRIPT_TXT
from teams_recorder.messages import Err

T = TypeVar("T")


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + Files.TMP_SUFFIX)
    retry_io(lambda: tmp.write_text(text, encoding="utf-8"), str(tmp))
    retry_io(lambda: os.replace(tmp, path), str(path))


def _write_json(path: Path, data: object) -> None:
    _write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def _load_json(path: Path) -> Any:
    try:
        return json.loads(retry_io(lambda: path.read_text(encoding="utf-8"), str(path)))
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


def _decoded(path: Path, decode: Callable[[Any], T], read: Callable[[Path], Any] = _read_json) -> T:
    """Reads a JSON file and converts it to the domain; a file of the wrong shape (a missing key, an unknown
    enum value such as a verification status, a list where an object belongs) is a RepositoryError naming
    the file, like invalid JSON. AttributeError is deliberately not caught: the codec indexes or checks a
    value before calling a method on it, so one would be a bug in the code, not in the file."""
    return _decode(path, read(path), decode)


def _decode(path: Path, data: Any, decode: Callable[[Any], T]) -> T:
    """`decode(data)`, with a shape error reported against the file `data` was read from (see `_decoded`)."""
    try:
        return decode(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise RepositoryError(Err.BAD_JSON.format(path=path, error=exc)) from exc


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
        return _decoded(self._require(meeting_id) / META, codec.meeting_from_dict)

    def list_meetings(self) -> list[Meeting]:
        return [self.load_meta(meeting_id) for meeting_id in self.meeting_ids()]

    def meeting_ids(self) -> list[str]:
        return [d.name for d in sorted(self.recordings.iterdir()) if d.is_dir() and (d / META).exists()]

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
        retry_io(lambda: lock.write_text(str(os.getpid())), str(lock))
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
        path = self._active_path
        # The meeting first, as before the pointer was decoded strictly: a pointer whose meeting folder is
        # gone is cleared whatever its handles hold, so the daemon's start-up recovery never trips on it.
        data = _read_json(path)
        meeting_id = _decode(path, data, lambda d: str(d["meeting_id"]))
        try:
            meeting = self.load_meta(meeting_id)
        except MeetingNotFound:
            self.clear_active()  # orphan pointer: the meeting folder is gone
            return None
        process_handle = _decode(path, data, lambda d: self._handle_from_dict(d["process_handle"]))
        mic_handle = _decode(path, data, lambda d: self._handle_from_dict(d["mic_handle"]))
        return ActiveRecording(meeting=meeting, process_handle=process_handle, mic_handle=mic_handle)

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

    def load_capture_stats(self, meeting_id: str) -> CaptureStats | None:
        """None when there is no stats file; any other failure to read or parse it is a RepositoryError."""
        path = self._require(meeting_id) / TAP_STATS
        try:
            text = retry_io(lambda: path.read_text(encoding="utf-8"), str(path))
        except FileNotFoundError:
            return None
        except OSError as exc:   # permission, a directory in its place, a transient errno that outlasted the retries
            raise RepositoryError(Err.FILE_UNREADABLE.format(path=path, error=exc)) from exc
        try:
            return codec.capture_stats_from_dict(json.loads(text))
        except (KeyError, TypeError, ValueError) as exc:   # ValueError covers JSONDecodeError
            raise RepositoryError(Err.BAD_JSON.format(path=path, error=exc)) from exc

    def load_transcript(self, meeting_id: str) -> Transcript:
        return _decoded(self._require(meeting_id) / TRANSCRIPT_JSON, codec.transcript_from_dict)

    def save_analysis(self, meeting_id: str, analysis: Analysis) -> None:
        _write_json(self._require(meeting_id) / ANALYSIS, codec.analysis_to_dict(analysis))

    def load_analysis(self, meeting_id: str) -> Analysis:
        return _decoded(self._require(meeting_id) / ANALYSIS, codec.analysis_from_dict)

    def save_minutes(self, meeting_id: str, markdown: str) -> None:
        _write_atomic(self._require(meeting_id) / MINUTES, markdown)

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
        return _decoded(p, codec.plan_from_dict) if p.exists() else None

    def _dated(self, pattern: str) -> list[tuple[date, Path]]:
        """Files in plans/ matching the pattern, with the ISO day their name starts with, oldest first."""
        found: list[tuple[date, Path]] = []
        for p in retry_io(lambda: list(self.plans.glob(pattern)), str(self.plans)):
            try:
                found.append((date.fromisoformat(p.name.split(".")[0]), p))
            except ValueError:  # a name that only looks like a day (e.g. 2026-13-45)
                continue
        return sorted(found)

    def latest_plan_before(self, day: date) -> DailyPlan | None:
        earlier = [p for d, p in self._dated(Files.PLAN_GLOB) if d < day]
        return _decoded(earlier[-1], codec.plan_from_dict) if earlier else None

    def load_open_actions(self) -> list[Action]:
        p = self.plans / Files.OPEN_ACTIONS
        if not p.exists():
            return []
        return _decoded(p, lambda items: [codec.action_from_dict(x) for x in items], _read_json_list)

    def save_open_actions(self, actions: list[Action]) -> None:
        _write_json(self.plans / Files.OPEN_ACTIONS, [codec.action_to_dict(a) for a in actions])

    # --- user story drafts --------------------------------------------------
    def _stories_json(self, day: date) -> Path:
        return self.plans / Files.STORIES_JSON.format(day=day.isoformat())

    def save_story_drafts(self, drafts: StoryDrafts, markdown: str) -> None:
        _write_json(self._stories_json(drafts.day), codec.story_drafts_to_dict(drafts))
        _write_atomic(self.plans / Files.STORIES_MARKDOWN.format(day=drafts.day.isoformat()), markdown)

    @staticmethod
    def _load_drafts(path: Path) -> StoryDrafts:
        return _decoded(path, codec.story_drafts_from_dict)

    def load_story_drafts(self, day: date) -> StoryDrafts | None:
        p = self._stories_json(day)
        return self._load_drafts(p) if p.exists() else None

    def recent_story_drafts(self, before: date, days: int) -> list[StoryDrafts]:
        start = before - timedelta(days=days)
        return [self._load_drafts(p) for d, p in self._dated(Files.STORIES_GLOB) if start <= d < before]

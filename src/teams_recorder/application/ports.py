"""Application-layer ports. Concrete adapters live in adapters/outbound.

Each port is a typing.Protocol: any object with the right methods qualifies,
including the fakes used in tests.
"""
from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple, Protocol, runtime_checkable

from teams_recorder.domain import (
    Analysis, CaptureStats, ClaimRef, CuratorInput, CuratorOutput, EnergyTimeline, LanguageSample, Meeting, Op, OpFailure,
    PassRecord, SpeakerLog, StoryDrafts, TaggedBlock, Transcript, TranscriptHealth, UserStory, Verification,
)


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
    speakers_handle: CaptureHandle | None = None   # the speaker observer; None when it did not start (reason in speakers.jsonl)


@runtime_checkable
class ProcessAudioCapture(Protocol):
    def start(self, pid: int, out: Path, epoch: float | None = None) -> CaptureHandle: ...  # epoch: shared track origin (Unix s)
    def stop(self, handle: CaptureHandle) -> Path: ...
    def is_running(self, handle: CaptureHandle) -> bool: ...
    def warmup(self) -> bool:
        """Pre-load the recorder (e.g. trigger the macOS permission prompt); True when it responded."""
        ...


@runtime_checkable
class MicCapture(Protocol):
    def start(self, device: str, out: Path, epoch: float | None = None) -> CaptureHandle: ...
    def stop(self, handle: CaptureHandle) -> Path: ...
    def is_running(self, handle: CaptureHandle) -> bool: ...


@runtime_checkable
class SpeakerObserver(Protocol):
    def start(self, out: Path, epoch: float) -> CaptureHandle:
        """Starts reading the Teams windows into `out` (JSON lines); `epoch` is the Unix time every event is relative to.
        Raises SpeakersUnavailable(reason) when it cannot."""
        ...
    def stop(self, handle: CaptureHandle) -> Path: ...
    def stop_stale(self) -> None:
        """Stops an observer left running with no handle to name it (a start that crashed or was interrupted before its
        handle was persisted); nothing when none is. Never raises for an absent one."""
        ...
    def is_running(self, handle: CaptureHandle) -> bool: ...
    def problems(self) -> list[str]:
        """What keeps it from running (binary missing, permission missing); empty when ready. Shown by `trec doctor`."""
        ...


@runtime_checkable
class EnergyMeter(Protocol):
    def measure(self, track: Path) -> EnergyTimeline:
        """RMS level per fixed step over the whole track. Raises CaptureError on failure."""
        ...


@runtime_checkable
class AudioMixer(Protocol):
    def mix(self, tracks: list[Path], out: Path) -> Path: ...


@runtime_checkable
class Transcriber(Protocol):
    def transcribe(self, audio: Path, language: str) -> Transcript: ...


@runtime_checkable
class LanguageDetector(Protocol):
    def detect(self, audio: Path, offsets: Sequence[float], window_seconds: float) -> list[LanguageSample]:
        """One sample per offset, in order. A sample whisper gave no answer for has language None.
        Raises TranscriptionError when the detection could not run at all."""
        ...


class AnalysisContext(Protocol):
    meeting: Meeting


@runtime_checkable
class MeetingAnalyzer(Protocol):
    def analyze(self, transcript: Transcript, meeting: Meeting) -> Analysis: ...


@runtime_checkable
class ClaimVerifier(Protocol):
    def verify(self, meeting: Meeting, analysis: Analysis, transcript: Transcript) -> dict[ClaimRef, Verification]:
        """Checks the analysis's claims against the transcript; a claim it could not judge is unconfirmed.
        Raises on failure (no answer, an invalid one): the caller then leaves the claims unverified."""
        ...


@runtime_checkable
class MinutesRenderer(Protocol):
    def render(self, meeting: Meeting, analysis: Analysis, health: TranscriptHealth | None = None, *, language: str | None = None) -> str:
        """minutes.md; `health` is the transcript's, so a degraded transcript gets a warning banner. `language` is the transcript's:
        a language other than Portuguese gets a line after the date line; None (no transcript) and Portuguese get none."""
        ...


@runtime_checkable
class StoryWriter(Protocol):
    def draft_from_blocks(self, day: date, blocks: list[TaggedBlock], analyses: list[Analysis], existing: list[UserStory]) -> StoryDrafts:
        """Drafts a story for each tagged block of the activities document. `analyses` are the meetings the blocks link to
        (context); `existing` are recent stories, which a block already covered by one of them must not duplicate. A block that
        is not a story ends up in `skipped` with a reason, its `source_line` set; `action_id` holds the block's ref."""
        ...


@runtime_checkable
class StoryRenderer(Protocol):
    def render(self, drafts: StoryDrafts, existing: list[UserStory], degraded: dict[str, TranscriptHealth] | None = None) -> str:
        """The review document, built only from what `*.stories.json` stores: a block story prints its `source_text`, a
        skipped block its `source_line`, a planner-era story its stored meetings. `existing` names the stories that left-out
        duplicates point to; `degraded`, by meeting id, the source meetings whose transcript cannot be trusted (degraded, or
        made from a Teams track recorded at the wrong sample rate), each shown with its warning banner."""
        ...


@runtime_checkable
class StoryPublisher(Protocol):
    """A destination for user stories (a board). Selected by configuration; several can be active."""

    @property
    def destination(self) -> str:
        """The configured destination name, recorded in each Publication."""
        ...

    def publish(self, story: UserStory, day: date) -> str:
        """Creates the story at the destination and returns the destination's id for it. Raises PublishError."""
        ...

    def problems(self) -> list[str]:
        """What keeps the destination from taking stories (shown by `trec doctor`); empty when it is ready."""
        ...


@runtime_checkable
class MeetingRepository(Protocol):
    # meetings
    def create(self, meeting: Meeting) -> None: ...
    def save_meta(self, meeting: Meeting) -> None: ...
    def load_meta(self, meeting_id: str) -> Meeting: ...
    def list_meetings(self) -> list[Meeting]: ...
    def meeting_ids(self) -> list[str]:
        """Ids of every meeting, oldest first, without reading their meta.json (so one damaged meeting cannot hide the others)."""
        ...
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
    def load_capture_stats(self, meeting_id: str) -> CaptureStats | None:
        """teams-tap's counters for the Teams track; None when the recorder wrote none (Windows, or before 2026-10-14)."""
        ...
    def write_speakers_unavailable(self, meeting_id: str, reason: str) -> None:
        """Replaces speakers.jsonl atomically with the single line saying why the observer could not start."""
        ...
    def load_speaker_log(self, meeting_id: str, fallback_epoch: float, end: float) -> SpeakerLog | None:
        """The observer's record; None when there is no speakers.jsonl, RepositoryError when it cannot be read. Times are
        seconds since the epoch of its start event, or since `fallback_epoch` (the meeting's start) without one."""
        ...
    def save_energy(self, meeting_id: str, energy: dict[str, EnergyTimeline]) -> None: ...
    def load_energy(self, meeting_id: str) -> dict[str, EnergyTimeline]:
        """Levels per raw track name (tap.wav, mic.wav); {} when there is no energy.json, RepositoryError when unreadable."""
        ...
    def last_notice_day(self, key: str) -> date | None:
        """The day a once-a-day notice last fired; None when it never did or the record cannot be read."""
        ...
    def save_notice_day(self, key: str, day: date) -> None: ...
    def save_transcript(self, meeting_id: str, transcript: Transcript) -> None: ...
    def load_transcript(self, meeting_id: str) -> Transcript: ...
    def save_analysis(self, meeting_id: str, analysis: Analysis) -> None: ...
    def load_analysis(self, meeting_id: str) -> Analysis: ...
    def save_minutes(self, meeting_id: str, markdown: str) -> None: ...
    def mark_failed(self, meeting_id: str, message: str) -> None: ...
    def clear_failed(self, meeting_id: str) -> None: ...
    def mark_curation_failed(self, meeting_id: str, message: str) -> None:
        """Writes recordings/<id>/curation_error.txt (status.CURATION_ERROR) atomically, without the meeting lock: no other
        step touches it and derive_status ignores it."""
        ...
    def clear_curation_failed(self, meeting_id: str) -> None: ...
    def curation_error(self, meeting_id: str) -> str | None: ...
    # user story drafts (one set per day)
    def save_story_drafts(self, drafts: StoryDrafts, markdown: str) -> None: ...
    def story_drafts_path(self, day: date) -> Path:
        """The review document (`plans/<day>.stories.md`)."""
        ...
    def load_story_drafts(self, day: date) -> StoryDrafts | None: ...
    def recent_story_drafts(self, before: date, days: int) -> list[StoryDrafts]:
        """Drafts of the days in [before - days, before), oldest first."""
        ...


@runtime_checkable
class ActivityCurator(Protocol):
    def curate(self, data: CuratorInput) -> CuratorOutput: ...
    def repair(self, data: CuratorInput, current: str, failures: list[OpFailure]) -> list[Op]:
        """Replacement ops for the failed ones; `current` is the in-memory text after the ops that applied."""
        ...


class VersionFiles(NamedTuple):
    """The files of one committed pass. None means the file does not exist: commit writes no `_base` / `_prevbase` file for it."""

    before: str
    after: str
    base: str | None      # base.md after the pass (None: the pass left no base, an undo of the first pass)
    prevbase: str | None  # base.md as it was when the pass committed (the base the pass read); None for the first pass


@runtime_checkable
class ActivityStore(Protocol):
    def lock(self, wait: bool = True) -> AbstractContextManager[bool]:
        """Serialises passes. Yields False when `wait` is False and the lock is held. On entry, reconciles a commit that a
        hard stop interrupted: rolled forward only when the document's box stamp is not None and equals the stamp of the
        pass's `_after`, rolled back otherwise (a missing stamp is never "replaced")."""
        ...
    def read_document(self) -> str | None: ...
    def read_base(self) -> str | None: ...
    def recent_archive(self, limit: int) -> list[str]:
        """The last `limit` archive entries, newest last, each as its header line and its first line."""
        ...
    def commit(self, before: str, after: str, archived: list[tuple[str, str]], base: str | None, record: PassRecord) -> None:
        """All or nothing for the document, base.md, the archive and the versions: the version files (`_pass.json` holds the
        archive sizes), the archive entries, the document, base.md and, as the commit point, the pass-log line. `archived`
        holds (text, reason); `base=None` deletes base.md and writes no `_base` file. Raises `CommitIncomplete` when it
        failed after the document replace (the pass happened; the next `lock()` finishes it), any other `RepositoryError`
        when it failed before it (nothing was changed)."""
        ...
    def rewrite_document(self, document: str, base: str | None = None) -> None:
        """Replaces the document and, when `base` is given, base.md, with no version files and no pass-log line: for a small edit
        that is not a pass (a story's tag replaced by its link). The caller holds `lock()`; the box is left as it is, so a stamp
        reconciliation is unaffected. Raises `RepositoryError`."""
        ...
    def log_pass(self, record: PassRecord) -> None:
        """Appends the record of a pass that changed nothing (kind skipped_empty or failed) to the pass log, and nothing
        else: no version files, no document or base write. Such a record has no version set, so it can never be undone."""
        ...
    def passes(self) -> list[PassRecord]:
        """The pass log, oldest first; a torn last line counts as absent."""
        ...
    def version(self, name: str) -> VersionFiles: ...
    def version_names(self) -> list[str]:
        """The names of the version sets that have files, oldest first: the committed passes in the keep window and a set a
        commit left unreconciled (its pass-log line is still missing). A new pass or undo never takes one of these names."""
        ...
    def truncate_archive(self, record: PassRecord) -> bool:
        """Truncates record.archive_file to archive_bytes_before only while its size equals archive_bytes_after; False when left in place."""
        ...
    def path(self) -> Path:
        """The document."""
        ...


class ConfirmAnswer(StrEnum):
    KEEP = "keep"            # the user chose to keep the recording
    DISCARD = "discard"      # the user chose to drop it
    NO_ANSWER = "no_answer"  # timed out, or the question could not be shown


@runtime_checkable
class RecordingConfirmation(Protocol):
    def ask(self, meeting: Meeting) -> ConfirmAnswer:
        """Asks whether to keep a recording that just started. Blocks until answered or timed out."""
        ...


@runtime_checkable
class Notifier(Protocol):
    def notify(self, title: str, body: str) -> None: ...


@runtime_checkable
class DiskSpace(Protocol):
    def free_bytes(self) -> int | None:
        """Free space where recordings are written; None when it cannot be read."""
        ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...

"""Domain exceptions. Adapters translate external failures into these classes."""


class TeamsRecorderError(Exception):
    """Base class for every exception in the project."""


class CaptureError(TeamsRecorderError):
    """Failed to start, stop or mix an audio capture."""


class SpeakersUnavailable(CaptureError):
    """The speaker observer cannot run; `reason` is a SpeakerReason value (binary-missing, permission-missing, start-failed)."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


class TranscriptionError(TeamsRecorderError):
    """Audio transcription failed."""


class AnalysisError(TeamsRecorderError):
    """LLM analysis, planning or story drafting failed."""


class PublishError(TeamsRecorderError):
    """Publishing failed: a destination (a board) could not take a story, or the selection was invalid."""


class RepositoryError(TeamsRecorderError):
    """Read or write failure in the meeting repository."""


class CommitIncomplete(RepositoryError):
    """A pass replaced the document but could not write `base.md` or its pass-log line: the pass happened, and the next
    `lock()` finishes it. It is not a failed pass."""


class MeetingNotFound(RepositoryError):
    """The requested meeting does not exist in the repository."""


class CuratorBusy(TeamsRecorderError):
    """The activities curator holds the lock and the caller must not wait (undo)."""


class NothingToUndo(TeamsRecorderError):
    """The pass log holds no pass that can be undone."""


class UndoStale(TeamsRecorderError):
    """The last pass is not the one that was previewed."""

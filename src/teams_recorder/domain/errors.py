"""Domain exceptions. Adapters translate external failures into these classes."""


class TeamsRecorderError(Exception):
    """Base class for every exception in the project."""


class CaptureError(TeamsRecorderError):
    """Failed to start, stop or mix an audio capture."""


class TranscriptionError(TeamsRecorderError):
    """Audio transcription failed."""


class AnalysisError(TeamsRecorderError):
    """LLM analysis, planning or story drafting failed."""


class PublishError(TeamsRecorderError):
    """Publishing failed: a destination (a board) could not take a story, or the selection was invalid."""


class RepositoryError(TeamsRecorderError):
    """Read or write failure in the meeting repository."""


class MeetingNotFound(RepositoryError):
    """The requested meeting does not exist in the repository."""

"""Domain exceptions. Adapters translate external failures into these classes."""


class TeamsRecorderError(Exception):
    """Base class for every exception in the project."""


class CaptureError(TeamsRecorderError):
    """Failed to start, stop or mix an audio capture."""


class TranscriptionError(TeamsRecorderError):
    """Audio transcription failed."""


class AnalysisError(TeamsRecorderError):
    """LLM analysis or planning failed."""


class RepositoryError(TeamsRecorderError):
    """Read or write failure in the meeting repository."""


class MeetingNotFound(RepositoryError):
    """The requested meeting does not exist in the repository."""

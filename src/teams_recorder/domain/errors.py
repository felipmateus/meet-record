"""Exceções do domínio. Adaptadores traduzem erros externos para estas classes."""


class TeamsRecorderError(Exception):
    """Base de todas as exceções do projeto."""


class CaptureError(TeamsRecorderError):
    """Falha ao iniciar, parar ou mixar captura de áudio."""


class TranscriptionError(TeamsRecorderError):
    """Falha na transcrição do áudio."""


class AnalysisError(TeamsRecorderError):
    """Falha na análise ou no planejamento via LLM."""


class RepositoryError(TeamsRecorderError):
    """Falha de leitura ou escrita no repositório de reuniões."""


class MeetingNotFound(RepositoryError):
    """A reunião pedida não existe no repositório."""

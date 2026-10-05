"""Status de uma reunião derivado dos arquivos presentes na sua pasta.

Decisão de arquitetura: o estado do pipeline é a existência dos arquivos,
não um banco. Este módulo é a única fonte da regra de derivação.
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
    """Deriva o status a partir dos nomes de arquivo presentes na pasta da reunião.

    Ordem de precedência: falha explícita > análise > transcrição > áudio final > gravando.
    O áudio pode ter sido apagado pela retenção sem afetar os status posteriores.
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
    """Nome da próxima etapa do pipeline para o status dado, ou None se concluído/falho."""
    return {
        MeetingStatus.RECORDING: "stop",
        MeetingStatus.RECORDED: "transcribe",
        MeetingStatus.TRANSCRIBED: "analyze",
    }.get(status)

"""Asks whether to keep a recording through a macOS dialog (osascript `display dialog`).

The dialog opens centered on the main screen, above other windows, with "Keep recording"
as the default button, so pressing Return keeps it. It closes by itself after the timeout.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Callable

from teams_recorder.application.ports import ConfirmAnswer
from teams_recorder.constants import Bin, Confirm, Parse
from teams_recorder.domain import Meeting
from teams_recorder.messages import Ask, Log

log = logging.getLogger(__name__)

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class DialogRecordingConfirmation:
    def __init__(self, timeout_seconds: int = Confirm.TIMEOUT_SECONDS, runner: Runner = subprocess.run) -> None:
        self.timeout_seconds = timeout_seconds
        self.runner = runner

    def script(self) -> str:
        return Parse.OSASCRIPT_CONFIRM.format(
            body=_esc(Ask.BODY), title=_esc(Ask.TITLE), discard=_esc(Ask.DISCARD), keep=_esc(Ask.KEEP), timeout=self.timeout_seconds,
        )

    def ask(self, meeting: Meeting) -> ConfirmAnswer:
        try:
            result = self.runner(
                [Bin.OSASCRIPT, "-e", self.script()],
                capture_output=True, text=True, check=False, timeout=self.timeout_seconds + Confirm.WAIT_MARGIN,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning(Log.CONFIRM_DIALOG_FAILED, exc)
            return ConfirmAnswer.NO_ANSWER
        return parse_answer(result.stdout or "")


def parse_answer(output: str) -> ConfirmAnswer:
    if Parse.DIALOG_GAVE_UP in output or Parse.DIALOG_BUTTON not in output:
        return ConfirmAnswer.NO_ANSWER
    button = output.split(Parse.DIALOG_BUTTON, 1)[1].split(",", 1)[0].strip()
    if button == Ask.DISCARD:
        return ConfirmAnswer.DISCARD
    if button == Ask.KEEP:
        return ConfirmAnswer.KEEP
    return ConfirmAnswer.NO_ANSWER


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')

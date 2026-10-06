"""Asks whether to keep a recording through a Windows message box (user32 MessageBoxTimeoutW).

Yes keeps it (the default button), No discards it. The box is topmost and takes the
foreground, so it shows over Teams even in full screen, and closes by itself after the
timeout. MessageBoxTimeoutW is exported by user32 since Windows XP but not documented;
if it is missing the question is skipped and the recording kept.
"""
from __future__ import annotations

import logging
import sys
from typing import Callable

from teams_recorder.application.ports import ConfirmAnswer
from teams_recorder.constants import Confirm, Windows
from teams_recorder.domain import Meeting
from teams_recorder.messages import Ask, Log

log = logging.getLogger(__name__)

MessageBox = Callable[[str, str, int, int], int]   # (text, title, flags, timeout ms) -> button id


def answer_for(button: int) -> ConfirmAnswer:
    if button == Windows.IDYES:
        return ConfirmAnswer.KEEP
    if button == Windows.IDNO:
        return ConfirmAnswer.DISCARD
    return ConfirmAnswer.NO_ANSWER     # MB_TIMEDOUT, or the box failed (0)


class MessageBoxRecordingConfirmation:
    def __init__(self, timeout_seconds: int = Confirm.TIMEOUT_SECONDS, message_box: MessageBox | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.message_box = message_box

    def ask(self, meeting: Meeting) -> ConfirmAnswer:
        try:
            box = self.message_box or _message_box_timeout
            return answer_for(box(Ask.BODY_WINDOWS, Ask.TITLE, Windows.MB_FLAGS, self.timeout_seconds * 1000))
        except (OSError, AttributeError) as exc:
            log.warning(Log.CONFIRM_DIALOG_FAILED, exc)
            return ConfirmAnswer.NO_ANSWER


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    def _message_box_timeout(text: str, title: str, flags: int, timeout_ms: int) -> int:
        fn = ctypes.WinDLL("user32", use_last_error=True).MessageBoxTimeoutW
        fn.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT, wintypes.WORD, wintypes.DWORD]
        fn.restype = ctypes.c_int
        return int(fn(None, text, title, flags, 0, timeout_ms))

else:
    def _message_box_timeout(text: str, title: str, flags: int, timeout_ms: int) -> int:
        raise OSError(sys.platform)

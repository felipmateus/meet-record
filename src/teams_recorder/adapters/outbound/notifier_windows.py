"""Notifications on Windows: a toast through Windows PowerShell (no extra dependency).

The toast is shown under PowerShell's registered app id, so Windows labels it "Windows
PowerShell"; the title line carries the app name instead.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Callable

from teams_recorder.constants import APP_NAME, Bin, Proc, Windows
from teams_recorder.messages import Log

log = logging.getLogger(__name__)

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


class ToastNotifier:
    def __init__(self, app_title: str = APP_NAME, runner: Runner = subprocess.run) -> None:
        self.app_title = app_title
        self.runner = runner

    def script(self, title: str, body: str) -> str:
        return Windows.TOAST_SCRIPT.format(title=_ps(f"{self.app_title}: {title}"), body=_ps(body), app_id=Windows.TOAST_APP_ID)

    def notify(self, title: str, body: str) -> None:
        try:
            self.runner(
                [Bin.POWERSHELL, *Windows.POWERSHELL_ARGS, self.script(title, body)],
                check=False, capture_output=True, timeout=Proc.NOTIFY_TIMEOUT * 3, creationflags=Windows.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:  # a notification never brings down the pipeline
            log.warning(Log.NOTIFICATION_FAILED, exc)


def _ps(text: str) -> str:
    """Escape for a single-quoted PowerShell string; newlines become spaces."""
    return text.replace("'", "''").replace("\r", " ").replace("\n", " ")

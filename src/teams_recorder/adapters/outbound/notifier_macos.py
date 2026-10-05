"""Notifications in the macOS Notification Center via osascript."""
from __future__ import annotations

import logging
import subprocess

from teams_recorder.constants import APP_NAME, Bin, Parse, Proc
from teams_recorder.messages import Log

log = logging.getLogger(__name__)


class MacOSNotifier:
    def __init__(self, app_title: str = APP_NAME) -> None:
        self.app_title = app_title

    def notify(self, title: str, body: str) -> None:
        script = Parse.OSASCRIPT_NOTIFY.format(body=_esc(body), title=_esc(self.app_title), subtitle=_esc(title))
        try:
            subprocess.run([Bin.OSASCRIPT, "-e", script], check=False, capture_output=True, timeout=Proc.NOTIFY_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:  # a notification never brings down the pipeline
            log.warning(Log.NOTIFICATION_FAILED, exc)


class LogNotifier:
    """For environments without a graphical interface (tests, CI)."""

    def notify(self, title: str, body: str) -> None:
        log.info(Log.LOG_NOTIFICATION, title, body)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')

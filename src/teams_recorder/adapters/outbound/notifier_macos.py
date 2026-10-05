"""Notifications in the macOS Notification Center via osascript."""
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)


class MacOSNotifier:
    def __init__(self, app_title: str = "teams-recorder") -> None:
        self.app_title = app_title

    def notify(self, title: str, body: str) -> None:
        script = f'display notification "{_esc(body)}" with title "{_esc(self.app_title)}" subtitle "{_esc(title)}"'
        try:
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:  # a notification never brings down the pipeline
            log.warning("notification failed: %s", exc)


class LogNotifier:
    """For environments without a graphical interface (tests, CI)."""

    def notify(self, title: str, body: str) -> None:
        log.info("[%s] %s", title, body)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')

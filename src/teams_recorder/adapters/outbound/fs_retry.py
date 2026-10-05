"""Retry for file operations that macOS TCC can transiently block from background processes.

Under launchd, touching files in ~/Documents (prompts, recordings, logs) occasionally fails
with "[Errno 11] Resource deadlock avoided" (EDEADLK) and succeeds moments later. Observed on
2026-10-05 when the daemon read prompts/analyze_system.md. Only transient errnos are retried.
"""
from __future__ import annotations

import errno
import logging
import time
from collections.abc import Callable
from typing import TypeVar

from teams_recorder.constants import Proc
from teams_recorder.messages import Log

log = logging.getLogger(__name__)
T = TypeVar("T")

TRANSIENT_ERRNOS = frozenset({errno.EDEADLK, errno.EAGAIN, errno.ETXTBSY})


def retry_io(operation: Callable[[], T], what: str, *, attempts: int = Proc.IO_RETRIES, delay: float = Proc.IO_RETRY_DELAY,
             sleep: Callable[[float], None] = time.sleep) -> T:
    """Run `operation`, retrying while it raises a transient OSError; re-raise anything else."""
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except OSError as exc:
            if exc.errno not in TRANSIENT_ERRNOS or attempt == attempts:
                raise
            log.warning(Log.IO_RETRY, what, exc.strerror, attempt, attempts)
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover

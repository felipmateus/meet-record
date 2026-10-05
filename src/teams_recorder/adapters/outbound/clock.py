"""Wall-clock implementation of the Clock port (second precision: timestamps become file names)."""
from __future__ import annotations

from datetime import datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now().replace(microsecond=0)

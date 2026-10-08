"""DiskSpace: free bytes on the volume that holds the data folder."""
from __future__ import annotations

import shutil
from pathlib import Path


class DataDirDiskSpace:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def free_bytes(self) -> int | None:
        probe = self.path
        while not probe.exists() and probe != probe.parent:   # the data dir may not exist yet
            probe = probe.parent
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            return None

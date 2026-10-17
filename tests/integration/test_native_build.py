"""The teams-speakers helper type-checks: docs/tasks/speaker-attribution/_tests.md IT-006."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
SOURCE = Path(__file__).resolve().parents[2] / "native" / "teams-speakers" / "Sources" / "teams-speakers" / "main.swift"


@pytest.mark.skipif(shutil.which("swiftc") is None, reason="swiftc not installed")
def test_it006_the_helper_typechecks():
    result = subprocess.run(["swiftc", "-typecheck", str(SOURCE)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr

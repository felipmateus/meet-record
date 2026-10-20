"""IT-018: `scripts/install.sh --dry-run` no longer offers the 6 pm planner and says it removes the old job when it is there.

The script runs from a throwaway copy of the project (its scripts and config.toml, the repo's virtualenv linked in) with a
throwaway HOME, so the dry run reads nothing of the real project or LaunchAgents; a dry run changes nothing."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from teams_recorder.constants import Legacy

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("brew") is None or shutil.which("swift") is None or not (REPO / ".venv").exists(),
    reason="the macOS installer's dry run needs macOS, Homebrew, the Swift toolchain and the project's virtualenv",
)


def _dry_run(tmp_path: Path, *, legacy_job: bool) -> str:
    project = tmp_path / "proj"
    (project / "scripts").mkdir(parents=True)
    for name in ("install.sh", "config_tool.py"):
        shutil.copy2(REPO / "scripts" / name, project / "scripts" / name)
    shutil.copy2(REPO / "config.toml", project / "config.toml")
    (project / ".venv").symlink_to(REPO / ".venv")
    home = tmp_path / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    if legacy_job:
        (agents / f"{Legacy.PLANNER_LABEL}.plist").write_bytes(b"x")
    env = {**os.environ, "HOME": str(home), "HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ANALYTICS": "1", "NO_COLOR": "1"}
    done = subprocess.run(["bash", str(project / "scripts" / "install.sh"), "--dry-run", "--yes", "--skip-model"], env=env, cwd=project,
                          capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Dry run finished" in done.stdout
    return done.stdout + done.stderr


def test_the_dry_run_lists_removing_the_old_planner_job_when_it_is_installed(tmp_path: Path):
    output = _dry_run(tmp_path, legacy_job=True)
    assert "6 pm" not in output and "and planner" not in output
    assert f"the old daily planner job ({Legacy.PLANNER_LABEL}) is removed by the install" in output
    assert "(dry run)" in output and "agent install" in output


def test_the_dry_run_does_not_mention_the_planner_when_there_is_none(tmp_path: Path):
    output = _dry_run(tmp_path, legacy_job=False)
    assert "planner" not in output.lower() and "6 pm" not in output

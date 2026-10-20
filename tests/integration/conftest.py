import json
import logging
import subprocess
from pathlib import Path

import pytest

from teams_recorder.constants import Stories

BACKLOG_INIT = ["backlog", "init", "Throwaway", "--no-git", "--defaults", "--integration-mode", "none", "--auto-open-browser", "false"]


@pytest.fixture
def throwaway_board(tmp_path: Path) -> Path:
    """A real Backlog.md project in a temporary folder, with the review column added (opt-in tests only)."""
    board = tmp_path / "board"
    board.mkdir()
    subprocess.run(BACKLOG_INIT, cwd=board, check=True, capture_output=True)
    config = board / "backlog" / "config.yml"
    config.write_text(config.read_text().replace('statuses: ["To Do"', f'statuses: ["{Stories.BACKLOG_STATUS}", "To Do"'))
    assert f'"{Stories.BACKLOG_STATUS}"' in config.read_text(), "Backlog.md changed its config format"
    return board


def board_tasks(board: Path) -> list[dict]:
    listed = subprocess.run(["backlog", "task", "list", "--json"], cwd=board, check=True, capture_output=True, text=True).stdout
    return list(json.loads(listed)["tasks"])


@pytest.fixture(autouse=True)
def _undo_root_logging_changes():
    """`trec daemon` (run through the CLI runner by some tests) installs a stream handler on the root logger that writes to the
    runner's captured stream; once that stream is closed, every later log line of a CLI test prints a "Logging error" into its
    output. Takes back what a test added to the root logger (pytest's own capture handlers aside) and its level."""
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in before and not type(handler).__module__.startswith("_pytest"):
            root.removeHandler(handler)
    root.setLevel(level)

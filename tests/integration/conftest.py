import json
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

"""Real Backlog.md CLI in a throwaway project. Opt-in: TREC_REAL_BACKLOG=1 (needs `backlog` on PATH)."""
import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher, GitIgnore
from teams_recorder.domain import Priority, UserStory

ready = os.environ.get("TREC_REAL_BACKLOG") == "1" and shutil.which("backlog")

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not ready, reason="set TREC_REAL_BACKLOG=1 (requires the backlog CLI)")]


def test_real_backlog_takes_a_story_in_triagem(tmp_path: Path):
    init = ["backlog", "init", "Spike", "--no-git", "--defaults", "--integration-mode", "none", "--auto-open-browser", "false"]
    subprocess.run(init, cwd=tmp_path, check=True, capture_output=True)
    config = tmp_path / "backlog" / "config.yml"
    config.write_text(config.read_text().replace('statuses: ["To Do"', 'statuses: ["Triagem", "To Do"'))
    story = UserStory("-x Exportar horas por projeto", "Como gestor, quero exportar horas, para fechar o mês.",
                      acceptance_criteria=["Dado um projeto, quando exporto, então recebo um CSV",
                                           "Dado um mês vazio, quando exporto, então vejo um aviso"],
                      source_action_ids=["a1"], source_meetings=["2026-10-09_10-00-00"], priority=Priority.HIGH)
    publisher = BacklogMdPublisher(tmp_path, ignore_state=lambda p: GitIgnore.OUTSIDE_GIT)

    assert publisher.problems() == []
    ref = publisher.publish(story, date(2026, 10, 9))

    listed = json.loads(subprocess.run(["backlog", "task", "list", "--json"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout)
    task = next(t for t in listed["tasks"] if t["id"] == ref)
    assert task["status"] == "Triagem" and task["acceptanceCriteriaCount"] == 2 and task["priority"] == "high"
    assert "2026-10-09" in task["labels"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["backlog"]        # nothing written outside the board

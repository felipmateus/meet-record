"""BacklogMdPublisher against a scripted `backlog` on PATH, and the real `git check-ignore`."""
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher, GitIgnore, git_ignore_state
from teams_recorder.config import find_tool
from teams_recorder.domain import Priority, PublishError, UserStory

FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_backlog_cli.py"
CONFIG = 'statuses: ["Triagem", "To Do", "In Progress", "Done"]\nauto_commit: false\nremote_operations: false\n'
DAY = date(2026, 10, 9)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in is a POSIX shell wrapper")


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "backlog"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_BACKLOG_LOG", str(tmp_path / "calls.jsonl"))
    (tmp_path / "board" / "backlog").mkdir(parents=True)
    (tmp_path / "board" / "backlog" / "config.yml").write_text(CONFIG, encoding="utf-8")
    return tmp_path / "board"


def _publisher(project: Path) -> BacklogMdPublisher:
    return BacklogMdPublisher(project, binary=find_tool("backlog", project), ignore_state=lambda p: GitIgnore.OUTSIDE_GIT)


def _calls(project: Path) -> list[dict]:
    return [json.loads(line) for line in (project.parent / "calls.jsonl").read_text(encoding="utf-8").splitlines()]


def test_arguments_reach_the_cli_intact(project: Path):
    story = UserStory("-x Exportar relatório de horas", "Como gestor, quero exportar,\npara fechar o mês.",
                      acceptance_criteria=["Dado um projeto, quando exporto, então recebo um CSV"], priority=Priority.LOW)
    publisher = _publisher(project)

    assert publisher.publish(story, DAY) == "TASK-1"
    assert publisher.publish(story, DAY) == "TASK-2"

    call = _calls(project)[0]
    assert Path(call["cwd"]).resolve() == project.resolve()
    args = call["args"]
    assert args[-1] == "-x Exportar relatório de horas"
    assert args[args.index("--desc") + 1].startswith("Como gestor, quero exportar,\npara fechar o mês.")
    assert args[args.index("--ac") + 1] == "Dado um projeto, quando exporto, então recebo um CSV"


def test_a_failing_cli_is_a_publish_error(project: Path, monkeypatch):
    monkeypatch.setenv("FAKE_BACKLOG_MODE", "fail")
    with pytest.raises(PublishError, match="Invalid status"):
        _publisher(project).publish(UserStory("T", "n"), DAY)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_ignore_state(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "backlog").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert git_ignore_state(repo / "backlog") is GitIgnore.NOT_IGNORED
    (repo / ".gitignore").write_text("backlog/\n")
    assert git_ignore_state(repo / "backlog") is GitIgnore.IGNORED
    (tmp_path / "outside" / "backlog").mkdir(parents=True)
    assert git_ignore_state(tmp_path / "outside" / "backlog") is GitIgnore.OUTSIDE_GIT

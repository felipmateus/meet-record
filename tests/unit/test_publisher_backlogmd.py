import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher, GitIgnore, git_ignore_state
from teams_recorder.constants import StoryDestination
from teams_recorder.domain import Priority, PublishError, UserStory
from teams_recorder.messages import Err, StoryDoc

DAY = date(2026, 10, 9)
PLAIN = "File: /p/backlog/tasks/task-7 - Exportar.md\n\nTask TASK-7 - Exportar horas\n=====\n\nStatus: ○ Triagem\n"
CONFIG = 'project_name: "teams-recorder"\nstatuses: ["Triagem", "To Do", "In Progress", "Done"]\nauto_commit: false\nremote_operations: false\n'
BINARY = sys.executable   # any executable on disk: problems() only checks that the binary resolves


def _story(**kw) -> UserStory:
    defaults = dict(
        title="Exportar horas por projeto", narrative="Como gestor, quero exportar horas, para fechar o mês.",
        acceptance_criteria=["Dado um projeto, quando exporto, então recebo um CSV", "Dado um mês vazio, quando exporto, então vejo um aviso"],
        details="**Contexto:** fechamento mensal", open_questions=["Qual separador usar?"],
        source_action_ids=["a1", "a2"], source_meetings=["2026-10-09_10-00-00"], priority=Priority.HIGH,
    )
    return UserStory(**{**defaults, **kw})


def _project(tmp_path: Path, config: str = CONFIG) -> Path:
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text(config, encoding="utf-8")
    return tmp_path


def _publisher(project: Path | None, answer=None, state=GitIgnore.IGNORED, **kw):
    """A publisher with a scripted runner; returns it and the list of (command, kwargs) it was called with."""
    calls: list[tuple[list[str], dict]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return answer(command) if answer else subprocess.CompletedProcess(command, 0, PLAIN, "")

    return BacklogMdPublisher(project, binary=BINARY, runner=runner, ignore_state=lambda p: state, **kw), calls


def test_command_shape():
    publisher = BacklogMdPublisher(Path("/p"), labels=("teams-recorder", "work"))
    cmd = publisher.command(_story(), DAY)

    assert cmd[:3] == ["backlog", "task", "create"] and cmd[-3:] == ["--plain", "--", "Exportar horas por projeto"]
    assert cmd[cmd.index("-s") + 1] == "Triagem"
    assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "-l"] == ["teams-recorder", "work", "2026-10-09"]
    assert cmd[cmd.index("--priority") + 1] == "high"
    assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "--ac"] == _story().acceptance_criteria   # commas kept, one each
    assert "--priority" not in publisher.command(_story(priority=None), DAY)
    assert publisher.command(_story(title="-s weird"), DAY)[-2:] == ["--", "-s weird"]               # never read as a flag


def test_body_carries_the_story_and_its_origin():
    body = BacklogMdPublisher(Path("/p"), drafts_dir=Path("/d/plans")).body(_story(), DAY)

    assert body.startswith("Como gestor, quero exportar horas, para fechar o mês.\n\n**Contexto:** fechamento mensal")
    assert StoryDoc.QUESTIONS + "\n- Qual separador usar?" in body
    assert StoryDoc.BOARD_ORIGIN.format(day="2026-10-09", meetings="2026-10-09_10-00-00", actions="`a1`, `a2`") in body
    assert body.endswith(StoryDoc.BOARD_DRAFTS.format(path=Path("/d/plans/2026-10-09.stories.md")))
    assert "**Contexto:**" not in BacklogMdPublisher(Path("/p")).body(_story(details="", open_questions=[]), DAY)


def test_publish_returns_the_task_id_and_runs_in_the_project(tmp_path: Path):
    publisher, calls = _publisher(_project(tmp_path))
    assert publisher.publish(_story(), DAY) == "TASK-7"
    assert calls[0][1]["cwd"] == tmp_path and calls[0][1]["encoding"] == "utf-8"
    assert publisher.destination == StoryDestination.BACKLOG_MD


@pytest.mark.parametrize(("raised", "message"), [
    (FileNotFoundError("backlog"), Err.BACKLOG_BINARY_MISSING.format(binary=BINARY)),
    (subprocess.TimeoutExpired("backlog", 60), Err.BACKLOG_TIMEOUT.format(seconds=60)),
    (PermissionError("denied"), Err.BACKLOG_EXEC.format(binary=BINARY, error="denied")),
])
def test_spawn_failures_become_publish_errors(tmp_path: Path, raised, message):
    def answer(command):
        raise raised
    publisher, _ = _publisher(_project(tmp_path), answer)
    with pytest.raises(PublishError, match=re.escape(message)):
        publisher.publish(_story(), DAY)


def test_cli_failure_and_missing_id(tmp_path: Path):
    project = _project(tmp_path)
    failing, _ = _publisher(project, lambda c: subprocess.CompletedProcess(c, 1, "line 1\nInvalid status: X\n", "boom\n"))
    with pytest.raises(PublishError, match=re.escape(Err.BACKLOG_FAILED.format(code=1, tail="line 1 | Invalid status: X | boom"))):
        failing.publish(_story(), DAY)
    silent, _ = _publisher(project, lambda c: subprocess.CompletedProcess(c, 0, "Created.\n", ""))
    with pytest.raises(PublishError, match=re.escape(Err.BACKLOG_NO_ID.format(tail="Created."))):
        silent.publish(_story(), DAY)


def test_problems_on_a_ready_project_and_outside_git(tmp_path: Path):
    assert _publisher(_project(tmp_path))[0].problems() == []
    assert _publisher(tmp_path, state=GitIgnore.OUTSIDE_GIT)[0].problems() == []
    assert _publisher(tmp_path, status="triagem")[0].problems() == []          # the CLI matches columns case-insensitively


def test_problems_name_what_is_missing(tmp_path: Path):
    assert _publisher(None)[0].problems() == [Err.BACKLOG_PROJECT_UNSET]
    assert _publisher(tmp_path / "nope")[0].problems() == [Err.BACKLOG_PROJECT_MISSING.format(path=tmp_path / "nope")]
    assert _publisher(tmp_path)[0].problems() == [Err.BACKLOG_NOT_INITIALIZED.format(path=tmp_path)]
    no_binary = BacklogMdPublisher(_project(tmp_path), binary="no-such-backlog-binary", ignore_state=lambda p: GitIgnore.IGNORED)
    assert no_binary.problems() == [Err.BACKLOG_BINARY_MISSING.format(binary="no-such-backlog-binary")]


def test_problems_with_the_board_configuration(tmp_path: Path):
    config = tmp_path / "backlog" / "config.yml"
    unsafe = CONFIG.replace('"Triagem", ', "").replace("remote_operations: false", "remote_operations: true")
    publisher, _ = _publisher(_project(tmp_path, unsafe), labels=("teams-recorder", "a,b"))
    assert publisher.problems() == [
        Err.BACKLOG_LABEL_SEPARATOR.format(label="a,b"),
        Err.BACKLOG_STATUS_MISSING.format(status="Triagem", config=config),
        Err.BACKLOG_GIT_ON.format(config=config),
    ]
    auto_commit = CONFIG.replace("auto_commit: false", "auto_commit: true")
    (tmp_path / "backlog" / "config.yml").write_text(auto_commit, encoding="utf-8")
    assert publisher.problems()[-1] == Err.BACKLOG_GIT_ON.format(config=config)


def test_windows_command_shims_are_refused(tmp_path: Path):
    shim = tmp_path / "backlog.cmd"
    shim.write_text("@echo off\n")
    shim.chmod(0o755)
    publisher = BacklogMdPublisher(_project(tmp_path), binary=str(shim), ignore_state=lambda p: GitIgnore.IGNORED)
    assert publisher.problems() == [Err.BACKLOG_SHIM.format(binary=shim)]


@pytest.mark.parametrize(("state", "message"), [
    (GitIgnore.NOT_IGNORED, Err.BACKLOG_NOT_IGNORED),
    (GitIgnore.UNKNOWN, Err.BACKLOG_IGNORE_UNKNOWN),       # fails closed when git cannot answer
])
def test_a_board_git_could_version_is_refused(tmp_path: Path, state, message):
    publisher, calls = _publisher(_project(tmp_path), state=state)
    expected = message.format(path=tmp_path / "backlog")
    assert publisher.problems() == [expected]
    with pytest.raises(PublishError, match=re.escape(expected)):
        publisher.publish(_story(), DAY)
    assert calls == []                                      # nothing written


def test_root_config_checks_the_config_file_and_the_tasks_folder(tmp_path: Path):
    (tmp_path / "backlog.config.yml").write_text(CONFIG, encoding="utf-8")
    seen: list[Path] = []

    def state(path):
        seen.append(path)
        return GitIgnore.IGNORED

    assert BacklogMdPublisher(tmp_path, binary=BINARY, ignore_state=state).problems() == []
    assert seen == [tmp_path / "backlog.config.yml", tmp_path / "backlog"]


def test_git_ignore_state_without_git(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    def dubious_ownership(command, **kwargs):
        return subprocess.CompletedProcess(command, 128, b"", b"fatal: detected dubious ownership")

    assert git_ignore_state(tmp_path / "backlog", runner=missing) is GitIgnore.UNKNOWN
    assert git_ignore_state(tmp_path / "backlog", runner=dubious_ownership) is GitIgnore.UNKNOWN

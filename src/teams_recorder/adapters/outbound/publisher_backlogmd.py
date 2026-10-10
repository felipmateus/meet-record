"""StoryPublisher for a local Backlog.md project (a Markdown kanban), through the `backlog` CLI.

Each story becomes one task in the configured status (the Triagem column), where the user
reviews it: moving it to To Do approves it, archiving it rejects it. This adapter only
creates tasks; it never edits, moves or deletes them.

The project may live inside this repository's folder, which is public, only while Git
ignores it. The check fails closed: inside a Git work tree, a board that Git would version,
or one whose status Git cannot confirm (git missing, an error), is reported by problems()
and refused by publish(); so is a Backlog.md configuration that commits or reaches remotes.
The flags and the output format were confirmed against Backlog.md 1.53.0 (techspec §9).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from teams_recorder.adapters.outbound.fs_retry import retry_io
from teams_recorder.adapters.outbound.process_control import NO_WINDOW
from teams_recorder.constants import BacklogMd, Bin, Files, Parse, Stories, StoryDestination
from teams_recorder.domain import PublishError, UserStory
from teams_recorder.messages import Err, StoryDoc


class GitIgnore(StrEnum):
    IGNORED = "ignored"
    NOT_IGNORED = "not_ignored"
    OUTSIDE_GIT = "outside_git"   # no Git work tree around the path: nothing could version it
    UNKNOWN = "unknown"           # inside a work tree, but git could not answer (missing, error)


def git_ignore_state(path: Path, runner: Callable[..., Any] = subprocess.run) -> GitIgnore:
    if not any((parent / BacklogMd.GIT_MARKER).exists() for parent in (path, *path.parents)):
        return GitIgnore.OUTSIDE_GIT
    try:
        result = runner(
            [Bin.GIT, BacklogMd.GIT_DIR, str(path.parent), *BacklogMd.GIT_CHECK_IGNORE, str(path)],
            capture_output=True, timeout=BacklogMd.TIMEOUT, check=False, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return GitIgnore.UNKNOWN
    if result.returncode == BacklogMd.GIT_IGNORED:
        return GitIgnore.IGNORED
    if result.returncode == BacklogMd.GIT_NOT_IGNORED:
        return GitIgnore.NOT_IGNORED
    return GitIgnore.UNKNOWN


@dataclass
class BacklogMdPublisher:
    project_dir: Path | None
    status: str = Stories.BACKLOG_STATUS
    labels: tuple[str, ...] = Stories.BACKLOG_LABELS
    drafts_dir: Path | None = None   # the plans folder, for the link back to the drafts document
    binary: str = Bin.BACKLOG
    runner: Callable[..., Any] = field(default=subprocess.run)
    ignore_state: Callable[[Path], GitIgnore] = field(default=git_ignore_state)
    destination: StoryDestination = StoryDestination.BACKLOG_MD

    def command(self, story: UserStory, day: date) -> list[str]:
        cmd = [self.binary, *BacklogMd.CREATE, BacklogMd.DESC, self.body(story, day), BacklogMd.STATUS, self.status]
        kind = [story.kind.value] if story.kind else []
        for label in (*self.labels, *kind, day.isoformat()):
            cmd += [BacklogMd.LABEL, label]
        if story.priority is not None:
            cmd += [BacklogMd.PRIORITY, story.priority.value]
        for criterion in story.acceptance_criteria:  # one --ac each: criteria keep their commas
            cmd += [BacklogMd.AC, criterion]
        return [*cmd, BacklogMd.PLAIN, BacklogMd.END_OF_OPTIONS, story.title]

    def body(self, story: UserStory, day: date) -> str:
        """The task description: the story sentence, the guide's other sections, open questions and where it came from."""
        parts = [story.narrative, story.details]
        if story.open_questions:
            parts.append("\n".join([StoryDoc.QUESTIONS, *(StoryDoc.BULLET.format(text=q) for q in story.open_questions)]))
        parts.append(StoryDoc.BOARD_ORIGIN.format(
            day=day.isoformat(),
            meetings=", ".join(story.source_meetings),
            actions=", ".join(StoryDoc.ACTION_REF.format(id=i) for i in story.source_action_ids),
        ))
        if self.drafts_dir is not None:
            parts.append(StoryDoc.BOARD_DRAFTS.format(path=self.drafts_dir / Files.STORIES_MARKDOWN.format(day=day.isoformat())))
        return "\n\n".join(p for p in parts if p)

    def publish(self, story: UserStory, day: date) -> str:
        problems = self.problems()
        if problems or self.project_dir is None:
            raise PublishError("; ".join(problems))
        output = self._create(self.command(story, day), self.project_dir)
        task_id = re.search(Parse.BACKLOG_TASK_ID, output, re.MULTILINE)
        if task_id is None:
            raise PublishError(Err.BACKLOG_NO_ID.format(tail=_tail(output)))
        return task_id.group(1)

    def problems(self) -> list[str]:
        problems: list[str] = []
        if shutil.which(self.binary) is None:
            problems.append(Err.BACKLOG_BINARY_MISSING.format(binary=self.binary))
        elif Path(self.binary).suffix.lower() in BacklogMd.SHIM_SUFFIXES:
            problems.append(Err.BACKLOG_SHIM.format(binary=self.binary))
        problems += [Err.BACKLOG_LABEL_SEPARATOR.format(label=label) for label in self.labels if BacklogMd.LABEL_SEPARATOR in label]
        if self.project_dir is None:
            return [*problems, Err.BACKLOG_PROJECT_UNSET]
        if not self.project_dir.is_dir():
            return [*problems, Err.BACKLOG_PROJECT_MISSING.format(path=self.project_dir)]
        config = next((self.project_dir / c for c in BacklogMd.CONFIG_FILES if (self.project_dir / c).is_file()), None)
        if config is None:
            return [*problems, Err.BACKLOG_NOT_INITIALIZED.format(path=self.project_dir)]
        text = retry_io(lambda: config.read_text(encoding="utf-8"), str(config))
        if not re.search(Parse.BACKLOG_STATUS.format(status=re.escape(self.status)), text, re.MULTILINE | re.IGNORECASE):
            problems.append(Err.BACKLOG_STATUS_MISSING.format(status=self.status, config=config))
        if any(re.search(pattern, text, re.MULTILINE) for pattern in Parse.BACKLOG_UNSAFE):
            problems.append(Err.BACKLOG_GIT_ON.format(config=config))
        board = [config, self.project_dir / BacklogMd.TASKS_DIR] if config.name == BacklogMd.ROOT_CONFIG else [config.parent]
        for path in board:
            state = self.ignore_state(path)
            if state is GitIgnore.NOT_IGNORED:
                problems.append(Err.BACKLOG_NOT_IGNORED.format(path=path))
            elif state is GitIgnore.UNKNOWN:
                problems.append(Err.BACKLOG_IGNORE_UNKNOWN.format(path=path))
        return problems

    def _create(self, command: list[str], cwd: Path) -> str:
        try:
            result = self.runner(
                command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=BacklogMd.TIMEOUT, check=False, creationflags=NO_WINDOW,
            )
        except FileNotFoundError as exc:
            raise PublishError(Err.BACKLOG_BINARY_MISSING.format(binary=self.binary)) from exc
        except subprocess.TimeoutExpired as exc:
            raise PublishError(Err.BACKLOG_TIMEOUT.format(seconds=BacklogMd.TIMEOUT)) from exc
        except OSError as exc:
            raise PublishError(Err.BACKLOG_EXEC.format(binary=self.binary, error=exc)) from exc
        if result.returncode != 0:
            raise PublishError(Err.BACKLOG_FAILED.format(code=result.returncode, tail=_tail(result.stdout + result.stderr)))
        return str(result.stdout)


def _tail(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return " | ".join(lines[-BacklogMd.TAIL_LINES:])

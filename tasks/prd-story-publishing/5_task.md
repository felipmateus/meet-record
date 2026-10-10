# Task 5.0: Backlog.md spike, in-repository setup and the Backlog.md publisher

## Overview

First confirm, against the real `backlog` CLI in a throwaway folder, the points the Backlog.md docs leave open; then prepare this repository to host a git-ignored Backlog.md project; then implement `BacklogMdPublisher`, which creates one task per story in the **Triagem** status and reports what is not ready. Delivers FR1, FR8, the Backlog.md part of FR9 and the privacy requirements.

<skills>
### Skills compliance

- `python-pro`: subprocess adapter behind an injected runner, typed command builder.
- `error-handling-patterns`: map every CLI failure to `PublishError` with the fix.
- `python-testing-patterns` / `testing-patterns`: scripted stand-in for the CLI, opt-in real test.
- `bash-defensive-patterns`: the one-time setup commands documented for the user.
- `verification-before-completion`: the spike answers are recorded before the adapter relies on them.
</skills>

<requirements>
- Spike: answer techspec §9 items 1–7 in a temporary folder and record the answers in techspec §9 (id format and regex, `--ac` with commas and the fallback decision, `-s` with a custom status, priority values, `statuses` line format, `init --no-git` side effects inside a Git repository and the agent-instructions flag, CLI discovery from the project root).
- `.gitignore` gains `backlog/` and `backlog.config.yml` before any Backlog.md file is created in this repository.
- One-time setup at the project root, run only with the user's approval: `backlog init --no-git` without agent instructions, `Triagem` added to `statuses`; `git status` shows no new tracked or untracked files afterwards.
- `BacklogMdPublisher` per techspec §5.1: `command()` kept in one method, body with traceability, one `--ac` per criterion (or the spike's fallback), priority mapping, ref parsed with `Parse.BACKLOG_TASK_ID`, `PublishError` for missing binary / non-zero exit / timeout / no id (and for any other failure of the spawn: the publish use case only collects `TeamsRecorderError`s), arguments as a list through `process_control`, no network, never edits or moves tasks.
- `problems()` and the guard in `publish` per techspec §5.1 and §11, including the git-ignore check and the `autoCommit` / `remoteOperations` check.
- Register the `backlog-md` builder in the container registry (4.0).
- Strings in `messages.py` (`Err`, `StoryDoc` body labels) and identifiers in `constants.py` (`Parse.BACKLOG_TASK_ID`, `Proc.BACKLOG_TIMEOUT`, config file names).
</requirements>

## Subtasks

- [ ] 5.1 Run the spike in a temporary folder and record the answers in techspec §9; adjust §5.1 if an answer changes the design.
- [ ] 5.2 Add the `.gitignore` entries.
- [ ] 5.3 With the user's approval, run the one-time setup at the project root and check `git status`.
- [ ] 5.4 Implement `adapters/outbound/publisher_backlogmd.py` (command, body, priority, ref parsing, error mapping).
- [ ] 5.5 Implement `problems()` and the publish guard (git-ignore, config checks).
- [ ] 5.6 Add the constants and messages; register the builder in `container.py`.
- [ ] 5.7 Add the scripted stand-in `tests/fixtures/fake_backlog_cli.py` (records arguments and cwd, prints a task id in the spike's format, can fail on demand).
- [ ] 5.8 Write the unit, integration and opt-in real tests below.

## Implementation details

See techspec §5.1 (adapter), §6 (location and one-time setup), §9 (spike) and §11 (privacy). The fake CLI follows the existing stand-ins (`tests/fixtures/fake_claude_cli.py`).

## Success criteria

- The spike answers are written in techspec §9 and the regex and `--ac` strategy match them.
- After setup, `backlog board` shows a Triagem column and `git status` is clean.
- Publishing a story with criteria that contain commas creates exactly one task in Triagem with the same number of acceptance criteria (real opt-in test).
- `problems()` is empty on a ready project and names each problem otherwise; `publish` refuses a backlog folder that Git would version.
- `pytest` and `mypy` clean; the opt-in real test passes with `TREC_REAL_BACKLOG=1`.

## Task tests

- [ ] Unit tests — `tests/unit/test_publisher_backlogmd.py`: `command()` shape (title, `--desc` with newlines, `-s Triagem`, labels with the day, priority present/absent, one `--ac` per criterion or the fallback), ref parsing (valid outputs from the spike, no id → error), error mapping (missing binary, non-zero exit with tail, timeout), `problems()` cases in temporary folders (no project, status missing, `autoCommit: true`, folder not ignored inside a `git init` repo, ignored folder, folder outside any Git repo).
- [ ] Integration tests — `tests/integration/test_publisher_backlogmd.py`: spawn `fake_backlog_cli.py` through `process_control` (on `PATH` via monkeypatch); the recorded cwd is the project folder and the arguments arrive intact (multi-line description, accents, commas); a failing run becomes `PublishError`.
- [ ] E2E tests — `tests/integration/test_publisher_backlogmd_real.py` (`-m slow`, `TREC_REAL_BACKLOG=1`): real `backlog init --no-git` in a temporary folder, add Triagem, publish one story, `backlog task list --json` shows it in Triagem with all criteria; no file created outside the Backlog.md folder.

## Relevant files

- `.gitignore`
- `src/teams_recorder/adapters/outbound/publisher_backlogmd.py` (new), `adapters/outbound/process_control.py`
- `src/teams_recorder/constants.py`, `messages.py`, `container.py`
- `tests/fixtures/fake_backlog_cli.py` (new), `tests/unit/test_publisher_backlogmd.py` (new), `tests/integration/test_publisher_backlogmd.py` (new), `tests/integration/test_publisher_backlogmd_real.py` (new)
- `tasks/prd-story-publishing/techspec.md` (§9 answers)

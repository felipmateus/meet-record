# Task 6.0: CLI: `trec publish`, publishing after drafts, `doctor` and `status`

## Overview

Expose publishing to the user: a `trec publish` command, automatic publishing right after drafting (in `trec stories` and in `trec plan`, so the 6 pm planner does it), one `trec doctor` line per destination and a `trec status` line with the stories waiting to be published. Delivers FR2, the exit-code part of FR4, and FR9.

<skills>
### Skills compliance

- `python-pro`: Typer command, option parsing, exit codes.
- `clean-code`: one helper for the draft → publish chain shared by `plan` and `stories`.
- `python-testing-patterns`: `CliRunner` tests with the fake Backlog.md CLI on `PATH`.
</skills>

<requirements>
- `trec publish [--date YYYY-MM-DD] [--only 1,3]` per techspec §8: one line per published story (`title → destination ref`), already-published and failure lines, exit 1 on any failure; no LLM prerequisites; invalid `--only` → clear error.
- After a successful draft, publish when `story_auto_publish` is true; a publishing failure exits 1 after the purge and never undoes the plan or the drafts.
- `trec doctor`: one line per configured destination with `problems()`; affects the exit code only when `story_auto_publish` is true.
- `trec status`: "Stories waiting to be published: N" over the last `dedup_days` days, when publishing is configured.
- All strings in `messages.py`; help texts without square brackets (Typer's rich markup).
</requirements>

## Subtasks

- [x] 6.1 Add the `publish` command and the `--only` parser.
- [x] 6.2 Chain publishing after drafting in the shared helper used by `plan` and `stories`; keep the exit-code rules.
- [x] 6.3 Add the destination lines to `doctor`.
- [x] 6.4 Add the waiting-stories line to `status`.
- [x] 6.5 Add the CLI strings; mention `trec publish` in the `config.toml` comment of `[stories] publish` and in `Stories.PUBLISH`.
- [x] 6.6 Write the unit and integration tests below.

## Implementation details

See techspec §8 and §10. Reuse the existing `_draft_stories` and `_day` helpers in `cli.py`.

## Success criteria

- `trec publish` on a day with drafts and the fake CLI prints one line per story and saves the refs; running it again prints "already published" and exits 0.
- `trec plan` with drafting and publishing enabled on a day with new actions (fake writer through the fake Claude CLI) ends with the stories published; with a failing destination it exits 1 after the purge and the plan file exists.
- `trec doctor` shows each destination's problems and its exit code follows the rule above.
- `pytest` and `mypy` clean.

## Task tests

- [x] Unit tests — `--only` parser (valid list, spaces, duplicates, non-numbers, zero) in `tests/unit/test_cli_helpers.py`.
- [x] Integration tests — `tests/integration/test_cli.py`: publish without drafts; publish with drafts and `fake_backlog_cli.py` on `PATH`; rerun idempotency; `--only`; failure exit code; `plan` on an empty day with publishing on (no publisher call, exit 0); `stories` → publish chain; `doctor` destination lines and exit code with publishing on and off; `status` waiting count.
- [ ] E2E tests — covered in 7.0.

## Relevant files

- `src/teams_recorder/adapters/inbound/cli.py`
- `src/teams_recorder/messages.py`
- `tests/integration/test_cli.py`, `tests/fixtures/fake_backlog_cli.py`

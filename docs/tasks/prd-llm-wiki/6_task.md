# Task 6.0: CLI, doctor, status and container wiring

## Overview

Make the wiki operable: build the store, writer and optional history in the composition root, attach the ingest to the pipeline when `[wiki] enabled = true`, and add `trec wiki ingest [id] [--force]`, `trec wiki lint` and `trec wiki rebuild [--yes]`, plus the wiki lines in `trec status` and `trec doctor`. After this task the whole flow runs end to end against the fake `claude`.

<skills>
### Skills compliance

- `python-pro`: Typer sub-app, exit codes and messages consistent with `transcribe`/`analyze`/`publish`.
- `testing-patterns`: CLI integration tests with the scripted `claude` on `PATH`, like the existing ones.
- `verification-before-completion`: the daemon is not restarted or reinstalled without the user's approval.
</skills>

<requirements>
- `container.py`: `wiki_store` (`FsWikiStore(settings.wiki_dir)`), `wiki_writer` (`ClaudeWikiWriter` over the shared transport), `wiki_history` (`GitWikiHistory` when `wiki_git` and `git` is found, else `None`), `ingest_meeting()`, `rebuild_wiki()`, `pipeline()` passing the ingest only when `settings.wiki_enabled`; the schema text loaded from `settings.wiki_schema_path`.
- `trec wiki ingest [id] [--force]`, `trec wiki lint`, `trec wiki rebuild [--yes]` as in techspec §7, with `_check_llm_prerequisites` for ingest and rebuild, notifications on failure (`Notify.WIKI_FAILED`), exit 1 on any failure or lint problem.
- `trec status`: the wiki line (pages, pending) when the folder exists or `enabled` is true. `trec doctor`: the wiki line and problem lines; problems fail the doctor only when `enabled = true`.
- Help texts and output lines in `messages.Cli`; `Ask.WIKI_REBUILD` for the confirmation.
- Windows: the Typer commands and the adapters are platform-neutral; nothing new under `if sys.platform == "win32"` beyond the PID-alive check already injected in task 3.
</requirements>

## Subtasks

- [ ] 6.1 Wire the container (`wiki_store`, `wiki_writer`, `wiki_history`, `ingest_meeting`, `rebuild_wiki`, `pipeline`).
- [ ] 6.2 Add `wiki_app` with `ingest`, `lint`, `rebuild` and the shared loop helper (`_ingest_meetings(c, ids, force)`).
- [ ] 6.3 Add the `status` and `doctor` lines.
- [ ] 6.4 Write the tests below.
- [ ] 6.5 With the user's approval, `trec agent restart` so the daemon loads the new code (ingest stays off: `enabled = false`).

## Implementation details

`trec wiki ingest` with no id prints one line per pending meeting as `transcribe` does (`<id>… ok (3 pages: 1 created, 2 updated, 0 rejected)` / `failed: <error>`), then the wiki path; the lint output lists problems grouped by kind; `rebuild` prints the backup path before ingesting so the user can recover if the run is interrupted. The doctor's `CLAUDE.md in sync|stale` comes from `store.problems()` (info level), so a schema edit is visible before the next ingest refreshes the copy.

## Success criteria

- With the fake `claude` on `PATH`: `trec wiki ingest` on a data dir with two analyzed meetings writes two meeting pages, the fake's entity pages, `index.md`, `log.md`, `CLAUDE.md` and two `wiki.json`; a second run prints `skipped` twice and changes nothing; `--force` re-ingests; `FAKE_CLAUDE_MODE=wiki_bad_slug` shows `1 rejected` and lint lists it; `FAKE_CLAUDE_MODE=error` leaves `wiki_error.txt`, exit 1, and `trec status` still shows the meeting as `analyzed`.
- `trec wiki lint` exits 0 on a clean wiki and 1 with a broken link planted in a page.
- `trec wiki rebuild --yes` leaves a `.bak-*` folder and a fresh wiki with the same pages.
- `trec plan` on the same data is unaffected by a wiki failure (the meeting still counts).
- `pytest`, `mypy` and the strings guard clean.

## Task tests

- [ ] Unit tests — `tests/unit/test_container_platforms.py` (wiring, history `None` when git off, ingest attached only when enabled); `tests/unit/test_cli_helpers.py` if a helper is extracted.
- [ ] Integration tests — `tests/integration/test_cli.py` (the scenarios above: ingest single/pending/force/rejected/error, lint, rebuild, status and doctor lines).
- [ ] E2E tests — not applicable here (task 7 and 8 run the real model).

## Relevant files

- `src/teams_recorder/container.py`, `adapters/inbound/cli.py`, `messages.py`
- `tests/unit/test_container_platforms.py`, `tests/integration/test_cli.py`, `tests/fixtures/fake_claude_cli.py`

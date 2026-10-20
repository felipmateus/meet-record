# task_10 memory

Status: implemented and verified on fakes and a tmp project (CliRunner); uncommitted. No `trec` command ran against the real data dir, no real model, no `trec agent`.

Evidence: `pytest -q` (one session, whole fast suite) exit 0, `mypy` clean (63 files), `tests/unit/test_no_hardcoded_strings.py` green (inside the run).
New tests (all in `tests/integration/test_cli_activities.py`, section "not curated in trec activities, trec doctor and trec status"): UT-087, doctor singular/window/ok/no-pass/no-document/unreadable, status line (counts, no document, renamed headings, unreadable), E2E-005 (real `Daemon` + `CuratingContainer` from `tests/unit/test_curator_worker.py`, FS repo and FS store, `_resume_pending()` + `step_soon`). Edited `tests/integration/test_cli.py` (`Open actions` assertions -> `Cli.ACTIVITIES_STATUS_NONE`; the damaged-file status test now damages the pass log).

Decisions:
- `trec status`: `Open actions: N` and `OPEN_ACTIONS*` messages removed; `Activities: 7 yours · 3 waiting on others (last pass Mon 19/10 10:12)` via `cli._activities_status_line(ActivitiesStatus)`; no document -> `Activities: not created yet (trec activities curate --since YYYY-MM-DD)`; no last pass -> no parenthesis; neither heading present -> `document has no actions or waiting sections`; a `TeamsRecorderError` -> `Activities: unreadable (...)`, exit 1 (same as the old line). `status` no longer reads `open_actions.json`.
- `trec doctor`: `cli._check_activities(settings)`, line `[mark] Activities document: <relative path> (<state>)`; marks: `ok ` (ok, last pass <when> / ok, no pass recorded), `WARNING` (N meetings not curated (trec activities) / 1 meeting ...), `info` (not created yet (...)); no document wins over not-curated; unreadable -> `[WARNING] Activities document: unreadable (...)`. Never changes the exit code. Built through `build_container(settings, headless=True)` like `status`.
- 10.3: the `Not curated` listing from task_07 already shows both reasons; no change needed (UT-087 asserts it).
- Messages: `Cli.ACTIVITIES_STATUS*`, `Cli.DOCTOR_ACTIVITIES*`.

Left to others: docs (`AGENTS.md`, architecture, PRD: task_11/14); `trec agent restart` not needed (CLI only).

---
status: completed
title: "Task 6: Pipeline hook, container wiring and the daemon's curator worker"
type: feature
complexity: high
---

# Task 6: Pipeline hook, container wiring and the daemon's curator worker

## Overview

Connects the curator to the running system: the `[activities]` config section, the container that builds `ClaudeCurator`, `FsActivityStore` and `CurateMeetings`, a `Pipeline.after_analysis` hook, and a `CuratorWorker` thread owned by the `Daemon` that batches analyzed meetings into passes, adds the meetings still pending from the last two working days, rebuilds its queue at daemon start and stops without waiting for an in-flight call. After this task, minutes after a recorded meeting is analyzed, the document updates by itself.

## Shippable Outcome

- Outcome: the daemon's pipeline enqueues each meeting that reaches `analyzed`; the worker runs `CurateMeetings` in passes of up to four plus pending ids; a curation failure leaves the meeting `analyzed` with `curation_error.txt` and no `error.txt`; `[activities] enabled = false` builds no worker.
- Verify in this task: UT-045, UT-107, UT-108, UT-120, IT-001, IT-002, IT-008, and the config cases listed inline.
- Integration verification: task_10 (E2E-005: daemon start curates a meeting left pending); task_08 starts the real daemon with the new code (shadow).

## Requirements

- Contracts: `_spec.md` › System Architecture (worker, daemon start, stop), › Core Interfaces (`Pipeline.after_analysis`, `Container.pipeline(after_analysis=None)`), › Architectural Boundaries (container never imports `daemon.py`; the daemon builds its own worker from `container.curate_meetings()` and passes `worker.enqueue` in `_finish_call` and `_resume_pending`), › Key Decisions (CuratorWorker stops without waiting), › Config Lifecycle (`[activities]` keys and defaults), Safety Invariants 8, 13; `_dx.md` › Config.
- `Pipeline.after_analysis` is called once the meeting reaches `ANALYZED`; its failures are logged, never written to `error.txt`.
- `CuratorWorker`: one daemon thread, `queue.Queue`, `enqueue` non-blocking, drains up to 3 more ids, adds `CurateMeetings.pending()`, de-duplicates, `request_stop()` sets a flag and enqueues a sentinel; `Daemon.shutdown` never joins an in-flight LLM call. Use `getattr(self.container, …)` defensively so the daemon's `FakeContainer` in tests keeps working.
- Config: `[activities] enabled=true, model (default: the analyzer's), cli_model="opus", effort="medium", notify=true, keep_versions=50` in `config.toml`, `config.Settings` with validation, and `scripts/config_tool.py`; the Windows installer learns the section where it writes config (no offline-installer docs in this repo).
- Container: `build_curator()` on its own transport per `llm.provider`, the store with `doc_format()` and `keep_versions`, `curate_meetings()` like `analyze_meeting()`. `[activities] enabled = false` disables only the automatic triggers.
- Log templates (pass start/end, queue size, lock wait, failures, batch isolation, reconcile) in `messages.Log`.
- The daemon runs this code only after `trec agent restart`, which needs the user's approval; do not run it here (task_08 does, with approval).

## Subtasks

- [x] 6.1 `[activities]` config, `Settings`, `config_tool.py`, Windows installer config step.
- [x] 6.2 Container builders; `Container.pipeline(after_analysis=None)`.
- [x] 6.3 `Pipeline.after_analysis` in `process` / `resume_pending`.
- [x] 6.4 `CuratorWorker` and its ownership by `Daemon` (start, `_resume_pending` enqueues `pending()`, `_finish_call`, `shutdown`).
- [x] 6.5 Tests.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/pipeline.py:46-86` — `process` / `resume_pending`.
- `src/teams_recorder/container.py:130-160` — `analyze_meeting()`, `pipeline()` returning a fresh `Pipeline`.
- `src/teams_recorder/adapters/inbound/daemon.py:218-313` — `_finish_call`, `_resume_pending`, `_background`, `shutdown`, `run_in_background`.
- `src/teams_recorder/config.py`, `config.toml`, `scripts/config_tool.py`, `scripts/install.ps1`.
- `tests/unit/test_daemon.py`, `tests/unit/test_pipeline.py`, `tests/unit/test_config.py`, `tests/unit/test_container_platforms.py`.

### Dependent Files

- `src/teams_recorder/adapters/inbound/cli.py` (task_07) uses `curate_meetings()` and the settings.

### Related ADRs

- [ADR-002](adrs/adr-002.md) — the curator runs alongside the planner until the go.

## Deliverables

- Config section, container builders, pipeline hook, `CuratorWorker`, tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-045, UT-120 — worker ordering and de-duplication; stop contract.
- [x] UT-107, UT-108 — queue rebuilt at daemon start; hook wiring and the container's import boundary.
- [x] IT-001, IT-002 — pipeline to document on `FsActivityStore`; a failing curator leaves the meeting `analyzed` with `curation_error.txt`.
- [x] IT-008 — `ClaudeCurator` through `fake_claude_cli.py` with one repair: one `curate` and one `curate-repair` usage entry, document committed.

Config cases not in `_tests.md` (from `_spec.md` › Config Lifecycle), owned here:
- [x] A config without `[activities]` yields the defaults of `_dx.md` › Config; each key set in the file is read; an `effort` outside `Effort` is rejected the way the existing sections reject it.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- Existing daemon and pipeline tests pass unchanged except for the new collaborator.

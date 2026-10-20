---
status: pending
title: "Task 14: Remove the planner; audio retention in the daemon"
type: refactor
complexity: high
---

# Task 14: Remove the planner; audio retention in the daemon

## Overview

Deletes the 18:00 planner now that the activities document replaces it: the use case, port, adapter, prompt, plan files and open-actions list as inputs, `trec plan`, the scheduled job, and every planner identifier except the legacy ones needed to remove an installed job. Audio retention, which ran as `trec plan --purge`, moves to the daemon (scheduled in the background on the first tick of each day), `[audio] retention_days` replaces `[planner] retention_days` (read as fallback for one release), and `agent install` / `restart` / `uninstall` and the installer scripts remove the old planner job.

## Shippable Outcome

- Outcome: `trec plan` is gone (`No such command`, exit 2); the daemon purges old audio once a day; installing, restarting or uninstalling the agent removes `local.teams-recorder.planner` (Windows: its task) when present; old configs and old `analysis.json` files load; the evaluation scripts read the document and pass log instead of plans.
- Verify in this task: UT-056, UT-090–UT-092, UT-094–UT-098, IT-011, IT-018.
- Integration verification: none (`trec agent restart` after merge, with the user's approval, is what removes the installed planner job on the dev Mac).

## Requirements

- **Prerequisite: the user has said "go" after the shadow week (ADR-002; recorded in task_12). Do not start without it.** task_13 must be complete (the story use cases have left `planning.py`).
- Contracts: `_spec.md` › Impact Analysis (rows for `planning.py`, the Planner list, `ActionStatus`, LaunchAgent / Windows task, installer scripts, `scripts/fidelity_eval.py` / `wiki_corpus.py`, user state kept unread), › Config Lifecycle, › Compatibility regime; [ADR-002](adrs/adr-002.md) (Decision, Risks, Implementation Notes); `_dx.md` › Removed, › `trec agent install` / `uninstall` / `status`, › Config.
- Hard cut, no shim: `planner_claude.py`, `prompts/plan_system.md`, `BuildDailyPlan`, `Planner` port, `DailyPlan`, `merge_open_actions`, `is_overdue_on`, `save/load_plan`, `latest_plan_before`, `load/save_open_actions`, `Files.PLAN_*` / `OPEN_ACTIONS`, `Llm.MAX_PREVIOUS_PLAN_CHARS`, `ScheduledTask.planner`, `LaunchAgent.planner`, `trec plan`, `_planner_agent`, `[planner] hour`; `planning.py` deleted.
- `ActionStatus.OVERDUE` survives only for decoding old files (read-only).
- `constants.Legacy` (`PLANNER_LABEL`, `PLANNER_TASK` and the arguments to build a `LaunchAgent(label=…)` / `ScheduledTask(name=…)` whose only use is `uninstall()`) replaces `Launchd.PLANNER_*` / `Windows.TASK_PLANNER`. The planner line disappears from `agent status`.
- `PurgeOldAudio` → `application/use_cases/retention.py`, default `constants.Audio.RETENTION_DAYS` (30); `trec purge` unchanged. The daemon schedules it through `_background` on the first tick of a new day (the tick never runs it inline), records the day before scheduling, logs a failure with its `Log` template and does not retry the same day.
- Config: `[audio] retention_days` (fallback `[planner] retention_days`; `[audio]` wins); `[planner]` section removed from `config.toml`; `scripts/config_tool.py` and the Windows installer learn `[audio]` (no offline-installer docs in this repo).
- `scripts/install.sh`, `install.ps1`, `uninstall.sh`, `uninstall.ps1`: no 6 pm planner offer or announcement; remove the legacy job.
- `scripts/fidelity_eval.py`, `scripts/wiki_corpus.py`: switch plan reads to the document / pass log; `tests/unit/test_eval_harness.py` green.
- Tests use a fake `launchctl` and fake scheduler; never touch the real LaunchAgents. **Ask the user before `trec agent restart`** (it also removes the installed planner job). `data/plans/*` and `open_actions.json` stay on disk untouched.

## Subtasks

- [ ] 14.1 Delete the planner code and constants; `constants.Legacy`; `ActionStatus.OVERDUE` decode-only.
- [ ] 14.2 `use_cases/retention.py`; the daemon's daily purge.
- [ ] 14.3 `[audio] retention_days` with fallback; remove `[planner]`; `config_tool.py`, Windows installer config.
- [ ] 14.4 `agent install` / `restart` / `uninstall` remove the legacy job (macOS and Windows); `agent status` without the planner line.
- [ ] 14.5 Installer and uninstall scripts; evaluation scripts off plan files.
- [ ] 14.6 Delete or rewrite the planner tests (`test_planner_claude.py`, plan parts of `test_planning_use_cases.py`, `test_launchd.py` planner cases); new tests.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/use_cases/planning.py` — what remains after task_13 (deleted).
- `src/teams_recorder/adapters/outbound/planner_claude.py`, `prompts/plan_system.md`.
- `src/teams_recorder/domain/models.py:176-300,440-470` — `ActionStatus`, `DailyPlan`, `merge_open_actions`.
- `src/teams_recorder/adapters/inbound/cli.py:553-645,736` — agent install/planner, `plan`, `purge`.
- `src/teams_recorder/adapters/inbound/daemon.py:218-313` — `_background` for the daily purge.
- `src/teams_recorder/adapters/outbound/launchd.py`, `scheduler_windows.py`, `src/teams_recorder/container.py`, `src/teams_recorder/config.py`, `config.toml`, `src/teams_recorder/constants.py:80-170`.
- `scripts/install.sh`, `scripts/install.ps1`, `scripts/uninstall.sh`, `scripts/uninstall.ps1`, `scripts/config_tool.py`, `scripts/fidelity_eval.py`, `scripts/wiki_corpus.py`.

### Related ADRs

- [ADR-002](adrs/adr-002.md) — remove the planner; no scheduled pass.

## Deliverables

- The deletion, `retention.py`, the daemon purge, config and installer changes, legacy-job removal, script updates, tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [ ] UT-090 — `trec plan` is gone.
- [ ] UT-091, UT-095, UT-096, IT-011 — legacy planner job removed by install, restart, uninstall (macOS and Windows), only through `Legacy` identifiers.
- [ ] UT-092 — `[audio]` / `[planner]` retention fallback.
- [ ] UT-094, UT-097, UT-098 — the daemon's daily purge, `PurgeOldAudio` in `retention.py`, a failing purge.
- [ ] UT-056 — a legacy `"overdue"` action still decodes.
- [ ] IT-018 — `scripts/install.sh --dry-run` without the 6 pm planner.

## Success Criteria

- `pytest` full suite (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green; no reference to the deleted names outside `constants.Legacy` and the decode-only `OVERDUE`.
- Windows changes are untested on real Windows; say so when reporting. Commits only with the user's approval.

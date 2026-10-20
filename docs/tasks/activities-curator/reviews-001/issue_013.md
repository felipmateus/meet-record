---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 392
severity: medium
author: claude-code
provider_ref:
---

# Issue 013: Planner hard cut deletes what is needed to remove the old job

## Review Comment

The Impact Analysis deletes `Launchd.PLANNER_*`, `ScheduledTask.planner` and `_planner_agent` (`_spec.md:392`). US-018 AC-1, UT-091 and IT-011 require `trec agent install`/`uninstall` to boot out and delete the installed `local.teams-recorder.planner` job and the Windows planner task. To do that, code needs the planner's label and plist path, and on Windows the task name `Windows.TASK_PLANNER`. Today those come only from `Launchd.PLANNER_LABEL` (`src/teams_recorder/constants.py:145`), `LaunchAgent.planner(...)` (`src/teams_recorder/adapters/outbound/launchd.py:117-120`) and `ScheduledTask.planner(...)` (`src/teams_recorder/adapters/outbound/scheduler_windows.py:37-38`).

Other gaps in the same migration:
- Between shipping slice 3 and the user's next `trec agent install`, the installed plist keeps running `trec plan --purge` (`constants.py:158`) every weekday at 18:00. With `plan` removed, that run exits 2 every day and nothing removes it. The usual post-change step is `trec agent restart` (AGENTS.md), which does not touch the planner. ADR-002's mitigation (`adrs/adr-002.md:49`) covers only install/uninstall.
- The installers still offer and announce "the 6 pm planner" (`scripts/install.sh:11,221-223`, `scripts/install.ps1:9,269-271`). They are not in the Impact Analysis.
- `PurgeOldAudio` takes its default from `PlannerDefaults.RETENTION_DAYS` (`src/teams_recorder/application/use_cases/planning.py:292`, `constants.Planner`), and that class is not listed for move/removal.

Suggested fix: keep legacy identifiers for removal only, e.g. `constants.Legacy.PLANNER_LABEL` and `Windows.TASK_PLANNER_LEGACY`, plus a `LaunchAgent(label=...)`/`ScheduledTask(name=...)` built only to `uninstall()`. Remove the legacy job in `agent restart` too, and/or on daemon start, logged once. Add `scripts/install.sh`/`install.ps1` to the Impact Analysis, and move `RETENTION_DAYS` to an `Audio` constant. Extend UT-091 to `agent restart`.

## Triage

- Decision: `VALID`
- Notes: Valid. Deleting `Launchd.PLANNER_*`, `ScheduledTask.planner` and `_planner_agent` leaves nothing to identify the installed job; until removal the plist keeps running `trec plan --purge` (exit 2 daily); `agent restart` was not covered; the installers still announce the planner; `PlannerDefaults.RETENTION_DAYS` feeds `PurgeOldAudio`.
- Verified: `LaunchAgent(project_dir, data_dir, label=Legacy.PLANNER_LABEL).uninstall()` is buildable without the planner factory (launchd.py: `label` is a field, `plist_path` depends only on it, `uninstall()` boots out and unlinks) and `ScheduledTask(name=…)` likewise; `agent install`/`restart`/`uninstall` and the four scripts are in Impact Analysis; `PurgeOldAudio` moves with `constants.Audio.RETENTION_DAYS`; UT-091/095/096/097, IT-018. The deviation (no removal on daemon start) is justified by AGENTS.md's approval rule.

### Resolution

Fixed, with one deviation. Added `constants.Legacy.PLANNER_LABEL` / `PLANNER_TASK` and a `LaunchAgent(label=…)` / `ScheduledTask(name=…)` built only to `uninstall()`; `agent install`, `agent restart` and `agent uninstall` remove the legacy job; installer and uninstall scripts added to the Impact Analysis (no longer offer or announce the planner, remove the job); `PurgeOldAudio` moves to `use_cases/retention.py` with `constants.Audio.RETENTION_DAYS`. Deviation: removal on daemon start was not added; `agent restart` is the step the project already requires after any Python change, so it closes the gap without the daemon unregistering a launchd job on its own (AGENTS.md asks approval for such actions). ADR-002 risk text updated; US-018 AC-1, AC-6. Tests: UT-091 extended, UT-095 (restart), UT-096, UT-097, IT-018 (installer dry-run).


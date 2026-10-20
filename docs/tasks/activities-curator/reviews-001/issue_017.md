---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 144
severity: low
author: claude-code
provider_ref:
---

# Issue 017: Daily purge on the detector tick does blocking I/O in the call loop

## Review Comment

ADR-002 moves audio retention into the daemon: "daily purge on the first tick of each day" (`_spec.md:144`, `adrs/adr-002.md:17`, UT-094). `Daemon.tick()` runs on the detector loop thread (`src/teams_recorder/adapters/inbound/daemon.py:65-75`, `:90-101`), and that loop has to keep reading the call state to start a recording after `start_after` positive readings. `PurgeOldAudio.execute` reads every meeting's `meta.json` and file list and deletes audio files (`src/teams_recorder/application/use_cases/planning.py:294-302`). AGENTS.md notes that on this Mac a first file open can take seconds because of endpoint scanning. The first tick of the day often comes right after the Mac wakes, which is often when the user joins a call. Running the purge inline there delays detection and the start of the recording.

Suggested fix: specify that the tick only *schedules* the purge, through `self._background(...)` like the other jobs (`daemon.py:307-313`). Record the day before scheduling so a failure does not retry every tick, and log failures with a `Log` template. UT-094 can then assert the purge was scheduled once per day through `run_in_background`.

## Triage

- Decision: `VALID`
- Notes: Valid. `Daemon.tick()` runs on the detector thread (daemon.py:65-101) and `PurgeOldAudio.execute` reads every meeting folder and deletes files; AGENTS.md documents multi-second first opens on this Mac, and the first tick of the day often coincides with a call start.
- Verified: the tick only schedules the purge through `_background` (daemon.py:307-313 is the existing helper), day recorded before scheduling, failure logged; ADR-002, `_dx.md` Config, US-018 AC-7; UT-094/098.

### Resolution

Fixed as suggested. The tick only schedules the purge through `_background` (like the other jobs); the day is recorded before scheduling so a failure does not retry every tick; failures log with a `Log` template. ADR-002 decision text, `_dx.md` Config notes, Impact Analysis (daemon row), US-018 AC-7, Monitoring. Tests: UT-094 rewritten (scheduled once per day through `run_in_background`, never inline), UT-098 (failure logged, not retried the same day).


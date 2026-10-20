---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 125
severity: medium
author: claude-code
provider_ref:
---

# Issue 004: `trec analyze` bypasses Pipeline, so `after_analysis` never fires

## Review Comment

The spec hooks curation into `Pipeline` through `after_analysis` (`_spec.md:298`, `:122-123`). It then states "`trec analyze <id>` : after_analysis = CurateMeetings inline" (`_spec.md:125`). But the `analyze` CLI command does not go through `Pipeline`. It calls `c.analyze_meeting()` and `use_case.execute(mid)` directly in a loop (`src/teams_recorder/adapters/inbound/cli.py:453-493`), and handles `mark_failed`/`clear_failed` itself. A `Pipeline.after_analysis` field is never reached from there.

Consequences:
- E2E-001 (`_tests.md:150`) runs `trec analyze <id>` and expects `trec activities` to show the curated focus. Implemented to the spec, that test fails.
- Behaviour that the CLI path needs is undefined:
  - `trec analyze` with no id analyzes every pending meeting. Is curation one pass per meeting, or batched in fours like the daemon?
  - What does the command print for curation?
  - What exit code applies when the analysis succeeded but curation failed? (`_dx.md` has no entry for this.)
  - Does a manual re-analysis of an already analyzed meeting re-curate it?

Suggested fix: in `_spec.md` System Architecture and `_dx.md` CLI, state that `cli.analyze` calls `CurateMeetings.execute` on the successfully analyzed ids after the loop, batched as the daemon batches. Define the output line, reusing `Curating … ok (...)`, and the exit code: 0 for the analysis, plus the `failed: <reason>` line and `curation_error.txt`. Also state whether `[activities] enabled = false` skips it. Add a CLI test for `trec analyze <id>` → curated, and one for analysis ok + curation failed.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified: `cli.analyze` (cli.py:453-493) loops `analyze_meeting().execute` directly and never builds a `Pipeline`, so `after_analysis` cannot fire there; E2E-001 would fail as specified.
- Verified: `cli.analyze` (cli.py:453-493, confirmed not to use `Pipeline`) now curates after its loop in batches of 4; output line, exit code 0 on curation failure, `[activities] enabled = false` skip and rerun semantics are in `_spec.md` System Architecture, `_dx.md` › `trec analyze`, US-016 AC-4; UT-084/085/086.

### Resolution

Fixed as suggested. System Architecture and `_dx.md` now state that `cli.analyze` calls `CurateMeetings.execute` on the successfully analyzed ids after its loop, in batches of 4 oldest first, reusing the `Curating … ok (<n> edits) — <summary>` line; exit code stays 0 when every analysis succeeded and curation fails (`failed: <reason>` line, `curation_error.txt`, notification; the daemon retries); an analysis failure still exits 1 and those meetings are not curated; re-analysing an analyzed meeting curates it again (rerun-safe); `[activities] enabled = false` skips the step silently while explicit `trec activities` commands still run (Config Lifecycle). US-016 AC-4. Tests: UT-084, UT-085, UT-086; E2E-001 unchanged and now consistent.


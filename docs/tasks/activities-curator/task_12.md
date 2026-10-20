---
status: pending
title: "Task 12: Shadow week review and the go decision"
type: qa
complexity: medium
---

# Task 12: Shadow week review and the go decision

## Overview

⛔ **This is the go-gate of slice 2.** The curator has been running alongside the 18:00 planner on the user's real meetings (rollout B, started in task_08). This task collects what the shadow week showed: the misses the user lists, the pass log against the thresholds, and the user's explicit decision. Only a "go" from the user unblocks the planner removal and the stories on demand (tasks 13–15); a "no-go" keeps them pending and turns the misses into spec changes.

## Shippable Outcome

- Outcome: a recorded go/no-go decision from the user, with the shadow week's evidence: the user's list of misses, retry rate, failure rate and document size from `log/activities.jsonl`, and the date the user said go.
- Verify in this task: Q-003, read from the pass log and the user's answers.
- Integration verification: none.

## Requirements

- **Prerequisite: the shadow has run for about a week of working days on real meetings (task_08 restarted the daemon with the user's approval). Do not mark this task completed without the user's explicit "go" (ADR-002).** No agent message counts as that go; only the user's own message does.
- **Ask the user before any action that spends the subscription** (a re-run of Q-001/Q-002 after a prompt fix) and before any `trec agent restart` (a recording may be in progress).
- Thresholds: `_spec.md` › Monitoring and Observability (retry rate < 10%, failure rate < 2%, document ≤ ~8k tokens) and `_tests.md` › Q-003 (the user lists misses; the decision is the user's).
- Fixes found during the week that stay inside the spec (prompt wording, a bug) can be made here with tests and the user's approval to commit; a change of rule or contract goes back to the spec before any slice-2 task starts.
- Read `log/activities.jsonl` and the document only to compute the numbers; do not edit `data/` by hand.

## Subtasks

- [ ] 12.1 Compute the shadow week's retry rate, failure rate, unaccounted refs and document size from the pass log.
- [ ] 12.2 Ask the user for the misses they saw (wrong item, duplicate, missing item, unwanted notification) and record them.
- [ ] 12.3 Fix in-spec issues found (tests first), asking before commits and restarts.
- [ ] 12.4 Ask the user for the go/no-go decision and record it with its date in this task's completion notes and in `_spec.md` › Open Questions.

## Implementation Details

### Relevant Files

- `<data_dir>/log/activities.jsonl`, `<data_dir>/activities/atividades.md` (read only).
- `prompts/curate_system.md`, `prompts/analyze_system.md` — where in-spec fixes would land.

### Related ADRs

- [ADR-002](adrs/adr-002.md) — "the removal ships when the user says go".

## Deliverables

- The recorded decision and evidence; any in-spec fixes with their tests.

## Tests

Cases assigned from `_tests.md` — read the definition before starting.

- [ ] Q-003 — the shadow week on real meetings; the user's go/no-go.

## Success Criteria

- The task is completed only with the user's "go" recorded. With a "no-go", it stays `pending` (or `in_progress`) and slice 2 is not dispatched.

---
status: completed
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

- [x] 12.1 Compute the shadow week's retry rate, failure rate, unaccounted refs and document size from the pass log. (Waived with Q-003: no week of passes was measured and `log/activities.jsonl` was not read; the bootstrap figures in the completion notes stand in.)
- [x] 12.2 Ask the user for the misses they saw (wrong item, duplicate, missing item, unwanted notification) and record them. (Waived: the user gave the go before a shadow week; no misses were listed.)
- [x] 12.3 Fix in-spec issues found (tests first), asking before commits and restarts. (None found; no code changed.)
- [x] 12.4 Ask the user for the go/no-go decision and record it with its date in this task's completion notes and in `_spec.md` › Open Questions.

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

- [x] Q-003 — the shadow week on real meetings; the user's go/no-go. (Not run as a week: the user waived the comparison and gave the go; see the completion notes.)

## Success Criteria

- The task is completed only with the user's "go" recorded. With a "no-go", it stays `pending` (or `in_progress`) and slice 2 is not dispatched.

## Completion Notes

### Decision: GO (2026-10-20)

- The user, in their own message on 2026-10-20, in this session: "pode remover o plano das 18h" ("you can remove the 18:00 plan"). This is an explicit go for the planner removal and the stories on demand (ADR-002); it unblocks task_13, task_14 and task_15.
- The go came from the user, not from an agent message. The user chose to give it immediately instead of waiting for a full shadow week.

### What Q-003 was and was not

- Q-003 (the shadow week compared on real meetings) was **not run as a week**. The user waived it with the go above: no week of side-by-side passes was collected, no misses were listed, and the pass-log thresholds (retry rate < 10%, failure rate < 2%, document <= ~8k tokens) were not measured over a week.
- Q-001 and Q-002 were also not run. The user was told they need approval and spend the Claude subscription, and chose not to run them. No quality evaluation was run for this task.
- Task_08 (quality gate and shadow rollout) is still `pending` in its file; this task does not change it.

### Evidence available (the bootstrap, not a shadow week)

- The daemon was restarted with the curator on 2026-10-20.
- A bootstrap `trec activities curate --since 2026-10-06` ran 9 passes successfully: 19 meetings curated, producing 37 own actions, 9 waiting on others and 13 context items.
- Reruns of already-curated meetings produced 0 edits.
- These figures were reported to this task by the caller. This task did not read `data/` or `log/activities.jsonl`, so retry rate, failure rate, unaccounted refs and document size are not computed here.

### Scope

- No code, test, prompt or `data/` change. Documentation touched: this file, `_spec.md` › Open Questions, `memory/task_12.md`, `memory/MEMORY.md`.
- Slice 2 (tasks 13 to 15) can now be dispatched. The 18:00 planner and its LaunchAgent are still installed and running until task_15 removes them; the go does not change running behavior by itself.

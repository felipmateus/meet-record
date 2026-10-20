---
status: pending
title: "Task 8: Quality gate and shadow rollout"
type: qa
complexity: medium
---

# Task 8: Quality gate and shadow rollout

## Overview

Measures, before the real daemon runs the curator on the user's meetings, whether the analyzer finds progress statements precisely and whether the curator keeps the document right over a sequence of synthetic days; then, with the user's approval, restarts the daemon so the curator runs alongside the 18:00 planner (rollout B, the shadow). Both evaluations spend the Claude subscription and the restart touches the daemon that records the user's real meetings, so each step waits for the user.

## Shippable Outcome

- Outcome: `scripts/fidelity_eval.py` can plant status updates and score them (Q-001) and can run the curator sequence (Q-002); both have run with the user's approval and their scores are recorded against the `_tests.md` targets; the installed daemon runs the new code (after the user approved `trec agent restart`) and the first real pass appears in `log/activities.jsonl`.
- Verify in this task: Q-001 and Q-002 results; `trec doctor` / `trec agent status` after the restart; one real pass record.
- Integration verification: Q-003 (the shadow week itself) belongs to the go-gate, task_12.

## Requirements

- **Ask the user before running Q-001 and before running Q-002** (each spends the Claude subscription; give the estimated number of calls). Keep the evaluation data directories outside the repo (AGENTS.md: `CLAUDE.md` is inherited).
- **Ask the user before `trec agent restart`** (a recording may be in progress); never install, uninstall or restart the LaunchAgent without that approval.
- Targets: `_tests.md` › Quality Evaluations Q-001 (recall and precision ≥ 90%, verifier flags injected false updates including an intention planted as `done` and a wrong new date) and Q-002 (the full target list; run at effort `medium` and `high` before fixing the default). Thresholds may be tuned after the first run only with the user's agreement (`_spec.md` › Open Questions).
- Prompt tuning that a failed target calls for stays inside the spec's rules (`prompts/analyze_system.md`, `prompts/curate_system.md`); a change of rule goes back to the spec.
- The harness changes must not break `tests/unit/test_eval_harness.py`; plan-reading parts of the scripts stay until task_14.

## Subtasks

- [ ] 8.1 Extend `scripts/fidelity_eval.py` with planted status updates and traps (Q-001) and the curator sequence with a simulated user between and during passes (Q-002), scored by an LLM judge against the planted-fact key.
- [ ] 8.2 Ask the user; run Q-001; record scores; tune and re-run if a target misses (each run asked).
- [ ] 8.3 Ask the user; run Q-002 at `medium` and `high`; record scores and the chosen default effort.
- [ ] 8.4 Ask the user to approve `trec agent restart`; after it, confirm the worker is up and a real pass is logged.

## Implementation Details

### Relevant Files

- `scripts/fidelity_eval.py`, `scripts/wiki_corpus.py` — existing harnesses (`setup|oracle|inject|defend|report|gate|…`).
- `tests/unit/test_eval_harness.py` — harness tests.
- `_spec.md` › Monitoring and Observability — thresholds watched in the shadow week.

### Dependent Files

- task_12 reads the shadow week's pass log against the same thresholds.

## Deliverables

- Harness extensions and their unit tests; recorded Q-001 / Q-002 results (in this task's completion notes); the daemon restarted with the user's approval.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before running. Ask the user before running each one.

- [ ] Q-001 — analyzer status updates and verifier injection (`fidelity_eval`).
- [ ] Q-002 — curator sequence (~10 working days, ~25 synthetic meetings, simulated user).

## Success Criteria

- `pytest` (one session) and `mypy` green after the harness changes; `tests/unit/test_no_hardcoded_strings.py` green.
- The shadow is running only after the user approved the restart; nothing is committed without the user's approval.

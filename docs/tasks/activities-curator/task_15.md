---
status: pending
title: "Task 15: Documentation of the planner removal"
type: docs
complexity: low
---

# Task 15: Documentation of the planner removal

## Overview

Removes the daily plan from the project's documentation and describes what replaced it: the activities document as the one place to look, stories drafted only from `#história` tags, publishing without plans, audio retention in the daemon and the removed `trec plan`. After this task no page tells the user to wait for the 18:00 plan.

## Shippable Outcome

- Outcome: `AGENTS.md`, `README.md`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 and `docs/prd/` describe slice 2 accurately and no longer mention the planner except as removed.
- Verify in this task: a read-through against `_dx.md` and the merged code; a search for `trec plan`, `planner`, `open_actions` and `18:00` in the changed docs finds only historical notes.
- Integration verification: none.

## Requirements

- **Prerequisite: the user has said "go" after the shadow week (ADR-002; recorded in task_12).** Depends on task_13 and task_14.
- `AGENTS.md` (`_spec.md` › Impact Analysis, AGENTS.md row, slice-2 part): ports table removes `Planner`, changes `StoryWriter` (`draft_from_blocks`, writer sets kind/priority/due) and `StoryRenderer` (`render(drafts, existing, degraded)`); the LLM-stack list drops `planner_claude`; commands drop `trec plan` and show `trec stories` without `--date`; the intro sentence about the daily plan; the daemon-scheduled purge under the restart rule; the scheduler row without the planner job.
- `docs/prd/pages/06-daily-plan.md` (the plan replaced by the document), `08-user-stories.md` (tag-based drafting, publishing without plans), `04-automation.md` / `05-operations.md` / `07-installation.md` where they mention the planner job or `trec plan`, `docs/prd/README.md` and the appendices (`data-layout.md`: `plans/` keeps only story drafts; `enum-dictionary.md`: `ActionStatus.OVERDUE` decode-only).
- `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10: dated note for the planner removal and stories on demand.
- `README.md`: no `trec plan`; `trec stories` from tags.
- English only. Do not add offline Windows installer documentation here.

## Subtasks

- [ ] 15.1 `AGENTS.md`.
- [ ] 15.2 PRD pages and appendices.
- [ ] 15.3 REQUIREMENTS §10 and README.

## Implementation Details

### Relevant Files

- `AGENTS.md`, `README.md`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md`, `docs/prd/README.md`, `docs/prd/pages/04-automation.md`, `05-operations.md`, `06-daily-plan.md`, `07-installation.md`, `08-user-stories.md` (all mention the planner today), `docs/prd/appendix/data-layout.md`, `docs/prd/appendix/enum-dictionary.md` (`overdue` row), `docs/prd/appendix/relationships.md` (mentions the planner).

## Deliverables

- Updated documentation (the `docs` commit of the slice-2 wave, committed only with the user's approval).

## Success Criteria

- Every command, config key and file name in the changed pages exists in the code; `pytest` unaffected.

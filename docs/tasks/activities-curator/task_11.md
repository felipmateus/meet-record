---
status: completed
title: "Task 11: Documentation of the shadow slice"
type: docs
complexity: low
---

# Task 11: Documentation of the shadow slice

## Overview

Brings the project's documentation in line with what slice 1 shipped: the analyzer's progress statements and minutes section, the activities document and its files, the curator worker, `trec activities` / `curate` / `undo`, the doctor and status lines, the `[activities]` config, and the new ports. During the shadow the planner still exists, so these pages describe both side by side; task_15 removes the planner from them.

## Shippable Outcome

- Outcome: `AGENTS.md`, `README.md`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 and the relevant `docs/prd/` pages describe the slice-1 behavior accurately; a reader can find the document, its files and every new command.
- Verify in this task: a read-through against `_dx.md` and the merged code (commands, config keys, file names match).
- Integration verification: none.

## Requirements

- `AGENTS.md` (`_spec.md` › Impact Analysis, AGENTS.md row, slice-1 part): ports table gains `ActivityCurator` (`curator_claude.ClaudeCurator`), `ActivityStore` (`activities_fs.FsActivityStore`) and the `MeetingRepository` error-file methods; the LLM-stack import exception names `curator_claude`; commands list `trec activities [--open] | curate | undo`; the English-only rule gains the Portuguese allowance for `messages.ActivityDoc`, the curator's one-line summaries in notification bodies and CLI lines, and the focus lines `trec activities` prints; the `activities/` lock and file layout; the `CuratorWorker` under the restart rule. The planner entries stay until task_15.
- `docs/prd/pages/03-analysis.md` (status updates, `for_whom`, the minutes section); the activities document in `docs/prd/` (follow `docs/prd/README.md` for whether it is a new page or a section of `06-daily-plan.md`); `docs/prd/appendix/data-layout.md` (the `activities/` tree, `curation_error.txt`, `log/activities.jsonl`).
- `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10: phase status and a dated note for the curator in shadow.
- `README.md`: `trec activities` and the document.
- English only; Portuguese only where it quotes document labels.
- Do not add offline Windows installer documentation here (it lives in the `meet-record-windows` repository).

## Subtasks

- [x] 11.1 `AGENTS.md`.
- [x] 11.2 PRD pages and the data-layout appendix.
- [x] 11.3 REQUIREMENTS §10 and README.

## Implementation Details

### Relevant Files

- `AGENTS.md`, `README.md`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md`, `docs/prd/README.md`, `docs/prd/pages/03-analysis.md`, `docs/prd/pages/06-daily-plan.md`, `docs/prd/appendix/data-layout.md`.

## Deliverables

- Updated documentation (the `docs` commit of the slice-1 wave, committed only with the user's approval).

## Success Criteria

- Every command, config key and file name in the changed pages exists in the code; `pytest` unaffected.

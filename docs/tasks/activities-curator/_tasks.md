---
schema_version: "spec-tasks/v2"
workflow: activities-curator
graph:
  nodes:
    - id: task_01
      file: task_01.md
    - id: task_02
      file: task_02.md
    - id: task_03
      file: task_03.md
    - id: task_04
      file: task_04.md
    - id: task_05
      file: task_05.md
    - id: task_06
      file: task_06.md
    - id: task_07
      file: task_07.md
    - id: task_08
      file: task_08.md
    - id: task_09
      file: task_09.md
    - id: task_10
      file: task_10.md
    - id: task_11
      file: task_11.md
    - id: task_12
      file: task_12.md
    - id: task_13
      file: task_13.md
    - id: task_14
      file: task_14.md
    - id: task_15
      file: task_15.md
  edges:
    - from: task_02
      to: task_03
    - from: task_01
      to: task_04
    - from: task_02
      to: task_04
    - from: task_03
      to: task_04
    - from: task_01
      to: task_05
    - from: task_02
      to: task_05
    - from: task_03
      to: task_05
    - from: task_04
      to: task_06
    - from: task_05
      to: task_06
    - from: task_06
      to: task_07
    - from: task_07
      to: task_08
    - from: task_03
      to: task_09
    - from: task_05
      to: task_09
    - from: task_07
      to: task_09
    - from: task_06
      to: task_10
    - from: task_07
      to: task_10
    - from: task_07
      to: task_11
    - from: task_09
      to: task_11
    - from: task_10
      to: task_11
    - from: task_08
      to: task_12
    - from: task_11
      to: task_12
    - from: task_12
      to: task_13
    - from: task_13
      to: task_14
    - from: task_13
      to: task_15
    - from: task_14
      to: task_15
---

# Tasks: Activities curator

> Spec: [_spec.md](_spec.md) · Stories: [_user_stories.md](_user_stories.md) · Surface: [_dx.md](_dx.md) · Tests: [_tests.md](_tests.md) · ADRs: [001](adrs/adr-001.md), [002](adrs/adr-002.md), [003](adrs/adr-003.md)
> Rules that apply to every task: AGENTS.md (English only, except the Portuguese labels in `messages.ActivityDoc` / `messages.Minutes` and the prompts' requested output; strings in `messages.py` / `constants.py`, meeting file names in `domain/status.py`; `tests/unit/test_no_hardcoded_strings.py` green; `pytest` and `mypy` green; never two pytest sessions at once). Ask the user before committing (commits go in waves per layer, `docs/COMMITS.md`), before `trec agent restart` (a recording may be in progress), before touching the installed daemon or LaunchAgents, and before any run that spends the Claude subscription or API credit (Q-001, Q-002, Q-003, `TREC_REAL_*` tests). Never read `.env`, never write under `data/` or `backlog/`.

**Slice 1 — the curator in shadow (tasks 1–11).** The Motivating Problem is solved by tasks 1–7: after each analyzed meeting the daemon (or `trec analyze`, or `trec activities curate`) updates `data/activities/atividades.md`, with the analyzer's progress statements verified and listed in the minutes, while the 18:00 planner keeps running untouched. Task 8 runs the quality gate (Q-001, Q-002, with the user's approval) and starts the shadow rollout with `trec agent restart` (Build Order steps 1–5). Tasks 9–10 add undo, the not-curated listing in `trec doctor` / `trec status` (Build Order step 6). Task 11 documents the slice.

**Slice 2 — planner removal and stories on demand (tasks 12–15), behind the go-gate.** ⛔ **Go-gate: task_12.** Nothing in slice 2 starts until the shadow week has run and the user has explicitly said "go" (ADR-002; Q-003). task_12 records that decision; task_13, task_14 and task_15 depend on it and must not be dispatched without it. If the user says no-go, slice 2 stays pending and the misses become spec changes.

| Task | Title | Slice | Type | Complexity | Depends on | Tests owned |
| --- | --- | --- | --- | --- | --- | --- |
| task_01 | Progress statements in the analysis, verifier and minutes | 1 | feature | medium | — | UT-028, UT-050–UT-055, UT-057–UT-059 (10) |
| task_02 | The pure document functions | 1 | feature | high | — | UT-001–UT-015, UT-018–UT-024, UT-026, UT-027, UT-029, UT-112–UT-117 (31) |
| task_03 | Ports, fakes and the file-backed activity store | 1 | feature | critical | task_02 | UT-109, UT-125, IT-012, IT-014 (4) |
| task_04 | The Claude curator and its prompt | 1 | feature | high | task_01, task_02, task_03 | none in `_tests.md` (adapter cases inline) |
| task_05 | The curation use case | 1 | feature | high | task_01, task_02, task_03 | UT-030–UT-044, UT-046–UT-049, UT-100–UT-102, UT-104–UT-106, UT-123, IT-003–IT-005, IT-010, IT-013, IT-016, IT-019 (33) |
| task_06 | Pipeline hook, container wiring and the daemon's curator worker | 1 | feature | high | task_04, task_05 | UT-045, UT-107, UT-108, UT-120, IT-001, IT-002, IT-008 (7) |
| task_07 | `trec activities`, `trec activities curate` and the curation step of `trec analyze` | 1 | feature | medium | task_06 | UT-080–UT-086, UT-088, UT-089, UT-110, E2E-001, E2E-002 (12) |
| task_08 | Quality gate and shadow rollout | 1 | qa | medium | task_07 | Q-001, Q-002 (2, ask before running) |
| task_09 | Undo the last pass | 1 | feature | high | task_03, task_05, task_07 | UT-060–UT-066, UT-118, UT-119, UT-126, IT-006, IT-007, IT-015, IT-020, IT-021, E2E-003 (16) |
| task_10 | Not-curated meetings in `trec doctor` and `trec status` | 1 | feature | low | task_06, task_07 | UT-087, E2E-005 (2) |
| task_11 | Documentation of the shadow slice | 1 | docs | low | task_07, task_09, task_10 | none |
| task_12 | Shadow week review and the go decision | 2 | qa | medium | task_08, task_11 | Q-003 (1, the go-gate) |
| task_13 | Stories from tagged lines; publishing without plans | 2 | feature | high | task_12 | UT-016, UT-017, UT-070–UT-079, UT-093, UT-111, UT-121, UT-122, UT-124, IT-009, IT-017, E2E-004 (20) |
| task_14 | Remove the planner; audio retention in the daemon | 2 | refactor | high | task_13 | UT-056, UT-090–UT-092, UT-094–UT-098, IT-011, IT-018 (11) |
| task_15 | Documentation of the planner removal | 2 | docs | low | task_13, task_14 | none |

Withdrawn test IDs (owned by no task, per `_tests.md`): **UT-025**, **UT-103**.

Graph notes:
- task_01 (analyzer) and task_02 (pure domain) start in parallel. task_03 needs `box_stamp`, `PassRecord` and the `DocFormat` from task_02 for reconciliation. task_04 and task_05 both need the ports and fakes of task_03 and the `status_updates` of task_01; they can run in parallel.
- `pending()` and `not_curated()` are methods of `CurateMeetings` and stay in task_05; the queue rebuilt at daemon start is in task_06 (Build Order step 5). Step 6's remaining surfaces (undo, the doctor/status lines and the listing journey) are tasks 9–10. `_spec.md` › MVP Boundary puts the recovery rule in its slice 2 while Build Order step 5 puts the queue rebuild in step 5; this graph follows the Build Order.
- task_08 owns the evaluations and the `trec agent restart` that starts the shadow; tasks 9–11 can land during the shadow week (undo, doctor and status are CLI-side; a later daemon restart for them needs the user's approval too).
- Slice 2 order differs from Build Order steps 7 → 8 on purpose: tag-based stories do depend on the story use cases leaving `planning.py` and on the new `StoryRenderer.render(drafts, existing, degraded)`, so the move is done in task_13 together with the tag drafting; deleting the planner (task_14) then deletes what is left of `planning.py`. Doing step 7 first would delete `DraftUserStories` and leave `trec stories` with no drafting path until step 8.

---
status: pending
title: "Task 13: Stories from tagged lines; publishing without plans"
type: feature
complexity: high
---

# Task 13: Stories from tagged lines; publishing without plans

## Overview

Stories stop being drafted automatically from the daily plan: `trec stories` drafts a story only for each block the user tagged `#história` in the activities document, sends it with its meetings' analyses to the story writer, merges the drafts into today's file and replaces the tag with a link to the draft, never waiting on the curator and never drafting a line twice. Publishing keeps working for new and old drafts without any plan file, because the story use cases leave `planning.py` for `use_cases/stories.py` and the drafts document is rendered only from what `*.stories.json` stores. This prepares the planner removal (task_14), which deletes what remains of `planning.py`.

## Shippable Outcome

- Outcome: `trec stories` behaves and prints as `_dx.md` › `trec stories` (including the busy-lock and skipped cases, no `--date`); `trec publish` publishes block stories and planner-era drafts alike with no plan file; `trec plan` no longer drafts stories and `[stories] enabled` is ignored.
- Verify in this task: UT-016, UT-017, UT-070–UT-079, UT-093, UT-111, UT-121, UT-122, UT-124, IT-009, IT-017, E2E-004.
- Integration verification: none beyond E2E-004 (owned here).

## Requirements

- **Prerequisite: the user has said "go" after the shadow week (ADR-002; recorded in task_12). Do not start without it.**
- Contracts: `_spec.md` › Core Interfaces (`TaggedBlock`, `tagged_blocks`, `replace_tag`; `StoryWriter.draft_from_blocks`; `StoryRenderer.render(drafts, existing, degraded)`; `TagDraftResult`, `DraftStoriesFromTags` steps 1–5; `UserStory.source_text`, `SkippedAction.source_line`, `is_task_card` on stored `kind`, `ActionRoute`/`route_of` deleted), › Data Models › Story drafts, › Key Decisions (tag drafting idempotent through the drafts file; story writer contract changes), Safety Invariant 10; `_dx.md` › `trec stories`, › Errors (stories rows), › Config (`[stories]`).
- Move `PublishUserStories`, `PublishReport` / `PublishedStory` / `PublishFailure`, `recent_stories`, `stories_waiting` and `untrusted_sources(repo, meeting_ids)` to `application/use_cases/stories.py` with no plan input; delete `DraftUserStories`, `Err.PLAN_MISSING`, the routing helpers and plan-based drafting (`StoryWriter.draft`, its prompt part); keep `Err.STORIES_MISSING` for a day without drafts. `BuildDailyPlan` and `PurgeOldAudio` stay in `planning.py` for task_14.
- `trec plan` (still present until task_14) stops calling the story drafting; `[stories] enabled` is read and ignored.
- `DraftStoriesFromTags`: the writer call runs without the lock; `lock(wait=False)` only for the tag replacements (document and `base.md`, line found exactly once); busy → `deferred`, exit 0; a block already in the recent drafts (today included, `dedup_days + 1`) is never sent to the writer again; no pending-replacement file.
- The writer sets `kind` (feature, bug, technical, operation; anything else is a skip with the reason), `priority` and `due` from the block and its meetings' analyses; `prompts/stories_system.md` gains the blocks mode and loses plan-based drafting; the user's guide is still appended and re-read on every call.
- Old `*.stories.json` files (planner-era) load, render (stories by their stored meetings, skips by `action_id` and reason) and publish.
- Texts in `messages.Cli` / `messages.Err` / `messages.StoryDoc`.

## Subtasks

- [ ] 13.1 Model fields (`source_text`, `source_line`), codec round trip, `is_task_card` on stored `kind`; delete `ActionRoute` / `route_of` / `task_card`.
- [ ] 13.2 `use_cases/stories.py` with the moved publishing helpers (no plan input) and `StoryRenderer.render(drafts, existing, degraded)`.
- [ ] 13.3 `tagged_blocks`, `replace_tag`, `TaggedBlock` in `domain/activities.py`.
- [ ] 13.4 `StoryWriter.draft_from_blocks` in `stories_claude.py` and the prompt; remove plan-based drafting.
- [ ] 13.5 `DraftStoriesFromTags`; `trec stories` without `--date`; `[stories] publish` after drafting; remove drafting from `trec plan`; ignore `[stories] enabled`.
- [ ] 13.6 Tests, including the busy-lock journeys on a real `flock`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/use_cases/planning.py:70-300` — `DraftUserStories` (deleted) and the publishing helpers (moved).
- `src/teams_recorder/adapters/outbound/stories_claude.py:99-166` — writer call and message builder; `:116-128` derived priority/due/kind.
- `src/teams_recorder/adapters/outbound/stories_markdown.py` — renderer.
- `src/teams_recorder/domain/models.py:396-398` — `is_task_card`.
- `src/teams_recorder/adapters/outbound/repository_fs.py:318-330` — story drafts persistence.
- `src/teams_recorder/adapters/inbound/cli.py:620-700` — `plan`, `stories`, `_draft_stories`, `_draft_then_publish`, `publish`.
- `src/teams_recorder/container.py:140-153` — story builders.
- `src/teams_recorder/config.py:94,284` — `stories_enabled`.
- `tests/unit/test_planning_use_cases.py`, `test_stories_claude.py`, `test_stories_markdown.py`, `test_story_provenance.py`, `tests/integration/test_publish_flow.py`.

### Dependent Files

- task_14 deletes the rest of `planning.py`; task_15 documents the change.

### Related ADRs

- [ADR-002](adrs/adr-002.md) — stories on demand.

## Deliverables

- `application/use_cases/stories.py`, writer blocks mode, renderer change, model and codec fields, `trec stories`, tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [ ] UT-016, UT-017 — `tagged_blocks`, `replace_tag`.
- [ ] UT-070, UT-071, UT-072, UT-074, UT-075 — a tagged block drafted and merged, numbering, duplicate, nothing tagged, a skip.
- [ ] UT-073, UT-076, UT-077, UT-122 — edited lines, busy lock and deferred replacement, never re-drafted.
- [ ] UT-078, UT-079, UT-124 — planner-era drafts merged and rendered, stored `kind`, persisted `source_line`.
- [ ] UT-121, UT-111 — publishing with no plan; `[stories] publish`.
- [ ] UT-093 — `[stories] enabled` ignored.
- [ ] IT-009, IT-017 — `trec stories` on a real store; a child holding the `flock`.
- [ ] E2E-004 — tag a line of the E2E-001 document and draft it.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- Tests use throwaway boards and fake writers; nothing is published to the user's real `backlog/`.
- If the daemon must pick this up, `trec agent restart` only with the user's approval; commits only with the user's approval.

---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 260
severity: medium
author: claude-code
provider_ref:
---

# Issue 012: Blocks-mode stories leave StoryRenderer and UserStory fields undefined

## Review Comment

The spec changes only `StoryWriter` (`draft` → `draft_from_blocks`, `_spec.md:260-262`). It says drafts are "unchanged in shape", with `source_action_ids` holding block refs (`b1`…) (`_spec.md:349`). It also deletes `ActionRoute`/`route_of`/`task_card` (`_spec.md:392`). The code depends on actions in places the spec does not cover:

- `StoryRenderer.render(drafts, actions: list[Action], existing, degraded)` (`src/teams_recorder/application/ports.py:148-150`). `MarkdownStoryRenderer` maps `source_action_ids` to `Action`s to print each source action with its timestamp (`src/teams_recorder/adapters/outbound/stories_markdown.py:34-48`). In blocks mode there are no `Action`s, and the day's file merges new block stories with stories drafted earlier by the planner during the shadow period. Their `source_action_ids` are real action ids that `DraftStoriesFromTags` has no way to load once `load_plan`/`load_open_actions` are deleted.
- `UserStory.priority`, `due` and `kind` are derived from source actions (`strongest_priority`, `earliest_due`, `story_kind` in `src/teams_recorder/adapters/outbound/stories_claude.py:116-128`). `kind` becomes a board label (`publisher_backlogmd.py:77`). For a block, the spec does not say where these come from.
- `UserStory.is_task_card` calls `route_of(self.kind)` and `ActionRoute.TASK` (`src/teams_recorder/domain/models.py:396-398`). The CLI uses it too (`src/teams_recorder/adapters/inbound/cli.py:665`). Deleting `route_of`/`ActionRoute` breaks it, yet existing `*.stories.json` files contain task cards that `trec publish` ("unchanged", `_dx.md:221`) must still publish.
- `SkippedAction.action_id` and `duplicate_of` are keyed by action id. US-014 AC-2/AC-3 need them per block.
- `[stories] publish = true` auto-publishes after drafting today (`cli.py:673-679`). The spec does not say whether tag-based `trec stories` keeps that.

Suggested fix: add `StoryRenderer` to the changed ports, with blocks as the source description (the tagged text plus link labels) and old stories rendered from their stored fields without actions. Keep `is_task_card` working on stored `kind`: inline `kind in {TECHNICAL, OPERATION}` and delete only the routing functions. State how priority, due and kind are set for block stories (by the writer from the block text, or None). Decide on `publish`. Add a UT for merging a block story into a planner-era drafts file and rendering it.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified: `StoryRenderer.render` takes `Action`s, `UserStory.priority/due/kind` come from source actions, `is_task_card` calls `route_of`, `SkippedAction` is keyed by action id, and auto-publish exists; the spec deleted the supporting code without defining the replacements.
- Reopened (round 2): the renderer contract was changed but the other consumer of plan actions was not. `PublishUserStories` (application/use_cases/planning.py:184-226, the module the spec deletes; no new home is named) calls `self.repo.load_plan(day)` (deleted in Impact Analysis) and raises `Err.PLAN_MISSING` when it is None, re-renders after every publication with `renderer.render(drafts, plan.new_actions, …)` and computes `degraded` from plan actions. On any day without a planner plan, which is every day after slice 3, `trec publish` ("unchanged", `_dx.md`) and `[stories] publish = true` fail. The new `sources` map cannot fix the re-render either: it is built per `trec stories` call with per-call refs (`b1`…), while `SkippedAction` entries are persisted in `*.stories.json` (codec.py:478,486) and merged across runs, so a publish-time re-render has no `sources`, and a later run's `b1` describes an earlier run's skipped `b1`. `stories_waiting` (used by `trec status`, cli.py:135), `recent_stories` and `untrusted_sources` also live in planning.py. Needed: name the module `PublishUserStories` and these helpers move to; persist each skipped block's first line (e.g. a description field on `SkippedAction`) so `render` needs no transient `sources`; derive `degraded` from the stories' `source_meetings`; add a UT that publishes a block-only drafts file with no plan file.
- Verified (round 3): `application/use_cases/stories.py` is named as the new home of `PublishUserStories`, its report types, `recent_stories`, `stories_waiting` and `untrusted_sources` (Components, Impact Analysis, Build Order step 7). `render(drafts, existing, degraded)` takes no transient input and prints the persisted `source_text`/`source_line`. `degraded` comes from the stories' `source_meetings`, and `Err.PLAN_MISSING` is deleted. UT-121 (block-only publish with no plan file) and UT-124 cover it. The only `load_plan` mentions left are in the deletion list and in UT-121's negative assertion.

### Resolution

Fixed. `StoryRenderer` joins the changed ports (`render(drafts, sources, existing, degraded)`); new `UserStory.source_text` (tagged block verbatim); a planner-era story in the same file renders from its stored meetings only (its actions are no longer loadable; stated as a one-day transition effect); the writer sets `kind` (feature/bug/technical/operation, others skipped with a reason), `priority` and `due` from the block and its analyses, or none; `is_task_card` is inlined on stored `kind` and only `ActionRoute`/`route_of` are deleted, so old `*.stories.json` still load, render and publish; `SkippedAction.action_id` holds the block ref; `[stories] publish` keeps auto-publishing (default false). Spec: Core Interfaces, Data Models, Impact Analysis, Key Decisions; `_dx.md` stories notes; US-014 EC-5. Tests: UT-078 (block story merged into a planner-era drafts file), UT-079, UT-111.

### Resolution (round 2)

Round-2 fix. New home `application/use_cases/stories.py` for `DraftStoriesFromTags`, `PublishUserStories` (+ `PublishReport`, `PublishedStory`, `PublishFailure`), `recent_stories`, `stories_waiting` and `untrusted_sources`; `planning.py` is deleted (only `PurgeOldAudio` goes to `retention.py`). Inputs no longer depend on plans: `PublishUserStories` loads `*.stories.json` only, re-renders with `renderer.render(drafts, existing, degraded)`, `degraded` from `untrusted_sources(repo, ids)` over the stories' `source_meetings`; `Err.PLAN_MISSING` is deleted (`STORIES_MISSING` stays). `StoryRenderer.render` loses the transient `sources`: block stories print the persisted `UserStory.source_text`, skipped blocks print the new persisted `SkippedAction.source_line` (per-run `b1` refs are never looked up after a call), planner-era entries render from stored fields. Updated: spec (Components, Core Interfaces, Data Models, story-drafts paragraph, Impact Analysis, Build Order step 7), `_dx.md` publish note, US-014 AC-4. Tests: new UT-121 (block-only publish with no plan file), UT-124, UT-078 rewritten.

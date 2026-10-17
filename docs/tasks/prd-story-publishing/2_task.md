# Task 2.0: Duplicate check across days and the redraft lock

## Overview

When drafting, give the model the stories of the last `dedup_days` days so it leaves out actions already covered (pointing to the covering story) instead of creating a new story; show that in the drafts document; and refuse to redraft a day whose stories were already published. Delivers FR5, FR6 and the duplicate part of FR10.

<skills>
### Skills compliance

- `prompt-engineering-patterns`: the new rule in `prompts/stories_system.md` and the "existing stories" message section.
- `python-pro`: port signature change and validation of model output.
- `python-testing-patterns`: fakes for the writer and the repository.
</skills>

<requirements>
- `StoryWriter.draft(day, actions, analyses, existing)`; the user message gains the existing-stories section (id, title, story sentence) — techspec §4.1, §5.2.
- `SkippedOut.duplicate_of` is kept only when it is the id of an existing story; invented ids are dropped (the action stays skipped).
- `prompts/stories_system.md` gains the duplicate rule (English, output in Portuguese).
- `DraftUserStories` passes the existing stories from `recent_story_drafts(day, dedup_days)` and raises `Err.STORIES_ALREADY_PUBLISHED` before calling the writer when the day's drafts have publications — techspec §4.3.
- The drafts document shows the covering story for duplicates (`StoryDoc.DUPLICATE_OF`) — techspec §5.3.
- `dedup_days` defaults to `Stories.DEDUP_DAYS` until the configuration of task 4.0 exists.
- `trec plan` still saves the plan when drafting is refused, and exits 1 (existing drafting-failure behavior).
</requirements>

## Subtasks

- [x] 2.1 Change the `StoryWriter` port and `FakeStoryWriter`; add the existing-stories section to `stories_claude.build_user_message`.
- [x] 2.2 Add `duplicate_of` to `SkippedOut` and validate it in `to_drafts`.
- [x] 2.3 Add the duplicate rule to `prompts/stories_system.md`.
- [x] 2.4 Render the duplicate reference in `stories_markdown` (title of the covering story when known, id otherwise).
- [x] 2.5 Update `DraftUserStories`: existing stories from the repository window and the redraft lock; `dedup_days` defaults to `Stories.DEDUP_DAYS` (the container passes the configured value in task 4.0, when the setting exists).
- [x] 2.6 Add the strings (`Prompt.STORIES_EXISTING`, `StoryDoc.DUPLICATE_OF`, `Err.STORIES_ALREADY_PUBLISHED`).
- [x] 2.7 Write the unit and integration tests below.

## Implementation details

See techspec §4.1 (writer port), §4.3 (use case changes), §5.2 (writer) and §5.3 (renderer).

## Success criteria

- With an existing story covering an action, a fake model answer marking `duplicate_of` produces a skipped action that references that story, and no new story.
- An invented `duplicate_of` is dropped and the action is still listed as skipped.
- Redrafting a day with any publication never calls the writer and leaves the drafts file untouched.
- `pytest` and `mypy` clean.

## Task tests

- [x] Unit tests — `tests/unit/test_stories_claude.py`: existing section present with ids and titles (absent when there are none); `duplicate_of` kept/dropped; `tests/unit/test_stories_markdown.py`: duplicate line with title and with an unknown id; `tests/unit/test_planning_use_cases.py`: existing stories come from the window only, lock raises before the writer, unpublished drafts can be redrafted.
- [x] Integration tests — `tests/integration/test_cli.py`: `trec plan --date` on a day with published drafts saves the plan, prints the refusal and exits 1 (fake drafts written with `FsMeetingRepository`).
- [ ] E2E tests — covered in 7.0 (real model on a repeated topic).

## Relevant files

- `src/teams_recorder/application/ports.py`, `application/use_cases/planning.py`
- `src/teams_recorder/adapters/outbound/stories_claude.py`, `stories_markdown.py`
- `prompts/stories_system.md`
- `src/teams_recorder/messages.py`, `constants.py`, `container.py`
- `tests/fakes/__init__.py`, `tests/unit/test_stories_claude.py`, `tests/unit/test_stories_markdown.py`, `tests/unit/test_planning_use_cases.py`, `tests/integration/test_cli.py`

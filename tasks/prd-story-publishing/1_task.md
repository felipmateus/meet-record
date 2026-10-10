# Task 1.0: Publication state and story persistence

## Overview

Give the domain a way to record where a story was published and which existing story already covers a left-out action, persist both in `plans/<day>.stories.json` (old files still load), and let the repository return the drafts of recent days. This is the data foundation for idempotent publishing (3.0), the redraft lock and the duplicate check (2.0).

<skills>
### Skills compliance

- `domain-driven-design`: value object `Publication`, behavior on `UserStory` / `StoryDrafts`, no I/O in the domain.
- `python-pro`: dataclasses, typing, backwards-compatible decoding.
- `python-testing-patterns`: round-trip and boundary tests.
</skills>

<requirements>
- `Publication` (destination, ref, published_at), `UserStory.publications` and `UserStory.publication(destination)`, `StoryDrafts.has_publications`, `SkippedAction.duplicate_of`, `PublishError` — as in techspec §3.
- JSON written before this change (no `publications`, no `duplicate_of`) loads with empty defaults.
- `MeetingRepository.recent_story_drafts(before, days)` returns the drafts of `[before - days, before)`, oldest first (techspec §4.1, §5.3).
- The drafts glob does not match plan files, and `latest_plan_before` keeps ignoring drafts files.
- Domain stays pure; strings and file patterns live in `constants.py` / `messages.py`.
</requirements>

## Subtasks

- [x] 1.1 Add `Publication`, `UserStory.publications` / `publication()`, `StoryDrafts.has_publications` and `SkippedAction.duplicate_of`; export them from `domain/__init__.py`.
- [x] 1.2 Add `PublishError` to `domain/errors.py`.
- [x] 1.3 Extend `codec` (story and drafts encoders/decoders) with the new fields and defaults for old JSON.
- [x] 1.4 Add `Files.STORIES_GLOB`, the port method `recent_story_drafts` and its `FsMeetingRepository` implementation.
- [x] 1.5 Implement `recent_story_drafts` in `InMemoryMeetingRepository` (tests/fakes).
- [x] 1.6 Write the unit and integration tests below.

## Implementation details

See techspec §3 (domain), §4.1 (repository port) and §5.3 (codec, repository). No behavior changes in use cases or CLI in this task.

## Success criteria

- A `StoryDrafts` with publications and a `duplicate_of` survives save → load unchanged.
- A drafts file written by the current branch (`feat/story-drafts`) loads with `publications == []` and `duplicate_of is None`.
- `recent_story_drafts` includes the first day of the window, excludes the `before` day and anything older than `days`.
- `pytest` and `mypy` clean; `test_no_hardcoded_strings.py` green.

## Task tests

- [x] Unit tests — `tests/unit/test_models.py`: `publication()` finds by destination and returns None otherwise; `has_publications` false for empty and unpublished drafts, true with one publication.
- [x] Integration tests — `tests/integration/test_repository_fs.py`: round trip with publications and `duplicate_of`; legacy JSON without the new keys; `recent_story_drafts` window boundaries (day before, first day, day outside, the `before` day itself); `latest_plan_before` unaffected by `.stories.json` files.
- [x] E2E tests — not applicable.

## Relevant files

- `src/teams_recorder/domain/models.py`, `domain/errors.py`, `domain/__init__.py`
- `src/teams_recorder/application/ports.py`
- `src/teams_recorder/adapters/outbound/codec.py`, `adapters/outbound/repository_fs.py`
- `src/teams_recorder/constants.py`
- `tests/fakes/__init__.py`, `tests/unit/test_models.py`, `tests/integration/test_repository_fs.py`

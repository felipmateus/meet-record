# Task 3.0: Publisher port and the publish use case

## Overview

Introduce the `StoryPublisher` port and the `PublishUserStories` use case: send each selected story to every publisher, skip what was already published there, save each publication as soon as it succeeds, keep going after failures and report everything. Delivers FR3, FR4 and the selection part of FR2, independent of any real destination.

<skills>
### Skills compliance

- `architecture-patterns`: port and strategy; fan-out in the application layer.
- `error-handling-patterns`: partial failure, collected errors, nothing lost on interruption.
- `python-testing-patterns`: fake publishers that fail on demand.
</skills>

<requirements>
- `StoryPublisher` with `destination`, `publish(story, day) -> ref` and `problems()` — techspec §4.1.
- `PublishUserStories(repo, publishers, renderer, notifier, clock, dedup_days).execute(day, only)` follows the algorithm in techspec §4.2: drafts required, 1-based `only` validated before publishing, skip per destination, save JSON and re-rendered Markdown after each success (re-rendered with the plan's new actions and `recent_stories(...)`, as in drafting), collect `TeamsRecorderError`s, one notification.
- `PublishReport` with published, already-published count and failures.
- New strings: `Err.STORIES_MISSING`, `Err.INVALID_STORY_NUMBER`, `Notify.STORIES_PUBLISHED`, `Notify.PUBLISH_FAILED` (and bodies).
- No CLI or configuration changes in this task.
</requirements>

## Subtasks

- [ ] 3.1 Declare `StoryPublisher` in `application/ports.py`.
- [ ] 3.2 Implement `PublishReport` and `PublishUserStories` in `application/use_cases/planning.py`; export it.
- [ ] 3.3 Add the strings to `messages.py`.
- [ ] 3.4 Add `FakeStoryPublisher` to `tests/fakes` (records calls, returns refs, can fail per story or always).
- [ ] 3.5 Write the unit and integration tests below.

## Implementation details

See techspec §2 (why fan-out lives in the use case), §4.1 and §4.2.

## Success criteria

- Two destinations × three stories → six publications recorded; a second run publishes nothing and reports six already published.
- One destination failing for every story does not stop the other destination; the report lists each failure.
- A failure on the second story keeps the first story's ref on disk.
- `only=[2]` publishes only story 2; `only=[9]` with three stories raises before any publish.
- `pytest` and `mypy` clean.

## Task tests

- [ ] Unit tests — `tests/unit/test_planning_use_cases.py`: all of the success criteria above with `InMemoryMeetingRepository`, `FakeStoryPublisher`, `FakeStoryRenderer` and `FakeClock`; no drafts → `RepositoryError`; notification titles and counts for success and failure.
- [ ] Integration tests — `tests/integration/test_repository_fs.py` (or a new `test_publish_flow.py`): with `FsMeetingRepository` and `MarkdownStoryRenderer`, a publisher that fails on the second story leaves a `.stories.json` with the first publication and a `.stories.md` that shows it; reloading and rerunning publishes only the rest.
- [ ] E2E tests — not applicable (covered in 7.0).

## Relevant files

- `src/teams_recorder/application/ports.py`, `application/use_cases/planning.py`, `application/use_cases/__init__.py`
- `src/teams_recorder/messages.py`
- `tests/fakes/__init__.py`, `tests/unit/test_planning_use_cases.py`, `tests/integration/test_repository_fs.py`

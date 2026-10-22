---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 316
severity: low
author: claude-code
provider_ref:
---

# Issue 005: MinutesRenderer change omits FakeMinutesRenderer and RenderMinutes' read

## Review Comment

The Impact Analysis row (`_spec.md:316`) changes the port to `render(…, language=None)` and says `AnalyzeMeeting` and `RenderMinutes` pass `transcript.language`. Two consumers are missing from the plan:

- `tests/fakes/__init__.py:432-437`, `FakeMinutesRenderer.render(self, meeting, analysis, health=None)`. Once the use cases pass `language=`, every existing use-case test that uses this fake raises `TypeError`. UT-073 (`_tests.md:143`, "AnalyzeMeeting passes transcript.language to the renderer") also needs the fake to record the value.
- `RenderMinutes.execute` (`src/teams_recorder/application/use_cases/processing.py:199`) loads the transcript only to take `.health`. It has to keep the transcript, or load it once, to pass `language`. The no-transcript branch must pass `None`.

Suggested fix: add `tests/fakes/__init__.py` (`FakeMinutesRenderer` gains `language` and records it) and the `RenderMinutes` change to the Impact Analysis and to task 5. Make UT-073 assert on the fake's recorded `language` for both use cases.

## Triage

- Decision: `VALID`
- Notes: Valid. `FakeMinutesRenderer.render` (`tests/fakes/__init__.py:432-437`) would raise `TypeError`, and `RenderMinutes` loads the transcript only for `health`.
- Verified: `tests/fakes/__init__.py:432-437`, `processing.py:188-202`.

### Resolution

Impact row now lists `AnalyzeMeeting`, `RenderMinutes` (keeps the transcript it loads, passes its `language`, `None` without a transcript) and `FakeMinutesRenderer` (gains the keyword, records `languages`). Build order task 5 and File References updated. UT-073 asserts on the fake's recorded language for both use cases; matrix row US-006.AC-3/AC-4 lists UT-073.

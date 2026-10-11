# Task 4.0: Ports, the ingest use case and the pipeline post-step

## Overview

Declare the `WikiWriter`, `WikiStore` and `WikiHistory` ports, write the `IngestMeetingIntoWiki` use case that orchestrates the two model calls, the validation and the writes under the wiki lock, the `wiki_pending` helper and `RebuildWiki`, and hook the ingest into the pipeline as a post-step that can fail without touching the meeting's state. Everything here runs on fakes; the real writer arrives in task 5.

<skills>
### Skills compliance

- `domain-driven-design`: the use case holds the rules (skip, force, sources merge, failure record); adapters hold no policy.
- `tdd-workflow`: each rule in techspec §4.2 becomes a test on fakes before the code.
- `python-testing-patterns`: the pipeline tests cover isolation and resume with the existing `test_pipeline.py` style.
</skills>

<requirements>
- Ports exactly as in techspec §4.1 (methods only, `Path` the only I/O type), with `FakeWikiWriter` (scripted plan and edits, records the messages it received) added to the fakes.
- `application/use_cases/wiki.py`: `IngestOutcome`, `IngestMeetingIntoWiki` with the eight steps of techspec §4.2 (skip unless `--force`; transcript optional and truncated; lock held through both calls; `initialize`; plan refs validated before reading; `validate_edits`; meeting page from `MinutesRenderer` with the related-pages section; sources ∪ meeting id, `created` kept, `updated` from the clock; index and log written by code; history commit fail-soft; `WikiIngest` saved; failures → `mark_wiki_failed` and re-raise); `wiki_pending(repo)`; `RebuildWiki`.
- `Pipeline.ingest` optional post-step and `resume_pending` extension (techspec §4.3): a failure logs, notifies `Notify.WIKI_FAILED` and returns `ANALYZED`; never `error.txt`.
- `Step.WIKI`, `Notify.WIKI_FAILED/_BODY`, `Err.WIKI_*`, `Log.WIKI_*` in `messages.py`.
</requirements>

## Subtasks

- [ ] 4.1 Add the three ports and `FakeWikiWriter`.
- [ ] 4.2 Implement `IngestMeetingIntoWiki` and `IngestOutcome`.
- [ ] 4.3 Implement `wiki_pending` and `RebuildWiki`.
- [ ] 4.4 Extend `Pipeline` (post-step, resume) and its container wiring is left to task 6.
- [ ] 4.5 Write the tests below.

## Implementation details

The meeting page is written even when the model returns nothing usable, so the wiki always has a source page per ingested meeting and the index always lists it. `analysis_hash` is the SHA-256 of the analysis JSON as the codec serializes it (stable ordering), truncated to 12 hex chars; `schema_version` likewise over the schema text. On `--force`, `WikiSource.previous` carries the earlier record so the writer can be told which pages already hold this meeting. `RebuildWiki` reports like the CLI loop (per meeting ok/failed) and never deletes the backup.

## Success criteria

- Skip, force, missing transcript, truncated transcript, rejected edits, all-rejected, lock timeout, writer failure, history failure and a malformed wiki each behave as techspec §4.2 and §10 say, proven on fakes.
- After an ingest the fake store holds: the meeting page with the related links, each accepted page with merged `sources` and correct `created`/`updated`, a regenerated index listing every page, one log entry.
- `Pipeline.process` on a transcribed meeting ends `analyzed` with `wiki.json` present when the fake writer succeeds, and `analyzed` with `wiki_error.txt` and a notification when it fails; `resume_pending` ingests an analyzed meeting without `wiki.json` and leaves one with it alone.

## Task tests

- [ ] Unit tests — `tests/unit/test_wiki_use_cases.py` (new; the cases above, `wiki_pending` ordering and filtering, `RebuildWiki` backup + clear + loop); `tests/unit/test_pipeline.py` (post-step, failure isolation, resume).
- [ ] Integration tests — none new.
- [ ] E2E tests — not applicable.

## Relevant files

- `src/teams_recorder/application/ports.py`, `application/use_cases/wiki.py` (new), `application/pipeline.py`
- `src/teams_recorder/messages.py`
- `tests/fakes/__init__.py`, `tests/unit/test_wiki_use_cases.py` (new), `tests/unit/test_pipeline.py`

---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 125
severity: medium
author: claude-code
provider_ref:
---

# Issue 006: MeetingRepository additions and the notice marker are not specified

## Review Comment

`_spec.md:125` says "The repository gains the loaders/savers for the two files and the daily-notice marker", and the tests depend on them:
- UT-033: `repo.load_active().speakers_handle`
- UT-040: "the repository raises while loading the speaker log"
- UT-042: "the notice marker holds today"

Core Interfaces (`_spec.md:132-214`) define none of these methods: no names, no signatures, no missing-vs-unreadable semantics, no error types. That covers:
- writing the `unavailable` line;
- loading the speaker log, which needs an epoch and an end (UT-020: `speaker_log_from_lines(lines, epoch, end)`), without saying where they come from;
- saving and loading `energy.json`;
- reading and writing the marker.

`MeetingRepository` (`application/ports.py:149-192`) is the contract between task 1 (repository and `FakeRepository`) and task 4 (use cases), so leaving it implicit invites two incompatible guesses.

The marker lives in `data/log/` (`Settings.log_dir`, `config.py:140-141`). That is outside the repository's documented layout (`recordings/`, `plans/`; `repository_fs.py:1-8,90-96`). US-008.EC-1 needs "unreadable = absent" and an atomic rewrite, and neither is stated.

Suggested fix: list the new port methods with their behaviour, and the fake's counterpart. For example:
- `write_speakers_unavailable(id, reason)`
- `load_speaker_log(id) -> SpeakerLog | None` (None when absent, `RepositoryError` when unreadable, epoch source named)
- `save_energy(id, ...)` and `load_energy(id)`
- `last_notice_day() -> date | None` and `save_notice_day(day)`

## Triage

- Decision: `VALID`
- Notes: Fixed: `MeetingRepository` additions specified with semantics (`write_speakers_unavailable`, `load_speaker_log(id, fallback_epoch, end)`, `save_energy`, `load_energy`, `last_notice_day`, `save_notice_day`); the marker lives at `<data_dir>/notices/speaker-labels`, unreadable = absent. (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: The `MeetingRepository` additions are specified with semantics in `_spec.md` Core Interfaces and implemented in `application/ports.py`, `repository_fs.py` (marker at `<data_dir>/notices/<key>`, unreadable = absent) and the fake in `tests/fakes`; `tests/unit/test_speakers_codec.py` and UT-044 pass. (review round 2, reviewer A)

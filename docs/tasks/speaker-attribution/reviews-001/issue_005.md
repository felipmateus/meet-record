---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 365
severity: medium
author: claude-code
provider_ref:
---

# Issue 005: No-label reason: derivation not total, invariant 5 breakable

## Review Comment

UT-046 maps four states of `speakers.jsonl`: an `unavailable` line, `seen` without a match, `stop` without `seen`, and no file. Three states that happen in practice are missing:
- The helper died mid-call before reading any tile: the file has `start` only, with no `stop` and no `seen`. This is the "Helper dies mid-call" case in the `_dx.md` Errors table.
- The helper was SIGKILLed after the stop timeout (`process_control.terminate`, `process_control.py:94-122`), so no `stop` line was written.
- The file is empty.

Invariant 5 ("the two never coexist") can break on the start path. `process_control.spawn` raises `EXITED_EARLY` when the child exits within the startup grace (`process_control.py:48-66`). By then the helper may already have created `speakers.jsonl` and written `start`, and the use case then writes the `unavailable` line into that file. The spec says neither overwrite nor append, nor which line wins on read. An exit code 3 inside the grace (permission revoked after `--check`) would also be reported as `start-failed` unless the adapter maps exit codes; that mapping is unspecified.

The CLI has no path to the reason. `trec transcribe` receives only the `Transcript` from `TranscribeMeeting.execute` (`adapters/inbound/cli.py:317`), yet `_dx.md` prints `Speakers: no labels (<reason>)`. The spec does not say whether the use case returns the reason, the transcript stores it, or the CLI re-reads the events.

Suggested fix:
- Define the reason over every file state, including "observer stopped before any window was read".
- Make the `unavailable` write an atomic replace (the helper is dead by then) and let `unavailable` win on read.
- Map exit 3 to `permission-missing` and exit 4 to `start-failed`.
- Name the carrier of the reason (for example a summary persisted with the transcript, see issue 008).
- Add unit tests for each case.

## Triage

- Decision: `VALID`
- Notes: Fixed: `no_label_reason` is total over the file states (`observer-died`, `no-window`, `no-match`, `no-observer`, the `unavailable` codes); the `unavailable` write is an atomic replace and wins on read (invariant 5); the adapter runs `--check` before spawning so an early exit is `start-failed`; the reason is carried by the transcript's summary (UT-018, UT-023, UT-046, UT-072). (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: `no_label_reason` is total over the file states (`_spec.md` Core Interfaces and reason table; `domain/speakers.py:134-144`); `write_speakers_unavailable` is an atomic replace and the codec lets `unavailable` win (`codec.speaker_log_from_lines`); exit 3 maps to `permission-missing` in the adapter (UT-072); the reason is carried by `LabelSummary`. UT-018, UT-023 and UT-046 pass. (review round 2, reviewer A)

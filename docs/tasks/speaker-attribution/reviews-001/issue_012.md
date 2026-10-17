---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 421
severity: low
author: claude-code
provider_ref:
---

# Issue 012: Take the event time origin from the start event; flush every line

## Review Comment

`_spec.md:421` and UT-020 convert event times with `epoch = meeting.started_at.timestamp()`, computed at transcription time.

`meeting.started_at` is a naive local datetime stored with `isoformat()` (`adapters/outbound/codec.py:59-70`), and `.timestamp()` reads it in the timezone current at that moment. The recorders, though, were aligned to the epoch computed at start (`application/use_cases/recording.py:41`; teams-tap pads the track from that instant, `native/teams-tap/Sources/teams-tap/main.swift:203-213`). If the timezone changes between recording and transcription (travel, or a resume after a restart), every event shifts by the offset and the labels silently drop to zero.

The helper already echoes the epoch it was given in its `start` event (`_dx.md:50`). That is the authoritative origin, yet `_spec.md:240` allows it to be null and `--epoch` is optional.

The helper contract (`_spec.md:216-222`) also never requires each JSON line to be flushed as it is written. US-007.EC-3 ("events written so far are kept") depends on that. So does the SIGKILL escalation in `process_control.terminate`, and so does `stop_capture` reading the subject right after the stop (UT-030).

Suggested fix: make `--epoch` mandatory for the observer. Take the origin from the `start` event and fall back to the meeting's start only when the event is missing, with a unit test for the fallback. Require line-at-a-time flushing in the helper contract.

## Triage

- Decision: `VALID`
- Notes: Fixed: `--epoch` is mandatory, the time origin is the `start` event's epoch with the meeting start as fallback (UT-020, UT-027), and the helper flushes every line (invariant 10). (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: `--epoch` is mandatory in the helper (`main.swift` argument parsing, usage line) and in the adapter command; the codec takes the origin from the `start` event with the meeting start as fallback (UT-020, UT-027 pass); invariant 10 and the helper header require one write(2) per line on an O_APPEND descriptor. (review round 2, reviewer A)

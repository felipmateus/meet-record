---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_dx.md
line: 195
severity: high
author: claude-code
provider_ref:
---

# Issue 004: Daily notice: reason set, scope and "day" disagree across documents

## Review Comment

The four documents disagree on which reasons notify:

| Source | Reasons |
| --- | --- |
| PRD FR7 | permission missing, not built, no window read |
| US-008.AC-1 | permission missing, not built, no window read, no line matched |
| `_dx.md:197-202` (bodies) | permission missing, not built, no window read, failed to start |

"No line matched" has no body. "Failed to start" is not in US-008. "No observer data for this meeting" (a `_dx.md` transcribe reason) has neither a body nor a rule.

Scope is undefined. The business rule (`_spec.md:53`) fires on any zero-label meeting. With `[speakers] enabled = false`, or on Windows (`_windows_adapters` passes `speakers=None`, `_spec.md:126`, while energy is still measured), a meeting where the user did not speak has zero labels and reason "no observer data". That produces a daily "Speaker labels unavailable" notice for a feature that is off or absent on the platform. US-011.AC-3 tries to exclude old meetings "unless it ended after this feature shipped", but nothing records a ship date, so the rule cannot be implemented or tested. UT-046 only maps the reason.

"Calendar day" is ambiguous: the day of the meeting, or of the transcription? A resume after a restart transcribes yesterday's meeting today. Invariant 9 does not say which. `TranscribeMeeting` has no `Clock` field today (`application/use_cases/processing.py:43-50`), and UT-042–044 need one; Core Interfaces do not add it.

Suggested fix: add one table to `_dx.md` mapping each reason code to whether it notifies and to its body constant. State that no notice fires when no observer was wired (feature off, Windows). Replace the ship-date clause with a checkable rule, for example notify only when `speakers.jsonl` exists. Name the day source (`clock.now()` at transcription) and add `clock` to `TranscribeMeeting` in Core Interfaces.

## Triage

- Decision: `VALID`
- Notes: Fixed: one reason table in `_dx.md` (code → transcribe line → notifies → body); no notice without an events file (feature off, Windows, pre-feature); `no-match` logs only; the day is the transcription day via `TranscribeMeeting.clock`; US-008 and US-011 reworded; PRD FR7 note added. (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: `_dx.md` has one reason table (code, transcribe line, notifies, body); the business rule and invariant 9 notify only when the events file exists and use the transcription day (`TranscribeMeeting.clock`). `processing.TranscribeMeeting._notify_no_labels` follows it (`SpeakerReason.notifies`, NO_OBSERVER silent, `no-match` log only); UT-042 to UT-047 in `tests/unit/test_transcribe_speakers.py` pass, including the yesterday-marker case. (review round 2, reviewer A)

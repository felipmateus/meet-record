---
provider: manual
pr:
round: 3
round_created_at: 2026-10-23T16:25:44Z
status: resolved
file: docs/tasks/speech-check/_tests.md
line: 45
severity: low
author: claude-code
provider_ref:
---

# Issue 004: US-002.EC-3 (one notification per transcription) has no test

## Review Comment

US-002.EC-3 (`_user_stories.md:59`) is a contract: "The same recording is transcribed twice → two notifications, one per transcription. There is no de-duplication."

The coverage matrix maps the whole of US-002 to UT-041 (`_tests.md:45`). UT-041 (`:136`) transcribes each case once, and checks only the 59.9 / 60.0 / 309.6 s boundary. UT-049 (`:146`) transcribes twice, but it asserts only the stored transcript. No case calls `execute` twice on a no-speech meeting and counts the notifications.

So an implementation that de-duplicates would pass the whole planned suite. One example is reusing the daily key of an existing notification, or skipping the notification when the stored transcript is already no-speech. That breaks the stated rule, "each one deserves a look" (`_spec.md:74`).

There is a smaller gap of the same kind. US-003.EC-1 (`_user_stories.md:72`, the vans meeting: 6.2 of 36.4 min of speech is found) has no row of its own. Only gate G1 exercises it (`_tests.md:228`). Map it to G1 explicitly.

Suggested fix: extend UT-041 or UT-049 with a case that transcribes the same 309.6 s no-speech meeting twice and expects 2 calls on `FakeNotifier`. Add a matrix row for US-002.EC-3 that names that case, and one for US-003.EC-1 that names G1.

## Triage

- Decision: `VALID`
- Notes: Valid. No case transcribes a no-speech meeting twice and counts notifications, and US-003.EC-1 had no row.
- Verified: `_tests.md` coverage matrix, UT-041, UT-049.

- Verified (round 4, 2026-10-23): UT-041 (`_tests.md:139`) has the repeat case (two `execute` calls → 2 `Notify.NO_SPEECH` calls on `FakeNotifier`). The matrix has rows for US-002.EC-3 (UT-041 repeat case), US-003.AC-1 auto mode (UT-056) and US-003.EC-1 (gate G1, vans). Every matrix ID is defined and every defined ID is in the matrix, counting the ranges UT-010–UT-013, UT-020–UT-023 and UT-060–UT-063: UT-001–008, 010–018, 020–023, 025–026, 030–036, 040–053, 055–056, 060–064, IT-001–005 and E2E-001–002.

### Resolution

UT-041 gains a repeat case (two `execute` calls → 2 `Notify.NO_SPEECH`). The matrix gains rows for US-002.EC-3 (UT-041 repeat case), US-003.EC-1 (gate G1, vans) and the US-003.AC-1 auto-mode case (UT-056).

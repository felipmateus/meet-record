---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 67
severity: medium
author: claude-code
provider_ref:
---

# Issue 008: One failing meeting burns retry attempts of its batch-mates

## Review Comment

A pass curates up to four meetings plus every pending one (`_spec.md:67`, `:124`). A failed pass is recorded with all of its meetings (`PassRecord.meetings`, `_spec.md:226`). A meeting stops being retried after 2 failed attempts (`_spec.md:67`, Safety Invariant 9, UT-038).

A meeting that fails on every attempt is called a "poison" meeting below. Examples: an analysis whose content keeps making the model break the open-line rule, or one that pushes the output past the token limit. Such a meeting gets added to every pass for two days. Each of those passes fails as a whole, and each failure counts against every innocent meeting in the batch. Example sequence:

1. P fails alone (P: 1 failure).
2. M1 is analyzed. The pass is M1 + P and fails (M1: 1, P: 2). M1 gets `curation_error.txt` and a failure notification, although it may be fine.
3. M2 and M3 finish together. The pass is M2 + M3 + M1 and fails again because of M1's content, or succeeds.

In the worst case a healthy meeting reaches 2 failures and drops out of automatic retry for a reason it does not own. The notifications also blame the wrong meetings (`_dx.md:294`). No test covers a mixed batch.

Suggested fix: when a pass with more than one meeting fails, isolate before counting. Re-run the batch one meeting at a time in the same worker cycle, or count a failure only against meetings in single-meeting passes. Pending meetings that already have a failure could also be curated alone. Add a test to UT-038: a batch failure caused by one meeting does not exclude the others.

## Triage

- Decision: `VALID`
- Notes: Valid. A failed multi-meeting pass was recorded against every meeting in it and each failure counted toward the 2-attempt cap, so a poison meeting exhausted its batch-mates.
- Verified: Business Rules "Batching", `CurateMeetings.execute` contract, Key Decisions, Safety Invariant 9, US-011 AC-7, US-015 EC-2; UT-038 (batch record not an attempt) and UT-102 (poison + healthy).

### Resolution

Fixed as suggested (re-run one at a time before counting). Business Rules "Batching", Key Decisions, Core Interfaces (`CurateMeetings.execute` re-runs a failed multi-meeting pass one meeting at a time; only a failed single-meeting pass produces the meeting's error file, attempt and notification; `pending()` counts only such records), Safety Invariant 9, US-011 AC-7, US-015 EC-2, `_dx.md` curate notes. Cost stated (up to N extra calls on a failed batch). Tests: UT-038 (batch record is not an attempt), UT-102 (poison + healthy batch).


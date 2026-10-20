---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 327
severity: medium
author: claude-code
provider_ref:
---

# Issue 002: Undo sets base to before, hiding the user's edits from later passes

## Review Comment

UT-061 (`_tests.md:141`) fixes the undo result as "document = before, base = before". `_before` is the re-read F' of the undone pass N (`ActivityStore.commit(F', written, …)`, `_spec.md:143`). That text already contains every edit the user made before pass N (pass N received them as `diff(base_{N-1}, F)`) and during pass N (stored only in pass N's `during_edits`). After the undo:

- `diff(base, document)` is empty, so the next pass does not see those edits.
- The next `user_edits` starts with "the last meeting/undo record's `during_edits`" (UT-035). That is now the undo record, and the spec gives its `during_edits` no value. So pass N's during-call edits are gone too.
- Undo also truncates the archive entries pass N appended.

Concrete loss: the user deletes open item X. Pass N archives X as `removido por você`. The user undoes pass N. The document stays without X (X was already gone in `_before`), the archive entry is truncated, and no later pass sees the deletion. X is now in no document and no archive, only in a version file that rotates out after 50 passes. This breaks Business Rules "Never delete" and "Deleted items", and Goal 2 ("an open item leaves the document only by being archived with a reason"). The same applies to ticks the user made before pass N: the curator no longer sees them as user changes to act on (✔ and move).

Simulated (scratchpad `sim/edits_sim.py`):

```
user_edits after undo: [] (X deletion seen before undo: ['-- [ ] X · [M0][m0]'] )
```

Write order is a second gap. Safety Invariant 7 orders "document before archive truncation". It does not place `base.md` or the undo record. If the CLI is interrupted between the document restore and the base write, `base` stays as pass N's base and the document is `_before`. That is the same misattribution as reviews-002/issue_001: the whole pass reads as deleted by the user.

Suggested fix: on undo, restore `base.md` to the base pass N started from, and carry forward the edits pass N had consumed. One option: store pass N's input base as a fourth version file (`_prevbase`) and set `base = _prevbase`, with `during_edits` of the undo record = pass N-1's `during_edits`. Then `diff(base, document)` again shows every user edit since pass N-1. Specify the undo write order (document → base → undo record → archive truncation) and what reconcile does with a stop inside it. Rewrite UT-061 and add a UT: "user deletes X, pass archives it, undo → next pass's `user_edits` shows X deleted".

## Triage

- Decision: `VALID`
- Notes: Valid. Undo set base = `_before` = F' of pass N, which already holds the user's edits made before N (N consumed them as diff(base, F)) and during N (only in N's `during_edits`), so after the undo no later pass saw them; a deletion archived by N became unrecoverable. The write order of undo was also unspecified.
- Verified (round 3): I traced the sequence N-1, N, undo N, M. After the undo, base = `_prevbase_N` = B(N-1), the document = F'(N) and the undo record's `during_edits` = `carried_N` = during(N-1). M's `user_edits` therefore shows each user edit made before or during N exactly once. The write order (document → base → pass log → `truncate_archive`) is stated, and IT-020 reconciles a stop inside it. UT-118 and UT-119 hold. Undoing the very first pass (base.md absent) cannot be expressed with the specified types; that is tracked in reviews-003/issue_002.

### Resolution

Fixed by making undo a commit through the same journal as a pass (simplification: no separate restore protocol and no separate reconcile). `commit` now also writes `_prevbase` (base.md as the pass read it). Undo = `commit(current, N.before, [], N.prevbase, undo_record)` (document, then base = `_prevbase`, then the pass-log line) followed by `truncate_archive` last; the undo record's `during_edits` = N's new `carried_edits` field, so the next `<user_edits>` again shows every user edit around N. A stop inside the undo is reconciled by the same stamp rule. Added `PassRecord.carried_edits` and `undoes`. Updated: spec (Core Interfaces, Key Decisions, Invariant 7), ADR-003, `_dx.md`, US-010 AC-6, UT-061 rewritten, new UT-118, UT-119, IT-015 rewritten, new IT-020.


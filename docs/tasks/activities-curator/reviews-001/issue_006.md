---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 453
severity: medium
author: claude-code
provider_ref:
---

# Issue 006: base.md derivation is ambiguous and misattributes authorship

## Review Comment

`<user_edits>` (the diff from `base.md` to the document) is how the curator tells the user's lines from its own. Principle 1 (`_spec.md:360`) depends on it: never reword, move or archive what the user wrote. The spec defines base as "the snapshot the curator read with its own ops applied (fallback: the written document)" (`_spec.md:453`). UT-030 says "base = snapshot + ops" (`_tests.md:74`). Three cases are undefined, and each one sends a wrong diff:

1. **Box and link block.** `render_box`/`render_links` run on the written document W (`_spec.md:134`). If they are not also applied to base, every following pass sees the new box header, focus and link definitions as user edits.
2. **Ops that applied to F' but fail on F.** The user's edit during the call created or changed the target, or the op is a repair op written against the in-memory F' text (`_spec.md:131-132`). Such an op is missing from base. The next diff then shows the curator's own new line as a line the user added, and from then on the curator treats it as untouchable user text: no date updates, no archiving, no dedup.
3. **Ops that apply to F but failed on F'** before the repair: is base built from the original ops, the repaired ops, or both?

The "fallback" condition is never stated (when does code fall back?). There is also no test where an op behaves differently on F and F'.

Suggested fix: specify base precisely and simply. For example: base = W with the during-call user edits reverted, computed as `apply_ops(F, ops_that_applied) → render_box → render_links`. When any applied op does not apply to F in the same way, fall back to base = W and record `unified_diff(F, F')` (the user's during-call edits) in `.curator/pending_edits.diff`. The next pass then prepends it to `user_edits`. Add UT cases for (1) the box is not in the next diff, and (2) a repair op that only matches F' does not show up as a user edit.

## Triage

- Decision: `VALID`
- Notes: Valid. The old definition (snapshot + own ops, undefined fallback) mishandled the box and links, ops that fit F' but not F, and repair ops; no test distinguished F from F'.
- Verified: base = `render_links(render_box(W))` from the written text (box, focus and links included, rescued lines excluded), `PassRecord.during_edits = unified_diff(F, F')`, next `user_edits = during_edits + diff(base, document)`; UT-030/035/049/100 cover the three cases the issue named. New defects in the same area (undo resetting base, box line seen twice) are reviews-002/issue_002 and issue_005.

### Resolution

Fixed differently from the suggested wording, for a simpler invariant. Instead of replaying ops on F (which needs a fallback condition and breaks for repair ops written against in-memory text), base is derived from what code actually wrote: `base = render_links(render_box(W))` where W is F' after the applied ops, so box, focus and links are in it and nothing depends on whether an op fits F. What the user did during the call, `unified_diff(F, F')`, is stored in `PassRecord.during_edits` (in the pass record, not a separate `pending_edits.diff` file, so it commits atomically with the pass) and the next pass sends `during_edits + diff(base, document)` as `<user_edits>`. Lines rescued from the box are excluded from base (they are the user's). Spec: Key Decisions bullet rewritten, System Architecture, PassRecord, Data Models, Safety Invariant 12, `CuratorInput.user_edits`; ADR-003 shares the commit mechanics. Tests: UT-030 and UT-035 rewritten, UT-049 (box not in next diff, during-call edit seen once), UT-100 (repair op matching only the in-memory text is not a user edit), IT-016.


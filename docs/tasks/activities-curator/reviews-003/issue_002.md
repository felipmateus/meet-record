---
provider: manual
pr:
round: 3
round_created_at: 2026-10-20T01:04:08Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 320
severity: low
author: claude-code
provider_ref:
---

# Issue 002: Undo-as-commit cannot express a first-pass undo; stamp ≠ version

## Review Comment

The round-2 fix for reviews-002/issue_002 routes undo through `commit`. Three cases the tests require are not covered by the specified types and wording.

1. **Undoing the first pass needs "no base", and the types cannot say it.** IT-006 (`_tests.md:210`, two passes, then undo twice) and UT-119 ("the first pass undone → base removed and `user_edits` \"\" as for a first pass", `_tests.md:158`) both undo the very first pass. Its `_prevbase` is "`base.md` as it is" (`_spec.md:354`, `:647`), but no `base.md` exists then. `VersionFiles.prevbase: str` (`_spec.md:345`) and `commit(…, base: str, …)` (`_spec.md:352`) have no "absent" value, and reconcile's roll-forward writes "`base.md` from `_base`" (`_spec.md:647`). Writing `""` instead makes the next `user_edits = unified_diff(body(""), body(document))`, which lists the whole skeleton as user additions and contradicts UT-119.

2. **"The stamp is the version" is false for an undo record.** `PassRecord.version` says "the same string is the stamp in the box's closing marker" (`_spec.md:320`). Key Decisions and ADR-003 say "the pass stamp = the version". An undo does not render a box. It writes N's `_before`, whose stamp belongs to the pass before N, or is `None` when N was the first pass. Reconcile is right only in the form "`box_stamp(document) == box_stamp(_after)`", with `None == None` counted as replaced. IT-020 relies on that form. If an implementer follows the `PassRecord` comment and compares with `record.version`, an undo interrupted after the document restore is rolled back. `base.md` then stays B(N) while the document is N's `_before`, and the next pass reads all of pass N as deleted by the user: the damage reviews-002/issue_001 fixed. IT-020 would catch this, but the spec contradicts itself on the rule.

3. Minor: `carried_edits` (a required `str`) has no stated value on an undo record. ADR-003 › Implementation Notes (`adrs/adr-003.md:74`) still lists `restore`, which `ActivityStore` no longer has.

Suggested fix: type `prevbase`/`base` as `str | None` (None means delete `base.md` and write no `_prevbase`/`_base` file) and say so in `commit` and in reconcile. Reword the `PassRecord.version` comment and the Key Decisions/ADR-003 sentence: "a pass writes its version as the stamp; reconcile compares with the stamp of `_after`, which for an undo is the restored text's (possibly none)". Set `carried_edits = ""` on undo records. Remove `restore` from ADR-003. Add a store test: undo of the first pass interrupted before and after the document restore.

## Triage

- Decision: `VALID`
- Notes: All three points are real contradictions inside the spec. (1) "no base" had no representation: `VersionFiles.base/prevbase` and `commit(base)` are now `str | None`; `None` means no `_base`/`_prevbase` file, `commit` deletes `base.md`, and reconcile rolling forward a set with no `_base` file deletes it too, so the next pass sees `user_edits` "" as on a first pass (a `""` base would list the whole skeleton as user additions). `UndoLastPass` comment says so. (2) `PassRecord.version` comment, Key Decisions, ADR-003 and Safety Invariant 3 now say a meeting pass writes its version as the stamp, and reconcile compares `box_stamp(document) == box_stamp(_after)`, with `None == None` counted as replaced (an undo's `_after` is the restored text, whose stamp is an earlier pass's or none); `version` is never the comparison value. (3) `carried_edits` is `""` on an undo record (undo records are never undone) in `PassRecord`, the Data Models row, `UndoLastPass` and UT-061; `restore` removed from ADR-003 Implementation Notes (now `truncate_archive`). Tests: UT-119 and UT-061 state `base=None`; new UT-126 (store: `base=None` writes no file and deletes `base.md`; reconcile compares stamps, `None == None` is replaced) and IT-021 (undo of the first pass interrupted before and after the document restore). Spec-only change; no source touched.
- Verified: (round 4) (1) `VersionFiles.base/prevbase` and `commit(base)` are `str | None` (`_spec.md:343-355`), `None` = no file and `base.md` deleted, in commit and in reconcile roll-forward; `UndoLastPass` comment (`_spec.md:420-422`), Key Decisions (`_spec.md:650`), ADR-003 Decision, UT-061, UT-119 agree. (2) `PassRecord.version` comment (`_spec.md:318`), Key Decisions (`_spec.md:649`), Safety Invariant 3 and ADR-003 now say reconcile compares `box_stamp(document) == box_stamp(_after)` with `None == None` as replaced, never `version`; UT-126 pins it. (3) `carried_edits` "" on undo records in `PassRecord`, Data Models (`_spec.md:527`), `UndoLastPass`, UT-061; ADR-003 Implementation Notes lists `truncate_archive`, no `restore`. IT-021 covers the first-pass undo stopped before and after the restore; coverage rows US-010 and Safety Invariants list UT-126/IT-021. One new edge introduced by the `None == None` rule is tracked separately as reviews-004/issue_001.

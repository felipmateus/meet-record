---
provider: manual
pr:
round: 4
round_created_at: 2026-10-20T01:14:11Z
status: resolved
file: docs/tasks/activities-curator/_tests.md
line: 223
severity: low
author: claude-code
provider_ref:
---

# Issue 001: `None == None` rolls forward a first-pass undo never restored

## Review Comment

The round-3 fix for reviews-003/issue_002 decides reconcile by `box_stamp(document) == box_stamp(_after)` and counts `None == None` as replaced (`_spec.md:348`, `:649`; Safety Invariant 3; ADR-003 Decision; UT-126). For an undo of the first pass, `_after` is the skeleton, which has no stamp (UT-117: "None for a skeleton box with no stamp"). The rule therefore reads any document without a stamp as "restored".

Failure mode (one hard stop plus one edit, the same preconditions ADR-003 already lists as a risk):

1. Pass N is the first pass. The user runs `trec activities undo`. The undo commit writes its version set and stops hard before the document restore. The document is still N's `_after`, stamped N.
2. Before the next `lock()`, the user deletes the box, or edits its closing marker so it no longer carries the stamp. `box_stamp(document)` is now `None`.
3. Reconcile compares `None == None`, counts it as replaced and rolls the undo forward. `base.md` is deleted, and the undo record (`undoes = N`) is written to the pass log. The document still holds all of pass N's content.
4. Pass N now counts as undone, so the next `undo` walks past it (UT-063) and raises `NothingToUndo`. The user cannot undo a pass whose content is still in the document. With `base.md` gone, the next pass gets `user_edits` "", so any deletion the user made to N's items is not reported to the curator.

The spec states the opposite in two places:

- IT-021 (`_tests.md:223`) ends with "a user edit to the document between the stop and the lock does not change either outcome".
- ADR-003 › Risks (`adrs/adr-003.md:69-70`) covers only the other direction: a deleted stamp makes a replaced document look unreplaced, so it is rolled back.

Before round 3, this direction could not happen, because every `_after` carried a stamp. A second, smaller inaccuracy in the same Risks list: "an editor overwrite that restores an old buffer … rolls back" is no longer always true for an undo. An old buffer that carries the stamp of pass N-1 equals the undo's `_after` stamp, so reconcile rolls forward. Here that outcome matches the disk, but the sentence is wrong.

Suggested fix (pick one):

- (a) Remove `None` from the comparison. The skeleton that UT-031 creates gets a fixed sentinel stamp in its closing marker (for example `00000000-000000`, a `DocFormat`/`constants` value), so every `_after` has a stamp. Drop the `None == None` clause, and a missing stamp in the document always means roll back. That is the direction ADR-003 already accepts, and it leaves a consistent "undo did not happen" state that the user can retry. Update UT-117, UT-126 and IT-021 (b), where both stamps become the sentinel.
- (b) Keep the rule, but record this direction in ADR-003 › Risks as accepted. Remove "does not change either outcome" from IT-021, or limit it to edits outside the closing marker (the wording UT-117 already uses). Also correct the editor-overwrite sentence for undo sets.

## Triage

- Decision: VALID
- Notes: Confirmed from the spec text: after round 3 an undo of the first pass has the skeleton as `_after`, which carried no stamp, so `None == None` counted any stamp-less document as replaced. Root cause: the skeleton was the only document the app writes without a stamp, which forced a `None == None` clause into the reconcile rule. Fix (reviewer's option a), spec only:
  - `DocFormat.skeleton_stamp` (`constants.Activities.SKELETON_STAMP = "00000000-000000"`) is the fixed stamp in the skeleton's closing marker (UT-031), so every document the app writes and every `_after` carries a stamp.
  - Reconcile rule: replaced iff `box_stamp(document)` is not None and equals `box_stamp(_after)`; a missing stamp in the document (user deleted or rewrote the marker) rolls back. The `None == None` clause is gone.
  - Updated: `_spec.md` (DocFormat, `box_stamp`, `PassRecord.version`, `lock()`, flow line, Commit order, Undo, Safety Invariant 3, `doc_format()`), `_tests.md` (UT-116, UT-117, UT-031, UT-126, IT-021 with new cases (c) and (d)), `adrs/adr-003.md` (Decision and Risks, including the corrected editor-overwrite sentence for undo sets). No test ID added or renumbered; `_dx.md` unaffected.
  - Accepted direction (ADR-003 › Risks): a stop after an undo's restore plus a deleted marker rolls the undo back, a consistent "undo did not happen" state the user retries.
- Verified: round 5 (2026-10-20). No `None == None` clause remains in `_spec.md`, `_tests.md` or `adrs/adr-003.md`. `DocFormat.skeleton_stamp` = `constants.Activities.SKELETON_STAMP` = `00000000-000000` (`_spec.md:209`, built by `doc_format()` at `:151`, UT-116). The rule "replaced iff `box_stamp(document)` is not None and equals `box_stamp(_after)`" is stated in `lock()` (`:349`), the flow (`:134`), Safety Invariant 3 (`:678`) and the ADR-003 Decision. UT-126 asserts that a missing stamp rolls back even when `_after` also has none. IT-021 (c) covers the reported failure (first-pass undo stopped before the restore, then the marker deleted → roll back, no `base.md` deletion, no undo record, the pass is not counted as undone). IT-021 (d) covers the accepted opposite direction. In ADR-003 › Risks, the deleted-stamp risk for undo and the editor-overwrite sentence now match the rule. Every test ID referenced from `_spec.md`/ADR-003 is defined in `_tests.md`. One residual prose inaccuracy that this fix introduced is filed as reviews-005/issue_001 (low).

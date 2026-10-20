---
provider: manual
pr:
round: 5
round_created_at: 2026-10-20T01:18:02Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 209
severity: low
author: claude-code
provider_ref:
---

# Issue 001: "every `_after` carries a stamp" is false for a stamp-less `_before`

## Review Comment

The round-4 fix (reviews-004/issue_001) adds the claim that every `_after` now carries a stamp:

- `_spec.md:209` (`skeleton_stamp`): "so every document the app writes, and every `_after` (a pass's or an undo's), carries a stamp".
- `adrs/adr-003.md` › Decision: "so every `_after` carries a stamp".
- `_spec.md:319` (`PassRecord.version`) and Safety Invariant 3 (`:678`) say an undo's `_after` has "an earlier pass's [stamp] or the skeleton's".

This is not true. An undo's `_after` is `_before_N`, the document as it stood when pass N read it. That text has no stamp when the user had already deleted or rewritten the closing marker before pass N ran, which `_spec.md:208`, `:227` and UT-117 all allow. It also has no stamp when the document was not created by the app (a legacy or user-made file, which `:208` names). Pass N's `render_box` then writes a stamped box, so the user sees nothing unusual. The fix's own tests already assume the stamp-less case can happen: UT-126 asserts reconcile "rolls back even when `box_stamp(_after)` is also None". So the spec and the ADR contradict the test catalog.

Failure mode under the rule as now written (the rule itself is safe; only the documentation is wrong):

1. The user removes the stamp from the closing marker. Pass N runs, so `_before_N` has no stamp and `_after_N` carries N's stamp.
2. The user runs `trec activities undo`. The process stops hard after the document restore and before `base.md`. The user makes no edit after the stop.
3. At the next `lock()`, `box_stamp(document)` is None, so reconcile rolls back. The pass log and `base.md` still say N happened, but the document holds the restored text.
4. If a pass runs before the user retries `undo`, its `user_edits` (diff `body(base_N)` → `body(document)`) reports all of N's items as deleted by the user. IT-019 guards against exactly this outcome for passes.

ADR-003 › Risks accepts the roll-back direction only for "a deleted or rewritten stamp" edited *between a hard stop and the next lock*. This case needs no edit after the stop. The same Risks bullet also calls the rolled-back state "consistent … (the pass still counts, `base.md` and the archive are intact)". That leaves out that the document holds the restored text, not N's `_after`, both in this case and in the accepted IT-021 (d) case. A smaller wording point: `_spec.md:650` still states the rule as "replaced iff `box_stamp(document) == box_stamp(_after)`" and adds the not-None condition only in a parenthesis, while `:349`, `:678` and the ADR state it in full.

Suggested fix, spec only:

- Replace "every `_after` carries a stamp" (`_spec.md:209`, ADR-003 Decision) with "every `_after` the app produced carries a stamp; an undo's `_after` has none only when the user removed the marker before the undone pass, and then reconcile rolls back".
- Widen ADR-003 › Risks: the roll-back direction also happens after an undo of a pass whose `_before` had no stamp, with no edit after the stop. In the "consistent" sentence, say that the document holds the restored text, so the user should retry `undo` before the next pass.
- State the full condition in `_spec.md:650` ("iff `box_stamp(document)` is not None and equals `box_stamp(_after)`").
- Optional: add a sub-case to UT-126 or IT-020: a stamp-less `_before_N` plus a stop after the restore → roll back.

## Triage

- Decision: VALID
- Notes: Root cause is documentation only: an undo's `_after` is `_before_N`, which has no stamp when the user removed the marker before pass N (or the file was not app-made), so "every `_after` carries a stamp" contradicts UT-117/UT-126. The rule itself (roll forward only when stamp is not None and equal) is correct and unchanged. Fixed spec-only, as the reviewer suggested.
- Verified: changed `_spec.md` lines 209, 319, 650 and 678 (claim corrected; full condition "not None and equals" stated at 650); `adrs/adr-003.md` line 17 (Decision claim corrected) and the Risks section (undo-after-restore bullet now says the document holds the restored text and the user retries `undo` before the next pass; new bullet for the stamp-less `_before` case with no edit after the stop); `_tests.md` line 160 (UT-126 sub-case added, no renumbering). Both preflight scripts pass (check-spec-markers.py rc=0, check-spec-part1-leak.py rc=0). No source, tests, prompts or config touched.

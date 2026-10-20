---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 142
severity: low
author: claude-code
provider_ref:
---

# Issue 005: A line typed in the box mid-pass shows twice in next user_edits

## Review Comment

`during_edits = unified_diff(F, F')` (`_spec.md:142`) is computed over the whole document, box included. Suppose the user types a line in the box while the call runs:

1. The line is in F' (so it is in `during_edits`, as an addition inside the box).
2. `render_box(W)` removes it from the box, and `rescue_box_lines` writes it at the top of `## Minhas ações` in the document but not in `base` (Key Decisions, `_spec.md:604`).
3. The next pass's `user_edits = during_edits + diff(base, document)` contains the line twice: once as typed in the box, once as added under the heading.

Simulated (scratchpad `sim/edits_sim.py`):

```
next <user_edits>: ['+- [ ] Ligar para o João', '+- [ ] Ligar para o João']
times the typed line appears: 2
```

This contradicts Safety Invariant 12 ("sees every user edit once"), UT-049 ("seen exactly once") and IT-016 ("next pass's `user_edits` has both user edits once"), so IT-016 cannot pass as written. The prompt also tells the model to move box additions into a section. A box addition it sees in `<user_edits>` may lead it to insert a second copy next to the rescued one.

Suggested fix: compute `during_edits` over the body only, as `unified_diff(body(F), body(F'))`. Box lines are fully handled by `render_box` + `rescue_box_lines`, and the link block is code-written. State this in the Key Decisions bullet and in `PassRecord.during_edits`.

## Triage

- Decision: `VALID`
- Notes: Valid. `unified_diff(F, F')` ran over the whole document, so a line typed in the box mid-pass was in `during_edits` and, after `rescue_box_lines`, again as an added line in the next `diff(base, document)`: twice, contradicting Invariant 12, UT-049 and IT-016.
- Verified (round 3): `during_edits = unified_diff(body(F), body(F'))` and `user_edits = during_edits + unified_diff(body(base), body(document))` appear identically in Key Decisions, PassRecord, Data Models and the System Architecture diagram. Invariant 12, UT-123 and IT-016 now say "once", and following a line typed in the box gives exactly one occurrence in the next `user_edits`.

### Resolution

Fixed by computing every user-edit diff over the body only: `during_edits = unified_diff(body(F), body(F'))` and `user_edits = during_edits + unified_diff(body(base), body(document))` (box and link block are code-written or handled by `<box_lines>`). A box line now reaches the model once, and after a rescue appears once as an added body line. Added `body_text`. Updated Key Decisions (base.md), PassRecord, Invariant 12, UT-035, UT-049, IT-016, new UT-123.


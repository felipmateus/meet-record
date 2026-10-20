---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 503
severity: medium
author: claude-code
provider_ref:
---

# Issue 003: Spanning-replace moves let lines they pass be rewritten unchecked

## Review Comment

The round-1 fix requires every move of a checkbox line to be a single `replace` whose target is "the item plus the lines it passes" and whose text is "the same lines reordered" (prompt Edits, `_spec.md:503`; ADR-001 Negative consequences). Two moves happen in normal use:

- **Every tick.** The user ticks an item; the next pass appends ✔ and moves it to the bottom of its section (Business Rules › Ticked items, US-006 AC-2).
- **Every 💤 sink.**

So most days at least one pass re-emits the rest of a section in `text`, often all of `## Minhas ações`.

Code checks a `replace` only by counts: open(text) >= open(target) and ticked(text) == ticked(target). Every line inside the target is exempt from the backstop (`check_open_invariant` skips lines inside a target). The model must copy the target exactly, or the match fails. But its second copy, in `text`, is not compared with anything. Simulated with the rule as written (scratchpad `sim/rule_sim.py`):

```
span move that drops a user sub-line and rewords a user line accepted: True
replace '- [ ] A\n- [ ] B' -> '- [ ] A\n- [ ] C' accepted: True
```

A tick-move whose copy drops a passed user note (a plain sub-line), rewords a passed user line, or turns item B into a different item C is therefore committed silently. That contradicts:
- "Lines the user wrote or changed are never reworded" (Business Rules; US-007 AC-1/AC-2);
- "never drop a user sub-line" (Principle 4);
- ADR-001's Positive consequences ("Untouched text is byte-identical … no drift on unchanged items"), which are now false for every line a move passes;
- the Business Rules sentence "so it can neither drop, tick nor untick a checkbox, even while adding a new one", which holds only for ticking.

ADR-001's own premise for rejecting whole-document rewrites is that the model is weak at verbatim copying. The spanning move brings that copying back, on the daily path.

There is also a composition problem. "One op per item; a later op may target text an earlier op wrote" does not say how a span interacts with another op on an item it passes, for example a 💬 insert on that item. If the insert is applied first, the span's target no longer matches.

Suggested fix (keeps code rules minimal and judgment in the prompt): add a `move` op, with `target` = the item's whole lines and `anchor` = one line. Code cuts the lines and pastes them after the anchor byte for byte, so the checkbox rule and the backstop hold by construction. Spanning `replace` is then no longer needed. A cheaper alternative is to drop the move requirement: ✔ is appended in place, and the item is archived the next working day anyway. The same applies to 💤, which can stay in place. Then state the per-op rule honestly: it guards checkbox state and count, and line identity is a prompt rule measured by Q-002. Add a UT where a span changes a passed line and show what code does.

## Triage

- Decision: `VALID`
- Notes: Valid. A spanning `replace` re-emits every line it passes; code compares only counts and exempts the whole target from the backstop, so a dropped user sub-line, a reworded user line, or B turned into C was accepted (reproduced by the reviewer's simulation and by reading the rule). It also contradicted ADR-001's byte-identical claim and left span/other-op composition undefined.
- Verified (round 3): `OpKind.MOVE`, `Op.anchor`, the `move` rule in `apply_ops`, the three anchor failure messages and `CuratorOut.ops[].anchor` are all specified. `Applied.targets` excludes `move` targets, so the backstop checks them. A spanning `replace` is mentioned only as rejected history (Key Decisions title, ADR-001 Negative consequences). The prompt asks for a `move` on every reorder. UT-112 to UT-115 cover the limit, the composition and the failures.

### Resolution

Fixed with the `move` op the caller preferred: `target` = the whole item, `anchor` = one line; code cuts the lines and pastes them after the anchor byte for byte, so state, count and every passed line hold by construction, and `move` targets are not exempt from the backstop. Spanning `replace` is no longer used anywhere (prompt, ADR-001, risks, UT-023, UT-005). Composition: ops apply in order and a `move` targets the item as earlier edits left it. The per-op rule is now stated honestly: it guards checkbox state and count, not line identity, which is a prompt rule measured by Q-002 (new UT-112 shows what code does with a same-count rewrite). New failures `anchor not found | found N times | inside the target`. New UT-113, UT-114, UT-115; UT-023 and UT-025 rewritten. Schema `CuratorOut.ops[].anchor`.


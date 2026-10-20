---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 54
severity: critical
author: claude-code
provider_ref:
---

# Issue 001: Open-line invariant either misses silent drops or rejects legit edits

## Review Comment

The spec calls the open-line rule "the one code invariant", and it is the only thing in code that backs the goal "an open item leaves the document only by being archived" (Goals; Safety Invariant 1). The spec gives it in two forms that do not agree, and neither form can be implemented so that it does what the rest of the spec requires.

- **Count form** (`_spec.md:54`, Business Rules): `open(result) + open(archived) >= open(before)`. This counts lines and ignores which lines they are. A pass that drops item B with `replace ""` and also adds a new item C passes the check. So does a pass that ticks item A while adding item C. Almost every pass adds items, so on a normal pass the check never catches the failure it exists for: an open item that disappears silently, which is the Motivating Problem.
- **Line form** (`_spec.md:191`, `check_open_invariant(...) -> str | None  # first missing open line`; UT-004/UT-005 in `_tests.md:53-54`). This compares the actual open lines. It rejects edits the prompt requires on open main lines: date changes (`_spec.md:55`, Principle 1 at `:360`), adding the two latest mention links to the line (`:62`), and appending the 💤 marker (`:363`). Each of these turns the old open line into a different string, so the old line counts as missing. Those passes fail, go to repair, and are thrown away.

Evidence: I wrote a simulation of both readings (scratchpad `invariant_sim.py`, run with `python3 -I`):

```
drop B + archive A + add C   count_rule: True  line_rule: False
tick A + add C               count_rule: True  line_rule: False
date change + 💤 (legit)     count_rule: True  line_rule: False
```

The count rule accepts the two illegal passes. The line rule rejects the legitimate one. UT-004 ("a replace turning `- [ ] X` into `- [x] X` returns `- [ ] X`") passes only if no other op in the same pass adds an open line, so the test as written hides the gap.

A related gap: the repair contract (`ActivityCurator.repair(..., failures: list[OpFailure])`, `_spec.md:245`) only knows target-match errors (`"not found" | "found N times" | "targets the box..."`, `:179`). An invariant violation has no `OpFailure` form, yet US-011 AC-2 and UT-034 expect a repair round for it.

Suggested fix: make the rule per op, not per document.
1. In `apply_ops`, for every `replace` whose target contains open lines, require the replacement `text` to keep the same number of open lines, each still unticked (`- [ ] `). The text after the checkbox may change, which allows date, link and 💤 edits. A `replace` that removes open lines or ticks them fails with a new `OpFailure` error, e.g. `"removes an open line without archive"`.
2. Keep `check_open_invariant` as a backstop that counts only lines no op touched: every open line of the re-read document that no op targeted must appear byte-for-byte in the result.
3. Add cases to `_tests.md`: tick + insert in the same pass → rejected; `replace ""` on B + insert C → rejected; a date change on an open line → accepted. Then the repair path for invariant violations goes through the same `OpFailure` list.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified against the spec text: the count form (`open(result)+open(archived) >= open(before)`) accepts drop-B-add-C and tick-A-add-C, and the line form (`check_open_invariant` / UT-004 / UT-005) rejects the date, link and 💤 edits the prompt requires; `OpFailure` had no shape for a rule violation although US-011 AC-2 and UT-034 expect a repair round for one. Root cause: one document-level check was asked to do two jobs (catch a silent loss, allow edits on open lines).
- Verified: `_spec.md` Business Rules (open-line rule) and Core Interfaces (`apply_ops` per-op rule: `replace` open(text) >= open(target) and ticked equal; `insert_after` no ticked line; `archive` unrestricted), `OpFailure("breaks the checkbox rule", detail)` reaches `repair`, backstop `check_open_invariant(before, after, targets)` discards without repair; UT-004/005/019-025/029/103/104. Re-simulated the round-1 cases against the new rule (scratchpad `sim/rule_sim.py`): tick+add in one replace and `replace ""` + insert are rejected, a date/💤 edit is accepted. The residual exposure of lines passed by a spanning move is a new defect, tracked as reviews-002/issue_003.

### Resolution

Fixed in the owning spec, following the guidance and extending it where the guidance left a hole.
- `_spec.md` Business Rules: the rule is per edit and stated in one sentence for the user (only `archive` takes a checkbox line away; only the user changes a box). `replace` must keep at least its target's open lines and exactly its ticked lines (so it cannot drop, tick or untick, even while adding a new open item in the same text, which the pure open-count version would have missed); `insert_after` adds no ticked line; text after the checkbox is free (date, links, 💤). Backstop `check_open_invariant(before, after, targets)`: every open line no edit targeted is still in the result.
- Core Interfaces: `OpFailure` gains `detail` and the error `"breaks the checkbox rule"`; `Applied.targets`; `apply_ops` carries the per-op rule; `check_open_invariant` signature changed; `ticked_count` added. A backstop failure is an implementation defect: pass discarded, no repair.
- Consequence made explicit: a move of a checkbox line (sinking 💤, moving a ticked item) is one spanning `replace`, because remove-and-reinsert is what the rule forbids. Prompt (Edits, Principles 3 and 4, checklist 6), ADR-001 (new Alternative 3, Negative consequence, Implementation Notes), Safety Invariant 1, Known Risks, `_dx.md` Errors table, US-006 EC-1, US-011 AC-2 updated.
- Tests (`_tests.md`): UT-004 and UT-005 rewritten; new UT-019 (date/link/💤 edit accepted), UT-020, UT-021 (tick+add, untick), UT-022, UT-023 (spanning move), UT-024 (drop B add C rejected), UT-025 (backstop), UT-029, UT-103 (backstop discards, no repair), UT-104 (rule failure reaches repair with detail).


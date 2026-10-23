---
status: completed
title: "Task 5: Short replies are not loops"
type: feature
complexity: low
---

# Task 5: Short replies are not loops

## Overview

Natural short replies ("Okay.", "Yeah.") no longer count as a whisper hallucination loop, unless three or more short, repeated lines stand back to back. The English vans meeting's retry, at 10.4% "loops" made only of "Okay.", stops being marked degraded and stops getting a second whisper pass for nothing.

## Shippable Outcome

- Outcome: `transcript_health` on a transcript whose only repeats are spread-out short replies reports `loop_share == 0.0` and not degraded. Back-to-back short loops, and loops of lines of 3 or more words, are flagged as today.
- Verify in this task: the health unit cases, the existing health suite (one assertion updated as an intended contract change), and the alternating-lines test passing unchanged.
- Integration verification: gate G3 (task 7) on the stored transcripts.

## Requirements

- Contracts:
  - `_spec.md` › Business Rules › Loop rule;
  - `_spec.md` › Impact Analysis rows for `domain/health.py` and `tests/unit/test_transcript_health.py`;
  - `_spec.md` › Safety Invariant 7.
- A line of at most 2 words (counted on `_key`, where a key with no words counts as short) is in a loop only when both of these hold:
  - the existing window rule flags it: 5 copies within 30 consecutive segments;
  - it sits in a run of at least 3 consecutive segments that are all short and all flagged by the window rule. Their texts may differ.
- `LOOP_REPEATS` and `LOOP_WINDOW` are unchanged. `SHORT_LINE_WORDS = 2` and `SHORT_LINE_RUN = 3` are new.
- Lines of 3 or more words keep today's rule exactly.
- `test_two_lines_alternating_are_a_loop_too` passes unchanged. Only the `within` assertion of `test_a_loop_is_five_copies_within_thirty_segments…` changes, from `[0, 26, 27, 28, 29]` to `[26, 27, 28, 29]`.
- Update the module docstring of `domain/health.py`.

## Subtasks

- [x] 5.1 The short-line condition in `loop_flags`, with the two new constants.
- [x] 5.2 The new cases, and the one updated assertion.

## Implementation Details

### Relevant Files

- `src/teams_recorder/domain/health.py:22-50` — `_key`, `loop_flags`, `LOOP_REPEATS`, `LOOP_WINDOW`.
- `tests/unit/test_transcript_health.py:30-38, 64-66` — the window test whose expected indices change, and the alternating-lines test that must keep passing.

## Deliverables

- The rule change, the constants, the docstring and the tests.

## Tests

- [x] UT-010, UT-011, UT-012, UT-013, UT-014, UT-015, UT-016, UT-017, UT-018 — the loop rule (`tests/unit/test_transcript_health.py`).

## Success Criteria

- No file outside `domain/health.py` and the health tests changes.
- `pytest` and `mypy` are green.

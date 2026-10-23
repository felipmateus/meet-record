---
provider: manual
pr:
round: 1
round_created_at: 2026-10-23T14:43:57Z
status: resolved
file: docs/tasks/speech-check/_spec.md
line: 86
severity: high
author: claude-code
provider_ref:
---

# Issue 001: Short-line run rule breaks two existing loop tests and cycle detection

## Review Comment

The loop rule (`_spec.md:83-87`) flags a line of at most 2 words only when "it belongs to a run of at least 3 consecutive segments with the same comparison key". Two tests in `tests/unit/test_transcript_health.py` assert the opposite today, and the spec does not mention either one: not in Impact Analysis (`_spec.md:367`), not in `_tests.md`, not as a compatibility decision.

Runtime evidence: I applied the rule as written to the inputs of those tests, using the real `_key` and `loop_flags` in a scratch script outside the repo:
- `test_a_loop_is_five_copies_within_thirty_segments_ignoring_case_and_punctuation` (line 30): the `within` case expects `[0, 26, 27, 28, 29]`. The new rule gives `[26, 27, 28, 29]`, because the lone `Ok.` at index 0 is not in a same-key run.
- `test_two_lines_alternating_are_a_loop_too` (line 64): `["Obrigado.", "Tchau, tchau."] * 5` expects every segment flagged. The new rule flags none, because each key appears at most once in a row.

The second test is a documented capability. The `domain/health.py` docstring says the window "also catches loops cycling through several lines". Under the rule as written, a whisper loop that alternates two short lines ("Obrigado." / "Tchau.") is never a loop again. Known Risks (`_spec.md:474`) covers only a hallucination "spread out (not back to back)", not a back-to-back cycle.

One definition keeps the existing guarantee and gives exactly the Evidence numbers: a short segment counts when it is window-flagged and sits in a run of 3 or more consecutive segments that are all short and all window-flagged, whatever their keys. Recomputed read-only:

| Transcript | today | same-key run (spec) | flagged-short run |
|---|---|---|---|
| vans en retry (G2 scratch) | 10.4% | 0.0% | 0.0% |
| MARTA en (G2 scratch) | 1.2% | 0.4% | 0.4% |
| vans stored | 68.7% | 65.7% | 65.7% |
| 2026-10-17_09-56-47 | 3.8% | 1.9% | 1.9% |
| MARTA stored | 1.0% | 1.0% | 1.0% |

It also keeps both existing tests as they are. (The `within` index 0 is still dropped under any run rule, so that assertion needs a decision either way.)

Suggested fix: decide explicitly, with the user if needed, since the decision of 2026-10-22 says "unless they repeat 3 or more times in a row". Either (a) adopt the flagged-short-run definition and add an alternating-cycle UT, or (b) keep same-key runs and list both tests in Impact Analysis as contract changes, with the cycle case added to Known Risks and to the `health.py` docstring update. Either way, update `test_a_loop_is_five…`'s expected indices in the task that owns the loop rule.


## Triage

- Decision: `VALID`
- Notes: Valid. The same-key reading breaks `test_two_lines_alternating_are_a_loop_too` and drops back-to-back cycles of short lines. The user chose the flagged-short-run reading (option B, 2026-10-23).
- Verified: `tests/unit/test_transcript_health.py:30-38,64-66`, `domain/health.py:41-52`.
- Round 2 (2026-10-23): rule substance confirmed. A scratch implementation of the flagged-short-run rule on the real `_key`/`loop_flags`, patched into the full suite: `1 failed, 1316 passed, 10 skipped`, and the one failure is `test_a_loop_is_five_copies…` (listed in Impact Analysis). UT-010/011/012/014/015/017/018 expectations hold (UT-017's separated case needs distinct separators; round 2 issue 004). Reopened for leftover summary wording only: `_spec.md:19` ("unless they repeat 3 or more times in a row") and `_spec.md:33` ("A short line repeated 3 or more times in a row is still a loop") state 3-in-a-row as sufficient, and "repeat" suggests the same text. Under the adopted rule, 3 in a row without 5 copies in the window is not a loop (UT-012), and the texts may differ. Reword both, for example: "unless 3 or more short lines that the window rule flags stand back to back".

### Resolution

Adopted: a short line counts when it is window-flagged and sits in a run of 3+ consecutive segments that are all short and window-flagged, whatever their texts. Updated: Overview, Core Features 3, Business Rules › Loop rule, Executive Summary, Evidence header and note, Safety Invariant 7, Known Risks (frequent short replies back to back), Impact Analysis (`test_a_loop_is_five…` `within` → `[26, 27, 28, 29]`, the alternating test unchanged). Stories: US-005.AC-1/AC-2, new EC-4. Tests: UT-010/UT-015 made precise, new UT-017 (alternating, cites the existing test) and UT-018 (the changed assertion), and G3 records any run of different short lines.

Round 2 leftovers fixed (2026-10-23): `_spec.md:19` and `:33` now say short lines count only when the loop rule flags them and 3 or more stand in a row, same text or not.

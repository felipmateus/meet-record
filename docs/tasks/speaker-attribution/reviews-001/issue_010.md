---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 399
severity: medium
author: claude-code
provider_ref:
---

# Issue 010: The verifier prompt pin test is missing from the spec's change list

## Review Comment

The spec changes `prompts/verify_system.md:1`, which says the transcript "has no speaker labels" (`_spec.md:394`), and UT-052 requires the new sentence. Impact Analysis (`_spec.md:281`) says "update the prompt-pin tests", but File References (`_spec.md:399`) list only `tests/unit/test_llm_claude.py:149-160`.

`tests/unit/test_verifier_claude.py:151-166` (`test_the_shipped_prompt_is_the_measured_prototype_prompt`) asserts that the shipped prompt equals `VERIFY_SYSTEM` in `scripts/fidelity_eval.py` with exactly two allowed replacements, because "The evaluation's numbers (§14.3) came from" that prototype. Any edit to line 1 fails this test.

Updating it is a product decision, not a mechanical edit. One option is to change `VERIFY_SYSTEM` in the evaluation harness; the measured §14.3 numbers then no longer describe the shipped prompt. The other is to add a third allowed replacement to the test.

Suggested fix: name this test and the script in File References and Impact Analysis, choose one of the two options, and record that choice next to the fidelity gate.

## Triage

- Decision: `VALID`
- Notes: Fixed: `tests/unit/test_verifier_claude.py:151-166` and `scripts/fidelity_eval.py` added to File References and Impact Analysis; decision recorded: the label sentence is a third allowed replacement, §14.3 predates it, the fidelity gate re-measures (UT-056). (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: `_spec.md` Impact Analysis and File References name `tests/unit/test_verifier_claude.py:151-166` and `scripts/fidelity_eval.py`, with the decision (third allowed replacement; section 14.3 predates it). The pin test has the third `.replace("it has no speaker labels and may contain recognition errors.", ...)` (`tests/unit/test_verifier_claude.py:165`) and passes. (review round 2, reviewer A)

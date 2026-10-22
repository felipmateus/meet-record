---
status: completed
title: "Task 4: Analysis across languages: header line, prompts, English greetings"
type: feature
complexity: medium
---

# Task 4: Analysis across languages: header line, prompts, English greetings

## Overview

This task makes an English transcript produce Portuguese minutes with literal quotes. The analyzer's and the verifier's messages name the transcript language when it is not Portuguese. The three system prompts allow quotes to keep the language they were said in. The participant check recognises English greetings. Every Portuguese user message stays byte-identical, but the system prompts change for every meeting, so task 6's gate G3 re-measures Portuguese output.

## Shippable Outcome

- Outcome:
  - `trec analyze` on an `en` transcript sends the analyzer and the verifier the line `Transcript language: English`;
  - the prompts ask for Brazilian Portuguese output with literal quotes;
  - the curator's step 7 carries the quote exception;
  - a participant greeted once in English ("Hi John") is confirmed;
  - on a `pt` transcript, the user messages are byte-for-byte today's.
- Verify in this task: UT-050–UT-054 and the existing analyzer, verifier, curator-prompt and verification suites.
- Integration verification: gate G3 (task 6) measures Portuguese output with the changed prompts. The opt-in real-call suites (`TREC_REAL_CLAUDE_CLI=1`) exercise US-004.AC-2/AC-4 when the user runs them (ask first: they spend the subscription).

## Requirements

- Contracts:
  - `_spec.md` › Business Rules: Output language, What the model is told.
  - `_spec.md` › Impact Analysis: the `llm_schema` / `verifier_claude` row, the two prompt rows (including the step-7 text and curator lines 1, 34, 43, 281) and the `Verify.ADDRESS` row.
  - `_spec.md` › Key Decisions (the header line) and Safety Invariant 5.
  - US-004.
- The header line is `Prompt.TRANSCRIPT_LANGUAGE.format(name=…)`. The name comes from `Prompt.LANGUAGE_NAMES` (task 1); another code prints the code itself. The line goes in the header, before the transcript, only when `transcript.language != "pt"`.
- `prompts/analyze_system.md:1` stops saying every meeting is held in Brazilian Portuguese. The Language section (`:65`) keeps the Portuguese output rule and says `evidence` keeps the transcript's language. `verify_system.md` says the same for quotes.
- `Verify.ADDRESS` adds `hi|hello|hey|thanks|thank you` to the greeting group (lowercase, no accents, like the others). Its docstring says the patterns cover Portuguese and English.

## Subtasks

- [x] 4.1 The header line in `llm_schema.build_user_message` and `verifier_claude.user_message`, and `Prompt.TRANSCRIPT_LANGUAGE`.
- [x] 4.2 The wording of `analyze_system.md`, `verify_system.md`, `curate_system.md` (lines 1, 34, 43, 281) and `Prompt.CURATE_TASK` step 7.
- [x] 4.3 English greetings in `Verify.ADDRESS`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/outbound/llm_schema.py:135-149` — `build_user_message`.
- `src/teams_recorder/adapters/outbound/verifier_claude.py:135-143` — `user_message`.
- `prompts/analyze_system.md:1, 50-66`, `prompts/verify_system.md`, `prompts/curate_system.md:1, 34, 43, 281` — the wording to change.
- `src/teams_recorder/messages.py:684-693` — `Prompt.CURATE_TASK`, step 7.
- `src/teams_recorder/constants.py:226-247`, `src/teams_recorder/domain/verification.py:135-164` — `Verify.ADDRESS` and `participant_heard`.
- `tests/unit/test_llm_claude.py`, `tests/unit/test_verifier_claude.py`, `tests/unit/test_curator_prompt.py`, `tests/unit/test_verification.py` — the owning suites.

### Dependent Files

- `scripts/fidelity_eval.py` — unaffected in code. Its `defend` sends its own inline verifier prompt, which is why gate G3 does not use it.

## Deliverables

- The two message builders, the prompt and `CURATE_TASK` wording, the greetings, and the tests.

## Tests

- [x] UT-050, UT-051 — the analyzer message: no line for `pt` (byte-identical to today's), `English` for `en`, the code for `es`.
- [x] UT-052 — the verifier message carries the same line for `en` and none for `pt`.
- [x] UT-053 — the prompt texts and `CURATE_TASK` step 7, including curator line 43.
- [x] UT-054 — English greetings confirm a participant; the existing Portuguese cases pass unchanged.

## Success Criteria

- The existing short-circuit tests (`tests/unit/test_llm_claude.py`, US-004.EC-1) and every existing verification test pass unchanged.
- `tests/unit/test_no_hardcoded_strings.py` passes.

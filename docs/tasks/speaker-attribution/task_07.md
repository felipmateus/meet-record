---
status: completed
title: "Task 7: Labels, roster and owner rules in the model input"
type: feature
complexity: medium
---

# Task 7: Labels, roster and owner rules in the model input

## Overview

Lets the analysis and the verification use the labels: the analyzer's message carries the roster and says which label marks the recording owner, the prompts take owners from labelled lines and participants from the roster, the verifier reads labelled lines and the roster as evidence of presence, and the participant code check stops flagging roster names. With task 6, this closes the Motivating Problem: owners in the minutes come from who actually spoke.

## Shippable Outcome

- Outcome: for a labelled transcript, the message sent to the analyzer starts with the roster and the owner-label note and shows `[HH:MM:SS] Name: text` lines; `analysis.json` owners follow the labels; roster participants are never marked unconfirmed by the code check.
- Verify in this task: UT-050–UT-056 (prompt pins, message builders, `participant_heard`, `VerifyAnalysis`).
- Integration verification: the live gates G1 and G3 (E2E-001, task 9).

## Requirements

- Contracts: `_spec.md` › System Architecture › Downstream, › Impact Analysis (the prompt-pin tests, the verifier pin's third replacement), › File References for the prompt lines that change.
- `llm_schema.build_user_message`: when `transcript.roster` is non-empty add `Prompt.ROSTER` ("Participants seen in the meeting window: …"); when `transcript.user_label` is set add `Prompt.SPEAKER_LABELS` ("Speaker labels: the name after a timestamp is who said the line; \"<label>\" is the recording owner"); otherwise the message is byte-for-byte today's.
- `prompts/analyze_system.md`: the input paragraph says a name after the timestamp is the person who said the line and is reliable; the first-person heuristic applies to unlabelled lines only (keep the pinned sentence "the user speaks in the first person taking on a commitment"); the participants rule says that when the message lists participants seen in the meeting window, `participants` is exactly that list; the data contract says `usuário` applies to lines labelled with the owner's label whatever name it is; the schema descriptions (`Prompt.FIELD_PARTICIPANTS`, owner fields) repeat the rules.
- `prompts/verify_system.md`: replace "it has no speaker labels" with the label sentence; `verifier_claude.user_message` adds the roster line as evidence of presence; `transcript_for` renders labelled lines. `tests/unit/test_verifier_claude.py:151-166`: the label sentence becomes the third allowed replacement (recorded in the spec).
- `domain/verification.participant_heard`: also true when the name matches a segment's `speaker` or an entry of `transcript.roster` (token rules as today).
- No signature change on `MeetingAnalyzer`, `ClaimVerifier`, `AnalyzeMeeting`, `VerifyAnalysis`.

## Subtasks

- [x] 7.1 `build_user_message` and the `Prompt` constants; the analysis prompt and schema descriptions; update `test_llm_claude.py` pins (UT-050, UT-051, UT-051b, UT-055).
- [x] 7.2 The verifier prompt, message and rendering; the pin test's third replacement (UT-052, UT-056).
- [x] 7.3 `participant_heard` with labels and roster; `VerifyAnalysis` behaviour (UT-053, UT-054).

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/outbound/llm_schema.py:116-127` — `build_user_message`.
- `src/teams_recorder/adapters/outbound/verifier_claude.py:77-103,140-160` — `transcript_for`, `user_message`.
- `prompts/analyze_system.md:5-7,14,20,45-48`, `prompts/verify_system.md:1` — the sentences that change.
- `src/teams_recorder/domain/verification.py:119-140` — `participant_heard`.
- `src/teams_recorder/application/use_cases/verification.py:30-72` — `VerifyAnalysis` (unchanged signature; the code check can only lower a verdict).
- `tests/unit/test_llm_claude.py:149-160`, `tests/unit/test_verifier_claude.py:151-166`, `scripts/fidelity_eval.py` (`VERIFY_SYSTEM`) — the pins.
- `src/teams_recorder/messages.py` › `Prompt` — the new header lines and descriptions.

### Dependent Files

- `docs/tasks/prd-fidelity-guard/prd.md` — its gate re-measures the verifier prompt later (note only).

### Related ADRs

- [ADR-001](adrs/adr-001.md) — why labels are trusted attribution.

## Deliverables

- The two prompts, the message builders, `participant_heard`, the updated pin tests, the new `Prompt` constants.

## Tests

- [x] UT-050, UT-051, UT-051b, UT-055 — the analysis prompt sentences, the header lines, the `usuário` rule with a fallback label, the schema description.
- [x] UT-052, UT-056 — the verifier prompt, message and rendering; the pin's third replacement.
- [x] UT-053, UT-054 — `participant_heard` with labels and roster; `VerifyAnalysis` not flagging roster names.

## Success Criteria

- With an unlabelled transcript (empty roster, no label) every message and prompt behaviour is unchanged, and the existing prompt-pin tests still pass with their updated sentences.

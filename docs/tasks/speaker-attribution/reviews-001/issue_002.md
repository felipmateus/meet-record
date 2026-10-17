---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_user_stories.md
line: 104
severity: high
author: claude-code
provider_ref:
---

# Issue 002: US-005.AC-3 "roster participants are confirmed" cannot happen

## Review Comment

US-005.AC-3 and EC-2, and UT-054 ("a roster name never mentioned in the text is confirmed"), expect a roster member who never spoke to come out confirmed. Neither verification path can confirm them:

- A code check only flags. The `VerifyAnalysis` docstring says "A code check can only make a claim unconfirmed" (`application/use_cases/verification.py:32-36`), and `_code_checks` only adds UNCONFIRMED.
- Confirmation comes only from the model verifier, which judges claims "using only the meeting's transcript" (`prompts/verify_system.md:1`, support "unsupported (the transcript does not say it)"). The spec gives the verifier no roster, so a name never said gets `unsupported`, which means UNCONFIRMED and a ⚠️ in the minutes.
- Part II extends `participant_heard` only "to accept a labelled speaker" (`_spec.md:119,390`; PRD FR5). A roster member who never spoke is not a labelled speaker. They are also not named twice or addressed (`domain/verification.py:119-140`), so the code check flags them too.
- With `[verification] enabled = false` the claims stay unverified, which is never "confirmed" either.

Suggested fix: decide the rule and align US-005, UT-054 and Part II. Options:
- (a) `VerifyAnalysis` confirms roster participants in code, with a reason. This needs the roster (issue 001) and an amendment to the "code checks only unconfirm" rule.
- (b) The verifier's message and prompt receive the roster as evidence of presence.
- (c) Reword the acceptance criteria to "not flagged by the code check".

In every case, `participant_heard` must also accept roster names, not only labelled speakers.

## Triage

- Decision: `VALID`
- Notes: Decided: the code check does not flag roster names (`participant_heard` accepts roster and labelled speakers); the verifier receives the roster as evidence of presence and decides; US-005.AC-3/EC-2, UT-053, UT-054 and PRD FR5 note reworded accordingly. (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: US-005.AC-3/EC-2 and UT-053/UT-054 now say the code check does not flag roster names and the verifier decides; `domain/verification.participant_heard` accepts roster names and labelled speakers, the verifier message carries the roster and `prompts/verify_system.md` says listed people were present. `tests/unit/test_verify_analysis.py::test_a_roster_name_never_said_in_the_text_is_not_flagged_by_the_code_check` passes (round 2). (review round 2, reviewer A)

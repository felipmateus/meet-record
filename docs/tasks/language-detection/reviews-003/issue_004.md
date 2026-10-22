---
provider: manual
pr:
round: 3
round_created_at: 2026-10-22T00:30:08Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 325
severity: low
author: claude-code
provider_ref:
---

# Issue 004: Participant check's Portuguese address patterns are not in scope

## Review Comment

The spec treats the analysis of an English transcript as a matter of prompts and header lines (Business Rules › What the model is told, `_spec.md:54`; Impact rows `_spec.md:325-327`). `VerifyAnalysis` also runs two code checks on every analysis (`application/use_cases/verification.py:68-71`). One of them reads the transcript text with Portuguese-only patterns:

- `Verify.ADDRESS` (`src/teams_recorder/constants.py:244-247`) treats a participant as "addressed" only after `bom dia|boa tarde|boa noite|obrigad[oa]|oi|ola` + name, or name + comma. The class docstring (`constants.py:229-231`) says these patterns "are data about meetings held in Brazilian Portuguese".
- `domain/verification.participant_heard` (`domain/verification.py:135-164`) confirms a participant who is the owner, appears in the roster or on a labelled line, is named twice, or matches one of those patterns. Anyone else is marked unconfirmed and gets ⚠️ in the minutes.

Failure mode: in an English meeting without observer data (Windows, `[speakers] enabled = false`, an older recording or a backfill), someone greeted once with "Hi John." or "Thanks John" is not confirmed. "oi john" would be confirmed in Portuguese. So the minutes of English meetings carry more ⚠️ on participants than Portuguese ones. `Verify.SENSITIVE` is not affected, because it runs on the claim text, which stays Portuguese.

This is not a regression against today, since English transcripts are unusable now. But Impact Analysis does not list it, and nothing records it as a known gap.

Suggested fix: add an Impact Analysis row, or a Known Risks bullet, for `Verify.ADDRESS`. Either extend it with English forms (`hi|hello|hey|thanks|thank you`, accent-free and lowercase like the others, with a test in `tests/unit/test_verification*.py`), or state that it is out of scope and that English participants rely on the roster and two mentions.

## Triage

- Decision: `VALID`
- Notes: Valid. `Verify.ADDRESS` (`constants.py:244-247`) only knows Portuguese greetings, and `participant_heard` (`verification.py:135-164`) marks anyone else unconfirmed unless labelled, in the roster or named twice. Chose to extend the patterns rather than record a gap: the change is two words in one regex group, and English participants without observer data are the case this feature creates.
- Verified: `src/teams_recorder/constants.py:226-247`, `src/teams_recorder/domain/verification.py:135-164`.
- Verified (round 4, 2026-10-22): the Impact row (`_spec.md:328`), Core Features (`:37`), the MVP Boundary (`:121`), the architecture list (`:152`), Build Order task 4 (`:362`), File References (`:433`), US-004.EC-3 (`_user_stories.md:93`), UT-054 (`_tests.md:134`) and the Coverage Matrix row (`_tests.md:39`) are all present. Checked at runtime: `participant_heard("John Carter", …)`, run with the current `Verify.ADDRESS` and with the greeting group extended by `hi|hello|hey|thanks|thank you`. Each UT-054 positive (`Hi John.`, `hello John`, `Hey, John`, `Thanks John`, `thank you, John`) is false today and true with the extension. `John said so` and `I talked to John yesterday` stay false. So the test discriminates, and its assumptions about `participant_heard` hold: text normalized with punctuation kept, `,?` before the name, the name matched per token.

### Resolution

`_spec.md`: a new Impact row for `Verify.ADDRESS` and its docstring (`hi`, `hello`, `hey`, `thanks`, `thank you`), Core Features, MVP Boundary, the System Architecture list and Build Order task 4 include it, and File References add both files. `_user_stories.md`: US-004.EC-3. `_tests.md`: UT-054 in `tests/unit/test_verification.py` and a Coverage Matrix row.

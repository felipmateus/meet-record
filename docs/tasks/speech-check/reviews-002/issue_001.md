---
provider: manual
pr:
round: 2
round_created_at: 2026-10-23T15:10:53Z
status: resolved
file: docs/tasks/speech-check/_tests.md
line: 230
severity: medium
author: claude-code
provider_ref:
---

# Issue 001: G2 fails a Portuguese meeting whose fallback is still `pt`

## Review Comment

G2's pass line (`_tests.md:230`) has two parts: "every result equals its language-detection G1 result", and "No recording loses its result to `no-usable-sample` or `too-few-votes`". The second part fails meetings whose transcript language does not change. Nothing says what happens when G2 fails.

Evidence from the spec's own tables and the code:
- 2026-10-17_09-44-07 has per-window speech `5 3 0` (`_spec.md:166`), and G1 heard `pt` 2, `ja` 1. `_tests.md:231` itself says the middle window "sits near the 3.0 s line". If its real value is under 3.0 s, the filter keeps one of three planned samples. Under the planned-count rule (`_spec.md:81`, `planned=3`), one counted sample gives `too-few-votes` (`domain/language.py:87-91`: `needed = min_votes`, and `reason = TOO_FEW_VOTES if counted == 1`). The language is then the fallback, `pt`, which is the G1 result. G2 still fails by its second clause.
- 2026-10-17_09-56-47 (`0 25 2 8`, G1 `pt` 2, `ja` 1, `en` 1) keeps two windows. Unless both heard `pt`, it gives `too-few-votes` (one `pt`, plus `ja`, which is not an allowed language, so it is not counted) or `no-majority` (`pt` + `en`). G1 did not record which window gave which answer (`_spec.md:171`), so this cannot be ruled out ahead of time.

For a `pt` meeting, falling back is harmless, because the fallback is `pt` (`_dx.md:15`, `languages = pt, en`). A loss only matters when the language would change, as it would for MARTA and vans (`en`). As written, the last task can stall on a gate that measures the wrong thing, with no decision recorded for that case.

Suggested fix: make the pass condition "every transcript language equals its G1 language". Require `majority` only for the recordings whose G1 language differs from the fallback (MARTA and vans). Record the reasons of the others as evidence. Also add one line on what a G2 failure means: for example, drop the language-sample filter (MVP keeps the check) or bring it back to the user. Do not leave it implicit.


## Triage

- Decision: `VALID`
- Notes: Valid. G2's second clause failed `pt` meetings whose language stays `pt` through the fallback.
- Verified: `domain/language.py:87-91`; `_spec.md` Evidence per-window table.

### Resolution

This is the user's choice (2026-10-23), as proposed. G2 passes when every transcript language equals its language-detection G1 language. MARTA and vans must also be decided by `majority`, and the fallback reasons of the others are recorded as evidence. A language change is the failure. When it happens, the sample filter does not ship as specified and goes back to the user with the evidence, and the MVP does not depend on G2 (`_tests.md` G2).

---
provider: manual
pr:
round: 2
round_created_at: 2026-10-23T15:10:53Z
status: resolved
file: docs/tasks/speech-check/_tests.md
line: 104
severity: low
author: claude-code
provider_ref:
---

# Issue 004: UT-017's separated case fails if the 3-word separator repeats

## Review Comment

UT-017 (`_tests.md:104`) ends with "the same 12 lines each separated by a 3-word line → none flagged". If the separator is one repeated 3-word line, the natural reading of "a 3-word line", the unchanged rule for long lines flags it: 11 or 12 copies within 30 segments. I ran the rule as written (a scratch implementation on the real `_key`/`loop_flags`, outside the repo):
- with one repeated separator ("isso mesmo pessoal"): flagged `[1, 3, 5, …, 23]`, the 12 separators, so "none flagged" fails;
- with distinct separators (`f"frase distinta {k}"`): flagged `[]`, as intended.

Suggested fix: say "each separated by a different 3-word line", or assert only that none of the 12 short lines is flagged.


## Triage

- Decision: `VALID`
- Notes: Valid. A repeated 3-word separator is flagged by the long-line rule.
- Verified: The reviewer's scratch run.

### Resolution

UT-017 says each separator is a *different* 3-word line (`f"frase distinta {k}"`) and explains why.

---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_user_stories.md
line: 71
severity: low
author: claude-code
provider_ref:
---

# Issue 010: A single counted vote prints 'no majority among 1 counted samples'

## Review Comment

US-003.EC-1 (`_user_stories.md:71`) and UT-012 (`_tests.md:77`) give `no-majority` when exactly one sample counted among several, for example `[en .9, is .9, None]`. The only `no-majority` CLI form (`_dx.md:82`) then renders as `Language: pt (fallback: no majority among 1 counted samples: pt 0, en 1)`. That is ungrammatical, and it reads as a contradiction: the one counted sample was 100% `en`. On short meetings this case is common. A 60-89 s meeting has 2 samples (UT-005), so one silent sample is enough to trigger it.

Suggested fix: add a reason such as `too-few-votes` ("fallback: only 1 counted sample (en); 2 needed"), or keep the reason and add a dedicated CLI form for `counted < min_votes`. Add the form to `_dx.md`, US-005 and UT-060-UT-064.

## Triage

- Decision: `VALID`
- Notes: Valid. One counted vote among several printed "no majority among 1 counted samples".
- Verified: `_dx.md` CLI forms; UT-005/UT-012 cases.

### Resolution

New reason `too-few-votes` (`LanguageReason.TOO_FEW_VOTES`): one sample counted in a meeting with more than one. CLI form `  Language: pt (fallback: only one counted sample (en); 2 needed; 3 taken)`. Updated: Business Rules › Decision, Core Interfaces, Data Models reason list, `_dx.md` forms and reason list, US-003.EC-1, US-005.AC-6, UT-012 (now also covers a 1–1 split as `NO_MAJORITY`), new UT-062a.

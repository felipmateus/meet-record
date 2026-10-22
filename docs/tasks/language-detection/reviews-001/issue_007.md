---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 37
severity: low
author: claude-code
provider_ref:
---

# Issue 007: Spec says the curator is told the language, but nothing tells it

## Review Comment

Core Features (`_spec.md:37`) says "the analysis, the claim verification and the activities curator are told when the transcript is not in Portuguese". The Business Rule (`_spec.md:54`) limits the header line to "the analyzer's and the verifier's messages". The Impact Analysis (`_spec.md:314`) changes only `build_user_message` and `verifier_claude.user_message`. Build order task 4 (`_spec.md:349`) gives the curator only prompt wording, and no `CuratorInput` or curator-message change is listed. US-004.AC-4 (an MVP behavior) is owned only by UT-053, which checks prompt text (`_tests.md:35`).

Either the curator gets a per-meeting language marker, which then needs a component, a test and a byte-identity rule for Portuguese like UT-050, or it does not, and `_spec.md:37` overstates the design.

Suggested fix: decide and state it. The likely simplest option is an unconditional prompt rule in `prompts/curate_system.md` ("a 💬 quote keeps the transcript's words, in the language they were said"), with `_spec.md:37` reworded to "the curator's prompt keeps quotes literal".

## Triage

- Decision: `VALID`
- Notes: Valid. Only the analyzer and the verifier get the header line; the curator gets prompt wording only.
- Verified: `_spec.md` Core Features vs Business Rules and Impact Analysis.

### Resolution

Core Features reworded: the analysis and the verifier are told the language; the curator's prompt gains an unconditional rule that a quote keeps the words said, in their language. No curator component change. US-004.AC-4 stays owned by UT-053 (prompt text) and the opt-in real-call suites.

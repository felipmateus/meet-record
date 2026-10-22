---
provider: manual
pr:
round: 4
round_created_at: 2026-10-22T02:12:24Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 333
severity: low
author: claude-code
provider_ref:
---

# Issue 001: Docs-sync row misses three pages on Portuguese-only content

## Review Comment

The spec now changes the curator's output contract for every meeting. A quote keeps the words said, in the language they were said in, so an English meeting's 💬 line and status-update quote stay in English (`_spec.md:53, 327`, US-004). The docs Impact row (`_spec.md:333`) is the task-6 list. A grep for the pinned-Portuguese wording, outside the pages that row already names, finds three pages that would then be wrong:

- `docs/prd/README.md:65`: "Analysis and activities-document content (summaries, actions, progress statements, the activities document, the story drafts) is produced in Brazilian Portuguese because the meetings are in Portuguese". After this feature the premise is false (meetings can be in English), and the quotes inside that content are no longer always Portuguese.
- `docs/prd/pages/09-activities.md:14`: "Content is Brazilian Portuguese, written by the model". The 💬 quote exception is missing.
- `docs/guide/activities-and-stories.md:15`: "The document (in Brazilian Portuguese) …". The same exception is missing in the user guide.

`prompts/stories_system.md:24` ("Write all content … in Brazilian Portuguese") matched the same grep. It needs no change: the story writer asks for no literal quotes (a grep for quote/literal/💬 finds none), and Business Rules › Output language keeps story drafts in Portuguese.

Failure mode: task 6 follows the row, so the PRD's language rationale and the activities pages would ship saying all activities content is Portuguese because meetings are, right next to an `atividades.md` that holds English 💬 quotes.

This is not reviews-003 issue 002: that issue's six locations are all in the row now. These three are new findings in the same class.

Suggested fix (spec only): add the three pages to the docs row in `_spec.md:333` and to File References `_spec.md:436`. For `prd/README.md:65`: "produced in Brazilian Portuguese (meetings are mostly in Portuguese, sometimes in English); literal quotes keep the language said". For the two activities pages: name the quote exception.

## Triage

- Decision: `VALID`
- Notes: Valid. The three pages state that all activities content is Portuguese because meetings are, with no quote exception; the curator's quote rule changes that for every meeting. `prompts/stories_system.md:24` needs no change, as the issue says.
- Verified: the three lines as quoted in the issue.
- Verified (round 5, 2026-10-22): resolved. The `_spec.md:333` docs row and File References list the three pages, and task 6 changed all three in the working tree: `docs/prd/README.md:65` ("meetings are mostly in Portuguese, sometimes in English); literal quotes keep the language said"), `docs/prd/pages/09-activities.md:14` (the 💬 quote exception) and `docs/guide/activities-and-stories.md:15` ("a 💬 quote from a meeting held in English stays in English"). A grep of README, AGENTS, docs/guide, docs/prd, §10 and the prompts for the pinned-Portuguese wording finds only the historical motivation line in §10.

### Resolution

`_spec.md` docs Impact row lists `docs/prd/README.md` (line 65, with the replacement wording from the issue), `docs/prd/pages/09-activities.md` (line 14) and `docs/guide/activities-and-stories.md` (line 15), both of which name the quote exception. File References list the three pages.

---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 503
severity: low
author: claude-code
provider_ref:
---

# Issue 007: Anchor rule forbids the inserts that add sub-lines to user lines

## Review Comment

Prompt › Edits (`_spec.md:503`) says: "Anchor inserts on a section heading or on a main line carrying a meeting id; never on a 💬 line." The round-1 fix for issue 014 made lines the user wrote by hand link-free on their main line forever (Business Rules › User's hand wins; Principle 4). It also made a sub-line the *only* thing the curator may add to them: `citado na …` (US-002 EC-2), the 💬 for progress on a user line (US-005 EC-5), and the duplicate case where the user's line keeps the meeting in a `citado na` sub-line (Principle 3, US-007 AC-4).

A sub-line goes under its main line, so the natural op is `insert_after` targeting the user's main line. That line carries no meeting id, so the anchor rule forbids it. The model is left with two options, both bad. It can break the stated rule, or it can `replace` the user's whole item with itself plus the new sub-line. The second puts the user's lines inside a target and exposes them to the unchecked copy described in reviews-002/issue_003.

Suggested fix: reword the anchor rule as "anchor inserts on a section heading or on a main line (yours with a meeting id, or the user's line when adding a sub-line to it); never on a 💬 line". Add one example of a `citado na` insert on a user line to Principle 3 or the worked example.

## Triage

- Decision: `VALID`
- Notes: Valid. The anchor rule forbade the only natural op for adding a sub-line to a user line (their main line has no meeting id), pushing the model to break the rule or to `replace` the user's whole item.
- Verified (round 3): the Prompt › Edits anchor rule now allows `insert_after` on the user's own line when adding a sub-line (`citado na …`, a 💬), and Principle 3 carries the JSON example of that insert.

### Resolution

Fixed by rewording the anchor rule in Prompt Edits: anchor on a section heading or on a main line, either one of yours carrying a meeting id or the user's line when adding a sub-line (`citado na …`, a 💬); never `insert_after` on a 💬 line; a `move` anchors on a heading or the last line of the destination. Added a `citado na` insert example to Principle 3.


---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 363
severity: medium
author: claude-code
provider_ref:
---

# Issue 014: Prompt rules conflict on user lines (💤 sinking vs never move)

## Review Comment

The normative prompt content contradicts itself on what may happen to lines the user wrote:

- Principle 1 (`_spec.md:360`) and Business Rules (`:55`) say lines the user wrote are "never reworded, moved or archived ... (a sub-line may be added)". The curator changes date, owner and priority fields "on lines it wrote" only.
- Principle 4 (`_spec.md:363`) says of *every* open item: "after about three weeks without mention append ` · 💤 sem menção desde <ddd dd/mm> — ainda vale?` and sink it". That edits the main line *and* moves it.
- Principle 6/Format (`_spec.md:62`, `:359`) puts "origin plus the two latest mention links" on the main line. A user line that a meeting mentions would get links appended to its main text.

A line the user writes by hand has no meeting link (US-002 EC-2), so no meeting can ever count as "mentioning" it. Under Principle 4, every user line therefore gets 💤 and sinks after about three weeks. That breaks Principle 1, and it breaks the Q-002 target "user lines preserved 100%" (`_tests.md:167`), which the evaluation would then count as a failure of the prompt rather than of the spec.

This is within the user's decision that judgment lives in the prompt. The issue is only that the prompt's own rules conflict, so the model and the evaluation cannot both be right.

Suggested fix: state the precedence in the prompt text and in Business Rules. For example: on user lines, 💤 and new mention links go into a sub-line (`- 💤 sem menção desde …` / `- citado na [Daily 19/10][id]`) and the line is not moved. Or user lines are exempt from 💤. Add the case to the Q-002 simulated user, so the evaluation measures the rule the prompt actually states.

## Triage

- Decision: `VALID`
- Notes: Valid. Principle 4 (💤 and sink every open item) and the Format rule (links on the main line) contradict Principle 1 for user lines, and a hand-written line has no meeting link, so under Principle 4 every user line would be marked 💤 after three weeks and the Q-002 "user lines preserved 100%" target would measure the prompt's own conflict.
- Verified: Business Rules (User's hand wins, Never delete, Format), prompt Line format and Principles 1/3/4, US-001 AC-2, US-002 EC-2, US-007 AC-2, Q-002 target for user lines (no 💤, no move, no main-line link). The anchor rule now forbids the inserts that add those sub-lines; tracked as reviews-002/issue_007.

### Resolution

Fixed with the second suggested option plus the sub-line for mentions. Precedence stated in Business Rules (User's hand wins, Never delete, Format), the prompt (Line format, Principle 3 duplicates, Principle 4) and the stories: user lines are exempt from 💤 and sinking, never get main-line links, and a meeting that mentions one adds a sub-line `citado na [<reunião> <dd/mm>][<id>]`. US-001 AC-2, US-002 EC-2, US-007 AC-2, `_dx.md`. Q-002 simulated user gains a user line older than three weeks and one mentioned by a meeting, with a 100% target for no 💤/move/main-line link.


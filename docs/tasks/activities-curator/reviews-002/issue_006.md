---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/_tests.md
line: 108
severity: low
author: claude-code
provider_ref:
---

# Issue 006: UT-101 contradicts pending()'s working-day window

## Review Comment

`pending()` takes meetings "analyzed since 00:00 of `working_days_ago(today, working_days)`" (`_spec.md:379`), with `working_days = 2`. UT-026 (`_tests.md:74`) fixes `working_days_ago(date(2026,10,19), 2) → date(2026,10,15)`, i.e. Monday − 2 = Thursday. So on Monday 19/10 the window starts at Thursday 15/10 00:00 and includes Thursday's meetings.

UT-101 (`_tests.md:108`) says the opposite: "`pending()` on a Monday returns Friday's analyzed meeting … and a meeting analyzed Thursday of the previous week is excluded". For any Monday, the previous week's Thursday is exactly `working_days_ago(Monday, 2)`. Checked: 2026-10-19 is a Monday and 2026-10-15 a Thursday, and the window as written includes it (scratchpad `sim/rule_sim.py`: `Thursday 15/10 meeting in pending(): True`). One of UT-026, the `pending()` definition or UT-101 must fail.

The Business Rule ("within the last 2 working days", `_spec.md:69`) does not settle it either. It is unclear whether today counts as one of the two days, i.e. whether the window is Fri+Mon or Thu+Fri+Mon. The same ambiguity affects `not_curated(working_days=10)` and the bootstrap window of 10 working days.

Suggested fix: decide whether today is day 0 or day 1. Either make UT-101's excluded case "Wednesday of the previous week", or define the window start as `working_days_ago(today, working_days - 1)` and adjust UT-026/UT-101 to match.

## Triage

- Decision: `VALID`
- Notes: Valid. UT-026 and the `pending()` definition make the window start Thursday 00:00 for Monday; UT-101 excluded exactly that Thursday.
- Verified (round 3): "today is day 0" is stated in Business Rules › Recovery, Key Decisions, the `working_days_ago` comment, US-011 AC-3 and UT-026 (Monday − 2 = Thursday). UT-101 now includes Thursday 15/10 and excludes Wednesday 14/10, which matches. Weekend days are still ambiguous; that is tracked in reviews-003/issue_003.

### Resolution

Decided: today is day 0, so the window starts at 00:00 of `working_days_ago(today, n)`: Monday reaches back to Thursday (Thursday, Friday, Monday). The convention is written in Business Rules (Recovery), Key Decisions, Assumptions, `_dx.md`, US-011 AC-3, UT-026; UT-101 rewritten (Thursday included, Wednesday excluded) and applies to `not_curated()` and the bootstrap window.


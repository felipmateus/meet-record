---
provider: manual
pr:
round: 3
round_created_at: 2026-10-20T01:04:08Z
status: resolved
file: docs/tasks/activities-curator/_tests.md
line: 76
severity: low
author: claude-code
provider_ref:
---

# Issue 003: UT-026's weekend case contradicts "today is day 0"

## Review Comment

The round-2 fix for reviews-002/issue_006 fixed the convention as "today is day 0" (`_spec.md:69`, `:248`, `:653`). UT-026 (`_tests.md:76`) adds a weekend case: "weekend today counts back from the previous Friday". That case can be read two ways, and they give different windows:

- Saturday is day 0, Friday is day 1, Thursday is day 2. Then `working_days_ago(Saturday, 2)` is Thursday.
- "Counts back from the previous Friday" means Friday is the starting point, day 0. Then it is Wednesday.

The window matters on a weekend: the daemon queues `pending()` at every start (a Mac reboot or a `trec agent restart` on a Saturday), and `not_curated()` and the bootstrap window use the same function. Whether Wednesday's meetings are retried or listed depends on which reading the implementer picks. The test's expected value is therefore ambiguous, and no line in the spec settles it.

Suggested fix: give UT-026 concrete dates, for example `working_days_ago(date(2026,10,24), 2) → date(2026,10,22)` (Saturday is day 0, so Friday is 1 and Thursday is 2) or `→ date(2026,10,21)` if a weekend day counts as Friday. Put the same sentence in the `working_days_ago` comment.

## Triage

- Decision: `VALID`
- Notes: Confirmed: "counts back from the previous Friday" admits two windows (Wednesday or Thursday for `working_days_ago(Saturday, 2)`). Resolved with the reviewer's first reading, which is the one consistent with "today is day 0": the weekend day is day 0 and not counted, Friday is 1, Thursday is 2. `_tests.md` UT-026 now gives concrete dates (`(2026-10-24, 2)` and `(2026-10-25, 2)` both give `2026-10-22`; `(2026-10-24, 0)` gives `2026-10-24`; Monday and Wednesday cases kept) and states a weekend day never counts as Friday. The same rule and examples are in the `working_days_ago` comment in `_spec.md` and in the Recovery business rule (on a Saturday or Sunday the window starts the Thursday before 00:00). Spec-only change; no source touched.
- Verified: (round 4) UT-026 (`_tests.md:76`) now gives concrete dates and the `working_days_ago` comment (`_spec.md:245-246`) and the Recovery rule (`_spec.md:69`) state the same convention. Each example checked at runtime with a reference implementation of "today is day 0, step back over Mon-Fri": Mon 2026-10-19,2 -> Thu 2026-10-15; Wed 2026-10-21,2 -> Mon 2026-10-19; Sat 2026-10-24,2 -> Thu 2026-10-22; Sun 2026-10-25,2 -> Thu 2026-10-22; Sat 2026-10-24,0 -> Sat 2026-10-24. All match the spec.

---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_tests.md
line: 95
severity: medium
author: claude-code
provider_ref:
---

# Issue 009: STATUS_UPDATE claim omits change and quote; verifier can't check them

## Review Comment

The spec says the literal `evidence` quote is "checked by the verifier" (`_spec.md:330`). It names false progress from the analyzer as a medium risk, mitigated by "verifier + 💬-only + eval" (`_spec.md:463`). UT-052 (`_tests.md:95`) fixes the claim shape as "text = about, owner = who, at".

In the code, a claim carries only `text`, `owner`, `due` and `at` (`src/teams_recorder/domain/models.py:257-265`, `Claim`). The verifier prompt line is built from `kind.value`, `text`, `owner`, `due` and `at` (`src/teams_recorder/adapters/outbound/verifier_claude.py:104-112`). With text = `about`, the verifier sees "status_update: timesheet de outubro, owner usuário, at 00:02:55". It is never told *what* changed (done vs in_progress vs cancelled) or what quote is claimed. So it can confirm that the topic came up at that time, but it cannot catch the dangerous error, where "vou subir o timesheet" (intention) is extracted as `done`. `new_due` is also not mapped to `Claim.due`, so the `date_said` axis (`verifier_claude.py:123`) never fires for `due_changed`/`delayed`.

Suggested fix: in `_spec.md` Data Models and UT-052, define the STATUS_UPDATE claim as `text = "<change>: <about> — \"<evidence>\""`, `owner = who`, `due = new_due`, `at = at`. Name the reassignee in the text for `reassigned`. Extend `domain/verification.claims`, `_claim_verification` and `with_verifications` (`src/teams_recorder/domain/verification.py:13-91`) with a STATUS_UPDATE branch keyed by position. Add the change and quote axes to `prompts/verify_system.md`. Then make UT-052 assert that the verifier message contains the change and the quote, and Q-001 `inject/defend` covers a planted intention-as-done.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified: `Claim` carries text/owner/due/at only and the verifier line is built from those, so a STATUS_UPDATE claim of `text = about` cannot expose the change or the quote, and `new_due` never reached the `date_said` axis.
- Verified: Data Models defines the STATUS_UPDATE claim (`text = "<change>: <about> — \"<evidence>\""`, reassignee named, `owner = who`, `due = new_due`, `at`); the verifier line is built from text/owner/due/at (verifier_claude.py), so change, quote and new date now reach it; UT-052/057/058/059 and Q-001 inject/defend.

### Resolution

Fixed as suggested. Data Models now defines the claim: `text = "<change>: <about> — \"<evidence>\""` (`reassigned` names the new owner), `owner = who`, `due = new_due`, `at = at`; `domain/verification.claims`, `_claim_verification` and `with_verifications` get a STATUS_UPDATE branch keyed by position; `prompts/verify_system.md` gains the change-support and new-value axes; Impact Analysis row updated. Tests: UT-052 rewritten (asserts the mapping), UT-057, UT-058 (verifier message contains change and quote), UT-059 (intention planted as done is unconfirmed); Q-001 inject/defend now plants an intention-as-done and a wrong new date.


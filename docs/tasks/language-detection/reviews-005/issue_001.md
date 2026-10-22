---
provider: manual
pr:
round: 5
round_created_at: 2026-10-22T19:48:59Z
status: resolved
file: docs/REQUIREMENTS-AND-ARCHITECTURE.md
line: 617
severity: low
author: claude-code
provider_ref:
---

# Issue 001: §10 cites G3 evidence in a session temp dir that will vanish

## Review Comment

The G3 entry in §10 (`docs/REQUIREMENTS-AND-ARCHITECTURE.md:617`) gives its outputs as `/private/tmp/claude-501/-Users-felipemateusdecarvalho-Projetos-Pessoal-teams-recorder/a4ae1a73-cb4a-46b6-8063-9517b9014f9c/scratchpad/g3/` (`SUMMARY.md`, `b_report.md`, `a_old.json`, `a_new.json`, `old/`, `new/`). The text calls the user's sign-off of G3(b) a sign-off of "the side-by-side diff … `b_report.md` in the folder above".

That folder is one agent session's scratchpad under `/private/tmp`. macOS empties `/private/tmp` on reboot, and the path is tied to that session id. The folder exists today (checked in round 5), so nothing is lost yet. After the next reboot, §10 will point to evidence that is gone, and the G3(b) sign-off will cite a report nobody can open. §10 is the project's permanent record of gate results (AGENTS.md: "Keep `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 … in sync"). The same section already holds the G1 and G2 numbers inline, which is the durable pattern.

The outputs cannot simply be committed. `old/` and `new/` hold copies of real meetings (transcripts, analyses, an activities document), and AGENTS.md keeps meeting data out of git.

Suggested fix (docs only), pick one:
1. Move the non-sensitive summary (`SUMMARY.md`, the verdict counts and the changed claim) to a durable place outside the repo that §10 names, for example a dated folder next to the other evaluation work dirs, which AGENTS.md says live outside the repository. Say that the copies of meeting data were not kept.
2. Or drop the path from §10. State that the per-claim outputs were scratch and not retained, and that §10 is the record: it already lists the 55 claims, the noise list, the changed claim with its reasons, and the (b) differences per meeting.

Either way, the G3(b) sign-off sentence should not depend on a file that will not survive.

## Triage

- Decision: `VALID`
- Notes: Confirmed: `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 (G3 entry, line 617) pointed at a session scratchpad under `/private/tmp`, and the G3(b) sign-off sentence (line 619) cited `b_report.md` there. Root cause: the durable record depended on a non-durable folder. Fix (option 2, docs only): removed the path from line 617 and stated that the per-run outputs held copies of real meetings, are not retained, and that §10 is the record. Rewrote the sign-off sentence in line 619 so it no longer cites a file. I checked the scratch `SUMMARY.md` for anything essential that §10 lacked: only the unconfirmed-claim counts per meeting (0/10 vs 2/9, 6/19 vs 2/20) and the 2026-10-14 `meeting_type` difference (`project_review` vs `other`) were missing, so I added them in one sentence. No meeting data was copied. G1 and G2 records are unchanged. Docs-only change; no code touched, so pytest and mypy were not re-run.
- Verified: round 6 (2026-10-22). `grep -n -E "/private/tmp|/tmp/|scratchpad|b_report|SUMMARY\.md|a_old|a_new" docs/REQUIREMENTS-AND-ARCHITECTURE.md` returns nothing. Line 617 now says the per-run outputs held copies of real meetings, were not kept, and that §10 is the durable record of G3. Line 619 cites "a scratch report, not kept" and still records the sign-off: "signed off by the user on 2026-10-22, so G3 is passed: (a) with that one verdict accepted as noise, (b) signed off". The added sentence matches the scratch `SUMMARY.md` (lines 11-12: unconfirmed 0/10 vs 2/9 and 6/19 vs 2/20; `meeting_type` `project_review` vs `other`). It adds only counts and an enum value, no transcript text or names. Since round 5, only this file, the round-5 run log and this issue file changed (`find -newer reviews-005/_summary.md`). No file under `data/` or the scratch `old/`/`new/` dirs entered the tree (`data/` is gitignored, `git status` shows no new paths).

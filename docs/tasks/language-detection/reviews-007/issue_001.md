---
provider: manual
pr:
round: 7
round_created_at: 2026-10-22T20:04:27Z
status: resolved
file: docs/tasks/language-detection/_tests.md
line: 24
severity: low
author: claude-code
provider_ref:
---

# Issue 001: Coverage matrix still states the old G1 criterion for US-002.AC-2

## Review Comment

The G1 amendment of 2026-10-22 is recorded correctly in the gate itself (`_tests.md:177-178`), in `_user_stories.md:51` (US-002.AC-2), in `task_06.md:42,70` and in `docs/REQUIREMENTS-AND-ARCHITECTURE.md:584,616`. One place in the same contract file still states the pre-amendment criterion as the current behavior, with no qualifier:

- `docs/tasks/language-detection/_tests.md:24`, Coverage Matrix: `| US-002.AC-2 | 25 Portuguese meetings → \`pt\` | gate G1 (evidence, task 6) | — | — |`

The 25 meetings are the Portuguese ones recorded up to 2026-10-21 (27 minus MARTA and vans, per §10:581). That count includes both no-speech recordings, 2026-10-08_02-50-26 and 2026-10-17_10-15-32. The G1 table in `docs/REQUIREMENTS-AND-ARCHITECTURE.md:597,612` shows both came out `en`, and the amended criterion accepts that. So the matrix row, read as written, claims a result that G1 did not produce, and it contradicts the user story it traces (`_user_stories.md:51`, "every one in which someone speaks comes out `pt`"). A reader who checks traceability from the matrix gets the old criterion. That is exactly what the round is meant to rule out: "no place still stating the old criterion as current".

Two summary lines carry the same pre-amendment framing in a weaker form. Align them in the same pass:

- `docs/tasks/language-detection/task_06.md:14`, Overview: "G1: detection picks the right language for every stored meeting". The amendment note (`_tests.md:178`) says that no language is right for a recording with no speech, so "every stored meeting" is no longer the gate's scope.
- `docs/tasks/language-detection/_spec.md:353`, Testing Approach: "G1, detection on every real meeting with audio …, with no wrong language". The scope is the same, with no mention of the speech condition.

Suggested fix (docs only):

- Reword the matrix row to match US-002.AC-2, for example "25 Portuguese meetings → `pt` where someone speaks".
- Add "with speech" (or a pointer to `_tests.md` › G1) to the two summary lines.

Do not change the criterion itself, which is the user's decision.

Evidence:

- `grep -n 'G1\|25 Portuguese' docs/tasks/language-detection/*.md` lists `_tests.md:24` as the only contract line that states the G1 outcome without the speech condition.
- §10's G1 table, rows 587-614: 28 meetings; 24 `pt`, 4 `en` (MARTA, vans, and the two no-speech recordings). The 26 recordings with speech all match, and the times sum to 251.3 s. The §10 prose agrees with the table, so only the matrix row is out of line.

## Triage

- Decision: VALID
- Notes: `_tests.md:24` still read "25 Portuguese meetings → `pt`" with no speech condition, and the two no-speech recordings (2026-10-08_02-50-26, 2026-10-17_10-15-32) are among the 25 and came out `en`, which the amended G1 (`_tests.md:177-178`) accepts. `task_06.md:14` and `_spec.md:353` carried the same scope without the condition. Root cause: the 2026-10-22 G1 amendment was applied to the gate, the user story and §10, but not to these three summary lines.
- Fix (docs only, criterion unchanged): `_tests.md:24` now reads "25 Portuguese meetings → `pt`, where someone speaks (G1)"; `task_06.md:14` now says "every stored recording in which someone speaks (criterion in `_tests.md` › G1)"; `_spec.md:353` now says "with no wrong language wherever someone speaks (criterion in `_tests.md` › G1)". `_spec.md:394` and `adrs/adr-001.md:73` are left as is: they are risk-mitigation text, not pass criteria.
- Verification: docs-only change, no code touched; checked by re-reading the three lines and grepping for the old phrasing.
- Verified: round 8, 2026-10-22. The three lines now carry the speech condition: `_tests.md:24` ("25 Portuguese meetings → `pt`, where someone speaks (G1)"), `task_06.md:14` ("every stored recording in which someone speaks (criterion in `_tests.md` › G1)") and `_spec.md:353` ("with no wrong language wherever someone speaks (criterion in `_tests.md` › G1)"). All three agree with the gate (`_tests.md:177-178`), US-002.AC-2 (`_user_stories.md:51`) and §10 (`docs/REQUIREMENTS-AND-ARCHITECTURE.md:584`). A grep of the spec dir for "every other meeting", "every stored meeting", "every real meeting" and "25 Portuguese" finds no other line that states the old pass criterion as current: `_tests.md:178` and `task_06.md:42` name the change or the exclusion, and `_spec.md:394` and `adrs/adr-001.md:73` are risk-mitigation text. No code changed since round 7 (`find -newermt` lists only these three docs, this issue file and run logs). `uv run pytest -o addopts=""` gave 1317 passed, 10 skipped.

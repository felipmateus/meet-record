---
status: completed
title: "Task 6: Evaluation gates and documentation"
type: qa
complexity: medium
---

# Task 6: Evaluation gates and documentation

## Overview

This task proves the feature on real meetings and records the result:

- G1: detection picks the right language for every stored recording in which someone speaks (criterion in `_tests.md` › G1);
- G2: the MARTA meeting comes out healthy in English;
- G3: the changed system prompts leave Portuguese output unchanged.

It then brings every document that describes the pinned Portuguese language in line with the new behavior. The gates read real recordings through copies and never write under `data/`.

## Shippable Outcome

- Outcome: `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 records G1 (per-meeting result and detection time), G2 (MARTA, with the vans meeting as a known bad-audio case) and G3 (the verifier comparison with its noise list, and the analyzer and curator comparison signed off by the user). Every page in the docs Impact row describes per-meeting detection and the quote exception.
- Verify in this task: the three gates as written in `_tests.md` › Evaluation gates, and a docs review against the Impact row.
- Integration verification: none.

## Requirements

- Contracts: `_tests.md` › Evaluation gates (G1, G2, G3, their setup and pass criteria); `_spec.md` › Testing Approach; `_spec.md` › Impact Analysis (the docs row: every page and what changes in it); `_spec.md` › Technical Dependencies.
- Approvals to ask for before acting:
  - G3, because it spends the Claude Code subscription: about 3 × (4 verifier calls + 2 analyses, each with verification and a curator pass);
  - any commit;
  - `trec agent restart`, which makes the daemon load the new code.
- Data safety:
  - G1 reads `audio.m4a` and writes the clips to a temporary directory;
  - G2 and G3 run on scratch copies and scratch data dirs (`paths.data_dir`), never under `data/`;
  - G3's "old" side is a git worktree at the base commit, removed afterwards;
  - its comparison script is throwaway and not committed.
- A failed gate is reported with its evidence, not tuned away. A threshold changes only through a recorded spec or PRD note.

## Subtasks

- [x] 6.1 G1: detection on every stored meeting with audio; per-meeting result and time. Run 2026-10-22 on 28 meetings; 26 of 26 recordings with speech as expected; 2 no-speech recordings gave `en`, outside the gate by the user's amended criterion (see the G1 test below and §10).
- [x] 6.2 G2: the MARTA meeting with `-l en` through `TranscribeMeeting` on a scratch copy; the vans meeting recorded alongside it.
- [x] 6.3 G3, with the user's approval: (a) the verifier before and after on the same stored analyses; (b) the analyzer and curator before and after with `trec analyze`. Run 2026-10-22: (a) 51 of 52 stable claims kept, one changed, accepted by the user as noise; (b) signed off by the user (see §10).
- [x] 6.4 Documentation: every page in the docs Impact row, plus `AGENTS.md` (ports table, line 133).
- [x] 6.5 Record G1–G3 in §10. (G1, G2 and G3 recorded 2026-10-22 in `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10, "Language detection per meeting"; G3(a) and G3(b) recorded as accepted and signed off by the user.)

## Implementation Details

### Relevant Files

- `data/recordings/` — read only. G1 uses all meetings with `audio.m4a` (27 on 2026-10-21). G2 uses `2026-10-08_10-30-52` (MARTA) and `2026-10-14_15-00-56` (vans). G3 uses three Portuguese meetings with `analysis.json`.
- `src/teams_recorder/container.py:288-296`, `src/teams_recorder/application/use_cases/verification.py:29-60`, `src/teams_recorder/config.py:138-139` — `build_verifier`, `VerifyAnalysis` and `prompts_dir`, which G3(a) uses on each checkout.
- `src/teams_recorder/domain/health.py` — `transcript_health`, for G2's pass criterion.
- `docs/REQUIREMENTS-AND-ARCHITECTURE.md` — row 12, line 136, §10.
- `docs/prd/pages/02-transcription.md`, `docs/prd/appendix/data-layout.md`, `integrations.md`, `enum-dictionary.md`, `docs/prd/README.md:65`, `docs/prd/pages/09-activities.md:14` — PRD pages.
- `docs/guide/configuration.md`, `troubleshooting.md`, `commands.md`, `activities-and-stories.md:15` — guides.
- `README.md:7`, `AGENTS.md` (ports table, line 133).

### Related ADRs

- [ADR-001](adrs/adr-001.md) — the evidence G1 extends to every meeting.

## Deliverables

- The §10 record of G1–G3 and the updated documents.

## Tests

- [x] G1 — no meeting gets a wrong or non-allowed language; MARTA and vans give `en`. Passed 2026-10-22 under the criterion the user amended (every other recording in which someone speaks gives `pt`): 26 of 26 recordings with speech as expected, no non-allowed language. 2026-10-08_02-50-26 (10.9 s of silence) and 2026-10-17_10-15-32 (noise) gave `en`; they are outside the gate and stay recorded in §10 as known cases. Thresholds untouched; a speech check is a separate future spec.
- [x] G2 — MARTA in English is not degraded and has text in at least 95% of its minutes.
- [x] G3 — the verifier keeps every stable verdict, and the analyzer and curator outputs are signed off by the user. 2026-10-22: (a) one of 52 stable claims changed (`action:85ddf7fa`, 2026-10-14_09-31-39), accepted by the user as run-to-run noise (the new side disagrees with itself; the doubt is about the owner, not language); (b) outputs signed off by the user.

## Success Criteria

- A grep of the documents for the pinned-Portuguese wording ("pinned to pt", "-l pt" as the only call, "meetings are held in Brazilian Portuguese", "Meetings are in Brazilian Portuguese") finds no stale statement outside the historical notes in §10.
- The Open Questions (backfill of the two English meetings, short backchannels in the loop guard) are handed back to the user with the G2 numbers, not decided here.

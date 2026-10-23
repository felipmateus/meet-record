---
status: completed
title: "Task 7: Evaluation gates and documentation"
type: qa
complexity: medium
---

# Task 7: Evaluation gates and documentation

## Overview

This task measures the shipped code on the stored recordings, and it documents the feature where users and agents look:

- G1: the "no speech" verdict on every recording;
- G2: the language detection with the speech-aware samples;
- G3: the loop rule on the stored transcripts.

## Shippable Outcome

- Outcome:
  - G1, G2 and G3 pass, or a failure is reported to the user with its evidence before the task closes.
  - Their results, with the date run and the number of meetings read, are in `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10.
  - The docs listed in `_spec.md` › Impact Analysis › Docs row describe the feature.
- Verify in this task: the gate runs (read-only on copies), a full `pytest` and `mypy`, and the docs checked against `_dx.md`.
- Integration verification: none.

## Requirements

- Contracts:
  - `_tests.md` › Evaluation gates (inputs, retention, the pass rules of G1, G2 and G3);
  - `_spec.md` › Technical Dependencies › Gate inputs and audio retention;
  - `_spec.md` › Impact Analysis › Docs row.
- The gates read copies of `data/recordings/*/audio.m4a` and the stored `transcript.json` files.
  - They write only to temporary folders or the session's scratchpad, never under `data/`.
  - They make no Claude call.
- The four named recordings are mandatory: 2026-10-08_02-50-26, 2026-10-17_10-15-32, vans (2026-10-14_15-00-56) and MARTA (2026-10-08_10-30-52). If any has lost its audio, stop and report it; do not substitute another recording.
- A G2 failure means the language-sample filter is not shipped as specified. Report it with the per-window evidence and leave the decision to the user. Do not change thresholds to make a gate pass.
- Docs:
  - `docs/guide/configuration.md`, `docs/guide/commands.md`, `docs/guide/troubleshooting.md` (with the three-step recovery);
  - `docs/prd/pages/02-transcription.md`, `docs/prd/appendix/data-layout.md`;
  - `AGENTS.md` (a `SpeechDetector` row in the ports table);
  - `docs/REQUIREMENTS-AND-ARCHITECTURE.md`: the transcription requirement, the ports table, the adapter catalogue, a §10 entry with the gates, and the language-detection open questions (2) and (3) marked as handled.
- Do not run `trec agent restart`. Say in the report that the daemon loads the code only after it, with the user's approval.

## Subtasks

- [x] 7.1 G1 on every recording with audio, plus the four named ones.
- [x] 7.2 G2 with the filter and the planned-count rule.
- [x] 7.3 G3 on the stored transcripts and the vans and MARTA English transcripts.
- [x] 7.4 The docs and `AGENTS.md`.

## Implementation Details

### Relevant Files

- `docs/tasks/language-detection/_tests.md` › G1, and `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 "Language detection per meeting" — the baseline G1 and G2 results to compare with.
- `docs/tasks/speech-check/_spec.md` › Evidence (2026-10-22) — the pre-spec measurements the gates confirm.

## Deliverables

- The gate results in §10, and the updated docs.

## Tests

- [x] G1, G2, G3 — evidence recorded in §10 (not CI).

## Success Criteria

- Every gate ran on the day, on the recordings that still had audio, with the four named ones included.
- A full `pytest` and `mypy` are green.

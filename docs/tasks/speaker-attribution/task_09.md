---
status: in_progress
title: "Task 9: Installer, documentation and the manual gates"
type: docs
complexity: low
---

# Task 9: Installer, documentation and the manual gates

## Overview

Finishes the delivery for a fresh install and for the record: the installer and the README name the third permission and the helper, the PRD pages, the requirements document and AGENTS.md describe the behaviour, and the manual gates of the PRD (fidelity, coverage, owners, robustness, footprint) are run on real meetings and recorded. This task also owns the single live journey, since the helper cannot be tested automatically.

## Shippable Outcome

- Outcome: a fresh clone can follow the README to build both helpers, grant the three permissions and see labelled transcripts; the PRD's gate table has measured values.
- Verify in this task: E2E-001 (the manual gates G1–G5, with the user), `trec doctor` on the development Mac, the documentation cross-checked against `_dx.md`.
- Integration verification: none further (this is the integration owner).

## Requirements

- Installer: `scripts/install.sh` names Microphone, Screen & System Audio Recording and Accessibility (`PRIVACY_PANES` gains `Privacy_Accessibility`), explains which identity the Accessibility grant goes to (task 3) and the rebuild reminder; `scripts/build-native.sh` already builds both (task 2).
- README: the permissions section, the `trec doctor` description, the configuration table (`[speakers]`), the visible-window constraint, troubleshooting entries for the reason texts.
- `prd/pages/01-manual-recording.md`, `02-transcription.md`, `prd/README.md` §6 (speaker identification is no longer out of scope: attribution from the Teams window ships; voice identification stays out), `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 (a dated note), AGENTS.md (ports table rows for `SpeakerObserver` and `EnergyMeter`, the commands block for the second binary and the Accessibility permission rule), `config.toml` comments (task 4).
- Gates: with the user's approval, `trec agent restart`; then over the following meetings record G1 (30-line samples × 3 meetings), G2 (coverage from `trec status`), G3 (owner agreement over ten meetings), G4 (two weeks of daemon logs) and G5 (helper CPU, Teams responsiveness) in `docs/tasks/speaker-attribution/prd.md` › Success criteria; thresholds in `LabelRules` adjusted only through a recorded PRD note.
- Nothing committed without the user's approval; data under `data/` never deleted.

## Subtasks

- [x] 9.1 Installer and README.
- [x] 9.2 PRD pages, requirements §10, AGENTS.md, PRD §6.
- [ ] 9.3 With the user: restart the agent, run the gates on real meetings, record the results in the PRD.

## Implementation Details

### Relevant Files

- `scripts/install.sh:20-22,228-240` — permissions step and panes.
- `README.md:196-205,220-226,650-660` — permissions, doctor, troubleshooting.
- `prd/pages/01-manual-recording.md`, `prd/pages/02-transcription.md`, `prd/README.md` §6 — behaviour pages.
- `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 — the dated notes journal.
- `AGENTS.md` — ports table and commands.
- `docs/tasks/speaker-attribution/prd.md` › Success criteria — where the gate results go.

### Dependent Files

- Everything shipped by tasks 1–8.

### Related ADRs

- [ADR-001](adrs/adr-001.md), [ADR-002](adrs/adr-002.md) — summarised in the documentation.

## Deliverables

- The updated installer and documents; the PRD gate table filled with measured values and dates.

## Tests

- [ ] E2E-001 — the manual gates G1–G2 on real meetings (and G3–G5 over the following weeks), recorded in the PRD.

## Success Criteria

- A reader of the README alone can grant the right identity the Accessibility permission and verify it with `trec doctor`; the PRD's gate table shows whether the thresholds held.

## Completion Notes (2026-10-17)

Status stays `in_progress`: by the user's decision of 2026-10-17, subtask 9.3 and E2E-001 (the manual gates G1–G5 on real meetings) are done later. They wait for the user's real meetings and for `trec agent restart`, which needs the user's approval. Nothing was committed; no `trec` command, `launchctl`, daemon restart, permission change or `install.sh` run (not even `--dry-run`) happened, and nothing under `data/` was touched.

### Documented (9.1 and 9.2)

- `scripts/install.sh`: the permissions step names three permissions; Accessibility goes to the helper `native/teams-speakers/.build/release/teams-speakers`, added by hand with the `+` button (a background job's request creates no entry), because the daemon runs it as its own launchd job; a rebuild may require adding it again; `trec doctor` verifies. `PRIVACY_PANES` gained `Privacy_Accessibility`; the build step announces both binaries. `scripts/install.ps1` left as is (Windows has no observer; its text, "Teams audio itself needs no permission", is still true).
- `README.md`: key features, how it works, tech stack, installation, first-run checklist (three permissions, the `trec doctor` speaker line), command reference, recording in detail, a new "Speaker labels" section (how it works, the visible-window constraint, the guest-account note for testing), `[speakers] enabled` in the configuration table, privacy, data layout, architecture and ports tables, troubleshooting entries for each no-label reason and for the doctor warning, project status, further documentation.
- `prd/`: pages 01 (observer, energy, `Speakers:` line), 02 (labelling, summary reasons, notification, CLI lines), 03 (participants and owners from labels), 07 (installer steps), `README.md` (module row, permissions, title, roadmap row, §6 out of scope: attribution from the window ships on macOS, voice identification and clustering stay out), appendices (integrations, data layout, enum dictionary).
- `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10: a dated note "Speaker attribution implemented (2026-10-17)" with what shipped, the task 3 design and what is pending.
- `AGENTS.md`: the `SpeakerObserver` and `EnergyMeter` rows, the build and `--check` commands, the Accessibility rule and the rule that the daemon must be restarted, with the user's approval, for the observer and energy to take effect.
- `docs/tasks/speaker-attribution/prd.md` › Progress: tasks 1–8 done, task 9 documentation done, gates pending (the Success criteria table still reads Pending).

### Verified

- `bash -n scripts/install.sh`: exit 0. `pytest`: 732 passed, 8 skipped (unchanged baseline); `mypy`: no issues in 58 source files.
- Documentation cross-checked against `speakers_ax.py`, `energy_ffmpeg.py`, `domain/speakers.py`, `recording.py`, `processing.py`, `cli.py`, `messages.py`, `config.toml` and `scripts/build-native.sh`; nothing is described that is not implemented.

### Remaining (not done here)

- 9.3 / E2E-001: with the user's approval run `trec agent restart`, add the rebuilt helper to the Accessibility list, then record G1–G5 in the PRD's Success criteria table; the fidelity gate must also re-measure the verifier prompt (task 7).
- Follow-ups found while documenting: `scripts/uninstall.sh --all` does not remove `native/teams-speakers/.build` or the helper's launchd job (documented in `prd/pages/07-installation.md`); the open question from task 2 (does the helper need `AXEnhancedUserInterface`?) and the compact-view-only run; the task 5 gap (observer handle when the feature is switched off before `trec stop`).

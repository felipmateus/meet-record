---
status: completed
title: "Task 3: Permission identity spike"
type: infra
complexity: medium
---

# Task 3: Permission identity spike

## Overview

Settles which process identity macOS holds responsible for the helper's Accessibility permission when the daemon starts it, before anything is wired. The repository's own record says the Microphone grant for `teams-tap --mic` went to the daemon's Python, and every spike run used the terminal's grant, so the design of the observer adapter, the installer text and `trec doctor` depend on this answer.

## Shippable Outcome

- Outcome: `_spec.md` › Integration Points records the measured identity and the chosen design (plain spawn with the grant on the daemon's responsible process; the helper disclaiming responsibility at spawn so the grant attaches to its own binary; or the helper as its own launchd job), and the installer/README/doctor texts are decided accordingly.
- Verify in this task: IT-007, a manual procedure whose results (the System Settings entry that appears, `--check` output and exit code from a terminal and from the installed daemon's context) are recorded in the spec and in the task notes.
- Integration verification: none; task 4 implements the chosen design.

## Requirements

- Needs the user's explicit approval before each step that touches the installed daemon or macOS permissions (AGENTS.md); the daemon records the user's real meetings, so run the spike between meetings and restore the daemon's state afterwards.
- Procedure: build the helper (task 2); from a terminal run `--check`, then `--check --prompt`, and note the identity the prompt names and where it appears in System Settings > Privacy & Security > Accessibility; then make the installed daemon run `--check` once (for example a temporary `trec` diagnostic or a one-off `launchctl` job using the daemon's environment) and compare; if the grant does not follow the binary, try the disclaim option (a spawn attribute that makes the helper its own responsible process) and the launchd-job option, and record what each needs.
- Decide with the user which design ships, favouring the narrowest grant that works without manual steps per recording; write the decision into `_spec.md` (Integration Points, Build Order, Assumptions), into `_dx.md` (the `<identity named by the permission spike>` placeholders in the doctor lines) and into `docs/tasks/speaker-attribution/prd.md` (FR10 note).
- No product code beyond what the procedure needs; nothing committed.

## Subtasks

- [x] 3.1 Ask the user for approval and a time window; run the terminal checks and record the identity.
- [x] 3.2 Run `--check` from the daemon's context and record the result; try the alternative designs if the grant does not follow the binary.
- [x] 3.3 Record the decision and the measured facts in `_spec.md`, `_dx.md` and the PRD; list what task 4 must implement.

## Implementation Details

### Relevant Files

- `prd/appendix/integrations.md:21` — the record that the Microphone grant went to the daemon's Python.
- `docs/SPEAKER-ATTRIBUTION.md` §6 run 1 and `scripts/ax-speaker-probe.swift:100` — the spike relied on the terminal's grant.
- `src/teams_recorder/adapters/outbound/launchd.py`, `src/teams_recorder/adapters/inbound/cli.py:449-515` — how the daemon is installed and restarted, for the daemon-context check.
- `native/teams-tap/Package.swift` — the embedded-plist mechanism whose TCC effect is in question.
- `_spec.md` › Integration Points › macOS TCC — the three candidate designs.

### Dependent Files

- `src/teams_recorder/adapters/outbound/speakers_ax.py` (task 4), `scripts/install.sh`, `README.md`, `_dx.md` doctor lines (tasks 8 and 9).

### Related ADRs

- [ADR-001](adrs/adr-001.md) — risk "Permission identity".

## Deliverables

- The measured facts and the chosen design written into the spec, the DX contract and the PRD note; a short procedure the installer can repeat.

## Tests

- [x] IT-007 — the manual spike: `--check` from a terminal and from the installed daemon, the System Settings entry, the decision recorded.

## Success Criteria

- Task 4 can implement the adapter without guessing where the grant lives, and `trec doctor`'s mismatch warning names a real identity.

## Spike results so far (2026-10-17, approved by the user, no recording in progress)

- The installed daemon is the LaunchAgent `local.teams-recorder.daemon` running `.venv/bin/trec daemon`, whose interpreter is `~/.pyenv/versions/3.11.5/bin/python3.11`.
- **A — the helper spawned by the daemon's Python from a temporary LaunchAgent** (`subprocess.run([teams-speakers, "--check"])`, `ProcessType` Background, the daemon's working directory): exit 3, "Accessibility permission: missing". The terminal's grant, under which the spike and the live runs worked, does not cover the helper in the daemon's context.
- **B — the helper as its own temporary LaunchAgent** (`teams-speakers --check`): exit 3, "missing". Nothing has been granted to that identity yet.
- The helper is signed ad hoc (`Identifier=teams-speakers`, no team identifier), so macOS is expected to tie a grant to the binary's code hash: a rebuild may require granting again.
- Both temporary jobs were removed (`launchctl bootout`); the daemon was not touched.
- **Still to measure (needs the user to grant a permission):** run B with `--check --prompt`, allow the entry that appears under System Settings › Privacy & Security › Accessibility, then repeat A and B. If B reports granted and A still missing, the grant follows the helper only when it is its own responsible process, and the design is the helper as its own launchd job per recording (or a spawn that disclaims responsibility). If both report granted, a plain spawn from the daemon works. Granting the daemon's Python itself would also work but is the broadest grant and is not proposed.

## Spike result (2026-10-17, after the user granted the permission)

- The `--check --prompt` from the helper as its own LaunchAgent created no entry in the Accessibility list (a background job's request shows nothing); the user added `native/teams-speakers/.build/release/teams-speakers` by hand with the `+` button.
- Repeated: **A** (spawned by the daemon's Python) still exit 3 "missing"; **B** (the helper as its own LaunchAgent) "Accessibility permission: granted".
- Conclusion: the grant follows the helper only when the helper is its own responsible process. A plain spawn from the daemon would need the grant on the daemon's Python, the broadest option, not proposed.
- Candidate designs left for the user's choice: (1) the daemon starts the helper as its own launchd job per recording (what B measured); (2) the daemon spawns it with responsibility disclaimed, a private macOS API, not measured.
- Not measured: whether rebuilding the ad-hoc-signed helper drops the grant (expected when the code changes).
- A recording started during the second round (`current_recording.json` appeared); the checks did not interact with it, and the spike stopped there.

## Decision (2026-10-17, the user)

- Design 1: the daemon starts the helper as its own launchd job per recording (what test B measured). Recorded in `_spec.md` (Integration Points › macOS TCC, safety invariant 11, Assumptions, Build Order), `_dx.md` (the grant goes to teams-speakers, added with the `+` button), `_tests.md` (UT-070, UT-072, IT-003, IT-004) and the PRD's FR10 note.

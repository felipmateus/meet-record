# Task 9 memory

- State: `in_progress` by the user's decision (2026-10-17): 9.1 and 9.2 (installer, README, PRD pages, requirements §10 note, AGENTS.md, PRD progress) are done and uncommitted; 9.3 and E2E-001 (restart the agent, gates G1-G5 on real meetings) are pending and need the user's approval and real meetings.
- Documented facts later readers rely on: the helper's Accessibility grant is added by hand with the + button and goes to `native/teams-speakers/.build/release/teams-speakers` (own launchd job `local.teams-recorder.speakers`); a rebuild may require adding it again; a covered Teams window stops updating; the same account on two devices is one participant (test with a guest).
- Follow-ups: `scripts/uninstall.sh --all` does not remove the helper's build or job; fidelity gate must re-measure the verifier prompt; AXEnhancedUserInterface question and compact-view-only run open.
- Evidence: `bash -n scripts/install.sh` ok; `pytest` 732 passed, 8 skipped; `mypy` clean. No code changed.

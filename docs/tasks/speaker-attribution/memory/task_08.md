# Task 8 memory

- State: completed, uncommitted. CLI lines for doctor, status, transcribe and start in `adapters/inbound/cli.py`; texts in `messages.Cli` (`SPEAKERS_*`, `MEETING_SPEAKERS*`, `TRACK_SPEAKERS*`).
- Decisions: status shows no segment for `no-observer` (the user's review; amended in `_dx.md`); the doctor `[WARNING]` is reworded because `problems()` is the helper's own launchd check, not the terminal's, and replaces the `[ok ]` line; no doctor line on Windows; no `Speakers:` line in `trec start` when the observer is not wired; `trec stop` prints nothing new.
- Doctor calls `observer.problems()` once and reads the latest transcribed meeting's summary through `FsMeetingRepository` directly (no full container).
- Tests: `tests/unit/test_cli_speakers.py`, the speaker section of `tests/integration/test_cli.py` (IT-005 through `ProcessLaunchctl` of `test_speakers_observer.py`).
- Evidence: `pytest` 732 passed, 8 skipped; `mypy` clean. E2E-001 (task 9) and docs (README, AGENTS.md, PRD) remain.

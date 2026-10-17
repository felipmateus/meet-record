# Task 2 memory

- State: package, sources, plist, build script, UT-076, IT-006 done and uncommitted; `status: in_progress` because subtask 2.5 (a live call with the helper) is the user's to run; the exact command and what to look for are in the task file's Completion Notes. The event loop has never run (no Accessibility permission in the agent's shell, exit 3 verified).
- Helper contract choices later tasks rely on: `start.teams_pid` is `null` when Teams is not running at start; `window` events carry `kind` (`main`/`compact`); `speaking` and `seen` carry `window` with the same value; a lost window is preceded by `speaking: false` for its open states; the `stop` reason is always `signal`; exit 3 without the permission before any file is created (the adapter's `--check` runs first anyway); exit 4 when the output cannot be opened or written; usage errors exit 2.
- Build: `scripts/build-native.sh` now builds both packages and fails when the helper's sources contain the attribute-setting call; `native/teams-speakers/.build/` is git-ignored.
- Evidence: `pytest` 631 passed, 8 skipped; `mypy` clean; `swiftc -typecheck` exit 0.

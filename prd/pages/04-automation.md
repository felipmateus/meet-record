# Automatic recording (daemon and LaunchAgent)

> **Commands:** `trec daemon [--once]`, `trec agent install [--env K=V]… | uninstall | restart | status`
> **Module:** Automation · **Generated:** 2026-10-05

## Overview
This is the heart of the product: a background process that notices when a Teams call starts and ends, records it, and at the end chains transcription and analysis, without the user touching the keyboard. The LaunchAgent ensures it starts at login and comes back if it crashes.

## Detection
- **Signal:** every 3 s it reads `pmset -g assertions`. While in a call, Teams creates assertions that keep the Mac from sleeping (`PreventUserIdleDisplaySleep`, `PreventUserIdleSystemSleep`, `NoIdleSleepAssertion`, `NoDisplaySleepAssertion`). Lines for the `MSTeams` process carrying these assertions mean "in a call"; the Teams PID comes from the line itself.
- **Hysteresis:** recording starts after 2 consecutive positive readings (~6 s); it stops after 5 consecutive negative ones (~15 s). Failed readings are neutral.
- **Configuration:** `[detector] poll_seconds`, `start_after_positive_polls`, `stop_after_negative_polls`; `[audio] teams_process_name`.

## Interactions

### Call start
- Starts recording as in [Manual recording](./01-manual-recording.md) using the detected PID. If a manual recording is already active, the daemon adopts it instead of starting another one. Failures are logged and retried on the next cycle.

### During the call
- Checks every cycle that both recorders are still alive and logs a single warning per recorder that dies.

### Call end
- Stops the recording and launches the transcription → analysis sequence in the background, so the detector stays alert for the next call. Each step fails in isolation (`error.txt`).

### Startup and crash
- On startup: if it finds an orphaned recording (pointer + raw tracks), it finalizes it; if the pointer has no tracks, it discards it. It then resumes meetings stalled in `recorded` or `transcribed`.
- On SIGTERM/SIGINT: finishes the active call (recording → pipeline) before exiting.

### LaunchAgent
| Command | Behavior |
|---|---|
| `agent install` | Writes `~/Library/LaunchAgents/local.teams-recorder.daemon.plist` (RunAtLoad, KeepAlive, PATH with Homebrew and `~/.local/bin`, logs in `data/log/daemon.*.log`) and loads it in the user domain. `--env KEY=VALUE` adds variables to the daemon (e.g. `TREC_LLM_PROVIDER=claude-code`). If already loaded, unloads it first and waits for the removal to complete; retries loading up to 10 times because of a transient launchd error. |
| `agent uninstall` | Unloads and removes the plist. |
| `agent restart` | Restarts the daemon (after changing `config.toml` or updating the code). |
| `agent status` | Shows the plist, whether it is loaded, PID and state; exit code 1 if not loaded. |
| `daemon --once` | Diagnostics: a single detector reading and the PID found. |

## Integrations
| Integration | Use |
|---|---|
| `pmset -g assertions` | Call signal |
| `pgrep -x MSTeams` | Fallback for locating the PID |
| launchd (`launchctl bootstrap/bootout/kickstart/print`) | Daemon lifecycle |
| `osascript display notification` | Notifications |

## Relationships
- Chains [Recording](./01-manual-recording.md) → [Transcription](./02-transcription.md) → [Analysis](./03-analysis.md).
- [Operations](./05-operations.md) shows the resulting state.

## Business rules
- Validated on 2026-10-05 with three real calls; the third produced both tracks intact.
- `[TBC]` Behavior in long meetings (> 1 h) and with a headset switch mid-call has not been observed in production yet.
- Main log: `data/log/teams-recorder.log` (daily rotation, 30 days).

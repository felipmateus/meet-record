# Automatic recording (daemon and LaunchAgent)

> **Commands:** `trec daemon [--once]`, `trec agent install [--env K=V]… | uninstall | restart | status`
> **Module:** Automation · **Generated:** 2026-10-05

## Overview
This is the heart of the product: a background process that notices when a Teams call starts and ends, records it, and at the end chains transcription and analysis, without the user touching the keyboard. The LaunchAgent ensures it starts at login and comes back if it crashes.

## Detection
- **Signal:** every second it reads `pmset -g assertions`. While in a call, Teams creates assertions that keep the Mac from sleeping (`PreventUserIdleDisplaySleep`, `PreventUserIdleSystemSleep`, `NoIdleSleepAssertion`, `NoDisplaySleepAssertion`). Lines for the `MSTeams` process carrying these assertions mean "in a call"; the Teams PID comes from the line itself.
- **Hysteresis:** recording starts on the first positive reading (~1-2 s after the call starts); it stops after 5 consecutive negative ones (~5 s after hanging up). Failed readings are neutral.
- **Configuration:** `[detector] poll_seconds`, `start_after_positive_polls`, `stop_after_negative_polls`; `[audio] teams_process_name`.

### On Windows
- Teams is considered in a call while it holds the microphone open, as recorded by Windows for the privacy indicator (`ConsentStore\microphone`, `LastUsedTimeStop` = 0). Same 1 s polling and hysteresis.
- The daemon runs as a Task Scheduler task (`trec agent install`), at logon. The `planner` task of older versions is removed by `trec agent install`, `restart` and `uninstall`.
- The keep-or-discard question is a Windows message box: Yes keeps, No discards, closes after the timeout.
- `[TBC]` Not yet observed on a real Windows PC.

## Interactions

### Call start
- Starts recording as in [Manual recording](./01-manual-recording.md) using the detected PID. If a manual recording is already active, the daemon adopts it instead of starting another one. Failures are logged and retried on the next cycle.

- Then asks whether to keep the recording, in a dialog centered on the main screen: "Keep recording" (default) or "Discard". Recording does not wait for the answer. Not asked for an adopted manual recording, or when `[confirmation] enabled = false`.

### Keep-or-discard answer
- **Keep recording**, or no answer within `[confirmation] timeout_seconds` (default 30): the recording continues normally.
- **Discard** during the call: the recording stops and its files are deleted ("Recording cancelled" notification). The rest of that call is ignored; the next call is asked again.
- **Discard** after the call ended: the capture already stopped at hang-up; the meeting is deleted instead of transcribed.
- If the dialog cannot be shown, the recording is kept.

### During the call
- Checks every cycle that both recorders are still alive and logs a single warning per recorder that dies.

### Call end
- Stops the recording and launches the transcription → analysis sequence in the background (after the keep-or-discard answer, when it is still pending), so the detector stays alert for the next call. Each step fails in isolation (`error.txt`).
- When the analysis step saves `analysis.json`, the pipeline hands the meeting to the **curator worker**, a thread of the daemon that updates the [activities document](./09-activities.md) (up to four meetings per pass, oldest first). The worker never blocks recording, transcription or analysis; its failures are logged and written to the meeting's `curation_error.txt`, not `error.txt`. `[activities] enabled = false` starts no worker.

### Audio retention
- On the first tick of each day (the first tick after the daemon starts counts), the daemon schedules the audio retention in a background thread, never inline, so a call in progress is not delayed: it deletes `audio.m4a` of meetings older than `[audio] retention_days` (default 30) that already have a transcript (the same work as [`trec purge`](./05-operations.md)). The day is recorded before the work starts: a failure is logged ("audio retention failed; it runs again on the first tick of tomorrow") and not retried until tomorrow. A success logs how many files were removed. Until the 2026-10-20 removal of the planner, `trec plan --purge` at 6 pm did this.

### Startup and crash
- On startup: if it finds an orphaned recording (pointer + raw tracks), it finalizes it; if the pointer has no tracks, it discards it. It then queues the meetings analyzed in the last 2 working days that have no successful curation (the worker's queue is in memory, so a restart would otherwise lose them) and resumes meetings stalled in `recorded` or `transcribed`.
- On SIGTERM/SIGINT: finishes the active call (recording → pipeline) before exiting.

### LaunchAgent
| Command | Behavior |
|---|---|
| `agent install` | Removes the daily planner job an older version installed (`local.teams-recorder.planner`; Windows task `planner`) and says so when it was there. Writes `~/Library/LaunchAgents/local.teams-recorder.daemon.plist` (RunAtLoad, KeepAlive, PATH with Homebrew and `~/.local/bin`, logs in `data/log/daemon.*.log`) and loads it in the user domain. `--env KEY=VALUE` adds variables to the daemon (e.g. `TREC_LLM_PROVIDER=claude-code`). If already loaded, unloads it first and waits for the removal to complete; retries loading up to 10 times because of a transient launchd error. |
| `agent uninstall` | Unloads and removes the plist, and the legacy planner job when it is still there. |
| `agent restart` | Removes the legacy planner job first when it is still there (the old job would fail every weekday at 6 pm), then restarts the daemon (after changing `config.toml` or updating the code; the curator worker and the daily audio retention also start only after a restart). |
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

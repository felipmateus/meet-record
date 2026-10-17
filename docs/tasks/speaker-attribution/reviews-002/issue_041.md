---
provider: manual
pr:
round: 2
round_created_at: 2026-10-17T14:01:36Z
status: resolved
file: src/teams_recorder/adapters/inbound/daemon.py
line: 254
severity: medium
author: claude-code
provider_ref:
---

# Issue 041: A crash during the observer's startup grace leaks the helper job

## Review Comment

Safety invariant 11 (`_spec.md`) says: "`stop_capture`, `CancelRecording` and the daemon's recovery boot it out". Every one of these paths stops the observer only through a persisted handle:
- `daemon.py:254`: `_stop_leftover_observer` returns when `active.speakers_handle is None`;
- `recording.py:31-36`: `_stop_observer` is a no-op without a handle, and recovery's `stop_capture` goes through it;
- `AxSpeakerObserver.stop` (`speakers_ax.py`) needs a `CaptureHandle`. Nothing in the adapter boots out the fixed label without one.

The job exists before its handle is persisted. `StartRecording` saves the active recording without a handle (`recording.py:73`). `AxSpeakerObserver.start` then bootstraps `local.teams-recorder.speakers` and spends `Speakers.STARTUP_GRACE` (1.5 s) in `_watch` before it returns the handle that `_start_observer` persists (`recording.py:85`). The comment on line 73 expects a crash inside that grace.

Failure mode. The daemon is killed or crashes, or `trec start` is interrupted with Ctrl-C, after the `bootstrap` and before the handle is saved. The job keeps running: no `KeepAlive` is needed for that, it never exited. On the next daemon start, `recover()` finds `current_recording.json` with `speakers_handle` absent, so it does not boot the job out. The helper keeps polling Teams every 0.5 s and appends `seen`/`speaking` events to the recovered meeting's `speakers.jsonl` long after that meeting was finalized. It stops only when the next recording's `_boot` boots out the stale label (or at logout). The leaked events land past the meeting's end, and the process costs CPU and accessibility traffic to Teams for hours, which is what gate G5 (footprint) measures.

No test covers it: `tests/unit/test_daemon.py` and `tests/unit/test_speakers_ax.py` recover only recordings that carry a handle.

Suggested fix: give the adapter a handle-free way to boot out the fixed label (for example `stop_stale()`, or make `stop` accept `None` and boot out `Launchd.SPEAKERS_LABEL` and remove `<data_dir>/run/<label>.plist`). Call it from `recover()` whenever an active recording is found and the observer is wired, whatever the handle says. Add a recovery test where the active recording has no handle and the fake `launchctl` still has the job loaded. (Reviewer A covers the daemon. This is reported here because it is the launchd stale-job half of the adapter contract.)

## Triage

- Decision: `VALID`
- Notes: Valid. Root cause: the job exists from the bootstrap, one startup grace before the handle is persisted, but daemon recovery, _stop_observer and AxSpeakerObserver.stop all needed a handle.

Fix: new port method SpeakerObserver.stop_stale() (ports.py; fake in tests/fakes). AxSpeakerObserver.stop_stale boots out the fixed-label job and removes its definition; it acts only when the job definition file exists (written before the bootstrap, removed only with the job), so it costs no launchctl call otherwise, and the same _bootout path as stop. recording._stop_observer calls it when there is no handle (used by stop_capture, CancelRecording, and StartRecording's failure path, which now always stops/boots out); Daemon._stop_leftover_observer does the same and recovery with tracks goes through stop_capture.

Tests: tests/unit/test_daemon.py (recover without handle, with and without tracks, failing stale stop), tests/unit/test_recording_use_cases.py (failed start, stop_capture and cancel without handle), tests/unit/test_speakers_ax.py (stop_stale cases, an interrupted start cleaned by the next process).
- Verified: (round 3, 2026-10-17) New port method `SpeakerObserver.stop_stale()` (ports.py:77). The adapter is gated on the job definition, which is written before the bootstrap and removed only with the job (speakers_ax.py:105-127, 170-191). `recording._stop_observer` calls it when no handle exists, which covers stop_capture, CancelRecording and the failed-start path; `Daemon._stop_leftover_observer` does the same, and recovery with tracks goes through stop_capture. This matches `_spec.md` invariant 11. test_a_recovered_recording_without_an_observer_handle_still_boots_the_job_out, test_a_recovered_recording_with_tracks_and_no_observer_handle_boots_the_job_out_too, test_a_failing_stale_stop_does_not_stop_recovery, test_stop_capture_and_cancel_boot_out_a_job_whose_handle_was_never_persisted, test_a_start_interrupted_after_the_bootstrap_is_cleaned_by_stop_stale and test_stop_stale_asks_launchd_nothing_when_no_job_definition_exists all pass.

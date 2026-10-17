---
provider: manual
pr:
round: 2
round_created_at: 2026-10-17T14:01:36Z
status: resolved
file: src/teams_recorder/adapters/inbound/daemon.py
line: 97
severity: high
author: claude-code
provider_ref:
---

# Issue 003: The observer health check can block call-end detection in the daemon

## Review Comment

`Daemon.tick` calls `self._watch_capturers()` (`daemon.py:97`) before it handles the call state. That handling is what calls `_finish_call` when the call ends (`daemon.py:110-111`). `_watch_capturers` now also calls `speakers.is_running(handle)` on every tick (`daemon.py:136-144`), and nothing isolates that call.

`AxSpeakerObserver.is_running` is not a cheap pid probe like the recorders' checks. It spawns `launchctl print gui/<uid>/local.teams-recorder.speakers` through `subprocess.run` with no `timeout` (`speakers_ax.py:113-117`, `_launchctl` at `speakers_ax.py:144-145`). This creates two failure modes on the detection loop:

- If `is_running` raises (an `OSError` from the fork under resource pressure, or any parser error), the exception leaves `tick`. `run` logs it as `CYCLE_ERROR` and skips the rest of the iteration, including `_watch_disk` and the call-end check. While it keeps raising, the call never stops, so the recording runs on after the meeting and `_watch_disk` no longer warns.
- If `launchctl` stalls, the tick blocks with it, and the recording cannot be stopped by the daemon at all.

Both contradict the business rule "the observer's absence or failure never raises an error for the recording" and the reviewer brief's priority, which is that the observer must never delay a recording. Before this change, every call in `_watch_capturers` was a recorder check, with no subprocess spawned per tick.

Runtime evidence. The probe used the suite's own `_daemon` helper from `tests/unit/test_daemon.py` with a `FakeSpeakerObserver` subclass whose `is_running` raises `OSError`. The detector reports 3 ticks in call, then 6 ticks idle (`stop_after=3`):

```
tick raised: OSError launchctl: Resource temporarily unavailable   (x7: every tick once the recording is active)
active after the call ended: True | repo active: True
```

The call ended and the recording was never stopped. With the same detector states and a well-behaved observer, the existing tests stop it. No test makes `FakeSpeakerObserver.is_running` raise; UT-039 only covers a clean `False`. Severity is high: the likelihood is low, but the impact is a recording that never ends (the brief's top priority).

Suggested fix:
- Wrap the observer's check in `_watch_capturers` with a `try/except Exception` that logs once per meeting, or move the observer check after the call-state handling.
- Give every `launchctl` call in `speakers_ax._launchctl` a timeout. That part is the adapter, in reviewer B's scope; it is mentioned here because the daemon's contract depends on it.
- Add a daemon test: an observer whose `is_running` raises does not prevent `_finish_call` when the detector reports the call ended.

## Triage

- Decision: `VALID`
- Notes: Valid. Root cause: Daemon.tick ran the observer's is_running (a launchctl subprocess with no timeout) inside _watch_capturers, before call-state handling, with no isolation. Reproduced with a FakeSpeakerObserver whose is_running raises: with the isolation neutralised the new tests fail (RuntimeError from the fake).

Fix: daemon.py: the observer check moved to _watch_observer, run after _handle_state (call-state handling, extracted unchanged from tick) and wrapped in try/except Exception that logs once per meeting (Log.SPEAKERS_CHECK_FAILED) and retries next tick; recorder checks share _warn_if_dead. launchd.py gains run_launchctl(runner, *args, timeout) which turns TimeoutExpired into a failed CompletedProcess (exit 124); LaunchAgent is untouched. speakers_ax._launchctl uses it with Speakers.LAUNCHCTL_PRINT_TIMEOUT (5 s) for print and LAUNCHCTL_TIMEOUT (20 s) otherwise. A timed-out print is a failed print: _state gives 'not running', and is_running then asks the pid probe as for any failed print (kept: it is cheaper and more accurate than reporting a live helper dead).

Tests: tests/unit/test_daemon.py (a raising observer check never keeps the call from ending, logged once, observer still stopped; recorder death still reported), tests/unit/test_speakers_ax.py (every call carries a timeout; hanging print/bootout/bootstrap).
- Verified: (round 3, 2026-10-17) `Daemon.tick` now runs `_handle_state` before `_watch_observer` (daemon.py:99-101), and `_watch_observer` wraps the check in `try/except Exception`, logged once per meeting (daemon.py:143-158). Every adapter `launchctl` call goes through `launchd.run_launchctl` with a timeout (5 s for print, 20 s otherwise), and a TimeoutExpired becomes exit 124. test_a_failing_observer_check_never_keeps_a_call_from_ending passes with the reviewer's exact `OSError launchctl: Resource temporarily unavailable` scenario (logged once). So do test_a_failing_observer_check_does_not_hide_a_recorder_that_died, test_every_launchctl_call_carries_a_timeout_and_a_print_a_short_one and test_a_bootstrap_that_times_out_is_a_failed_start_not_a_hang.

---
provider: manual
pr:
round: 1
round_created_at: 2026-10-23T14:43:57Z
status: resolved
file: docs/tasks/speech-check/_dx.md
line: 24
severity: low
author: claude-code
provider_ref:
---

# Issue 007: No-speech CLI output omits the stderr warning and loses the notice

## Review Comment

Two mismatches between `_dx.md` and how `trec transcribe` logs:

1. `Log.NO_SPEECH` is a WARNING (`_spec.md:448`). In a CLI run no handler is configured (`_setup_logging` is daemon-only, `cli.py:837-844`), so Python's last-resort handler prints WARNING records to stderr. That happens between `Transcribing <id>…` and ` ok (…)`, as `_dx.md:87-91` shows for the failed check. The golden path (`_dx.md:24`) and UT-061 (`_tests.md:145-151`) show the no-speech block with no such line.
2. In a CLI run, the notification "goes to the log" (`_spec.md:74`, `_dx.md:126`, E2E-001 step 3). `LogNotifier.notify` logs at INFO (`notifier_macos.py:25-29`). With no handler configured, INFO is discarded, so it goes nowhere the user can read. The user-visible signal there is the CLI's own `WARNING:` line. This is the user's decision and is not re-litigated; the wording should just be accurate. E2E-001 step 3 can only be asserted through `caplog` at INFO level.

Suggested fix: show the stderr warning in the golden-path block and in UT-061 (or assert it through `caplog`, as UT-062 does). Reword the CLI notification as "logged at info level through `LogNotifier`; not shown in a CLI run", and have E2E-001 step 3 use `caplog.set_level(logging.INFO)`.


## Triage

- Decision: `VALID`
- Notes: Valid. In a CLI run the WARNING goes to stderr through the last-resort handler, and `LogNotifier` logs at info level, which is discarded.
- Verified: `cli.py:837-844`, `notifier_macos.py:25-29`.
- Round 2 (2026-10-23): `_dx.md:24,82,129,164`, US-002.AC-1, UT-061 (`caplog`) and E2E-001 step 3 (`caplog.set_level(logging.INFO)`) are fixed. Reopened because `_spec.md` keeps the wording the issue asked to correct: Business Rules `_spec.md:74` says that in a CLI run the notification "goes to the log, like every notification there", and Assumptions `:547` says "a log line in headless CLI runs". Reword both as in US-002.AC-1: logged at info level by `LogNotifier`, not shown in a CLI run, where the user sees the `WARNING:` line and the stderr warning.

### Resolution

`_dx.md`: the golden path and the `trec transcribe` section show the `Log.NO_SPEECH` stderr line before ` ok (…)`. The Notification section says the CLI logs at info level, unseen, and the user-visible signal is the `WARNING:` line. US-002.AC-1 says the same. UT-061 asserts the warning through `caplog`, and E2E-001 step 3 uses `caplog.set_level(logging.INFO)`.

Round 2 leftovers fixed (2026-10-23): Business Rules › Notification and Assumptions now say `LogNotifier` logs at info level, unseen in a CLI run, and the `WARNING:` line is the visible signal.

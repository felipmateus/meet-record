---
provider: manual
pr:
round: 1
round_created_at: 2026-10-23T14:43:57Z
status: resolved
file: docs/tasks/speech-check/_tests.md
line: 124
severity: medium
author: claude-code
provider_ref:
---

# Issue 003: UT-042 relies on a notifier guard that does not exist

## Review Comment

US-002.EC-2 (`_user_stories.md:58`) and UT-042 (`_tests.md:124`) require that a notifier which raises still saves the transcript and that `execute` returns it, "as for the degraded notification". No such guard exists. `TranscribeMeeting.execute` calls `self.notifier.notify(...)` for the degraded and rate-mismatch notifications with no try/except (`processing.py:94-99`), and no test drives a raising notifier: `FakeNotifier` (`tests/fakes/__init__.py:60-65`) never raises, and grep finds no raising notifier in `tests/`. Only the adapters swallow their own `OSError`/timeout (`notifier_macos.py:17-22`).

If the no-speech notification follows the pattern the spec points to (`_spec.md:303`, step 5, plain "notify"), UT-042 fails. In the daemon, an exception there after the save reaches `Pipeline.process`, which writes `error.txt` (status `failed`) for a meeting whose transcript was saved, and sends a second "step failed" notification.

Suggested fix: in Core Interfaces step 5, state that the no-speech notification is wrapped (catch `Exception`, log a warning with a new `Log` template, return the transcript). Drop the "as for the degraded notification" comparison, or extend the same guard to the existing two notifications and list that as a change.


## Triage

- Decision: `VALID`
- Notes: Valid. `processing.py:93-99` has no try/except around `notify`.
- Verified: `processing.py:93-99`, `tests/fakes/__init__.py` `FakeNotifier`.
- Verified (round 2, 2026-10-23): guard and `Log.NO_SPEECH_NOTIFY_FAILED` consistent in `_spec.md:312-313,473,510`, `_dx.md:129,171`, US-002.EC-2 and UT-042. No "as for the degraded notification" wording left. `processing.py:93-99` confirms the existing notifications are unguarded, as stated.

### Resolution

The no-speech notification is guarded: it catches `Exception` and logs `Log.NO_SPEECH_NOTIFY_FAILED` (`no-speech notification for %s failed: %s`), and `execute` returns the transcript. This is in Core Interfaces step 5, Safety Invariant 8, Monitoring, the Impact row for `messages.py`, `_dx.md` Notification and Logs, and US-002.EC-2. The existing degraded and rate-mismatch notifications stay unguarded, which is stated as out of scope. UT-042 is rewritten with a raising notifier and asserts the warning.

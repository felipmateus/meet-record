---
provider: manual
pr:
round: 2
round_created_at: 2026-10-17T14:01:36Z
status: resolved
file: src/teams_recorder/application/use_cases/processing.py
line: 90
severity: medium
author: claude-code
provider_ref:
---

# Issue 002: A labelling error outside three types discards the whisper transcript

## Review Comment

Safety invariant 7 and US-003.EC-2 say: "a labelling failure keeps the unlabelled transcript and logs". `TranscribeMeeting._label` (`processing.py:81-96`) only catches `(RepositoryError, OSError, ValueError)`. It also runs before `self.repo.save_transcript` (`processing.py:69-70`). Any other exception from loading or labelling therefore escapes `execute` while the meeting lock is held. Whisper's transcript, which can take many minutes for a long meeting, is never saved. The pipeline then records a transcription failure, and every retry fails the same way because the inputs on disk do not change.

Two inputs the readers accept today reach exception types the handler does not catch. Both were reproduced at runtime through `codec.energy_from_dict` and `label_segments`:

```
energy_from_dict({"step_seconds": 0, "tracks": {...}})          -> label_segments raises ZeroDivisionError (speakers._power_mean: start / step)
energy_from_dict({"step_seconds": 0.1, "tracks": {"tap.wav": [1e5, ...]}}) -> OverflowError (34, 'Result too large') in 10 ** (level / 10)
```

`energy_from_dict` validates the shape but not the range: it accepts any `step_seconds` and any level above the floor. A `speakers.jsonl` integer `t` too large for a float has the same effect. `_event` accepts any int, and `float(r["t"])` then raises OverflowError. These are damaged-file cases rather than the normal output of the meter and the helper. Still, the contract exists so that an advisory step can never cost the transcript, and the recording use cases in the same change all catch `Exception` for exactly this reason (`recording.py:_start_observer`, `_measure_energy`, `_title_from_window`).

UT-040 covers only a `RepositoryError` from `load_speaker_log`, so the gap is untested.

Suggested fix: catch `Exception` in `_label`, with the `# noqa: BLE001` justification the recording use cases use, keep logging `Log.SPEAKERS_LABEL_FAILED`, and return the unlabelled transcript. Optionally, also reject a non-positive `step_seconds` and non-finite or out-of-range levels in `energy_from_dict`, so the repository reports them as `RepositoryError`. Add a test where `label_segments` raises an arbitrary exception and the transcript is still saved unlabelled.

## Triage

- Decision: `VALID`
- Notes: Valid. Root cause: _label caught only (RepositoryError, OSError, ValueError) while it runs before save_transcript; energy_from_dict accepted step_seconds 0/negative and any level, so ZeroDivisionError / OverflowError escaped and the whisper transcript was lost on every retry.

Fix: processing.TranscribeMeeting._label catches Exception (logged with Log.SPEAKERS_LABEL_FAILED, transcript returned unlabelled). codec.energy_from_dict now rejects a step that is not a finite positive number and levels that are NaN, +inf, huge ints or above Speakers.MAX_LEVEL_DB (100) with ValueError, which the repository reports as RepositoryError naming energy.json; -inf and values below the floor still read as silence. codec._event/start epoch ignore non-finite times (an int too large for a float is a skipped line, not an OverflowError). domain _power_mean returns no window for a non-positive step instead of dividing by zero.

Tests: tests/unit/test_transcribe_speakers.py (any exception from label_segments keeps the transcript; damaged energy.json on disk through the real repository), tests/unit/test_speakers_codec.py (step, level and time rejections, repository error).
- Verified: (round 3, 2026-10-17) `TranscribeMeeting._label` catches `Exception` with the BLE001 justification and returns the unlabelled transcript (processing.py:81-96). `energy_from_dict` rejects a step that is not a finite positive number (0, -0.1, inf, nan, huge int, True) and levels that are NaN, +inf, huge or above 100 dB with ValueError, which the repository reports as RepositoryError. `_event` drops times no float can hold, and `_power_mean` returns None for a non-positive step. test_ut040_any_error_while_labelling_keeps_the_whisper_transcript[*], test_a_damaged_energy_file_on_disk_costs_the_labels_not_the_transcript[*], test_a_timeline_with_a_zero_step_labels_nobody_instead_of_dividing_by_zero and the codec rejection tests all pass.

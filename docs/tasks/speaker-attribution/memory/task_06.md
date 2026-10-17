# Task 6 memory

- Labelling lives in `TranscribeMeeting._label` (inside the lock, before `save_transcript`); the notice in `_notify_no_labels` (after the lock, like the other notifications).
- Notice rules: only reasons with `SpeakerReason.notifies`, only with `clock` and `notifier`; the marker is saved after the notification; a marker/notice I/O error is logged (`Log.SPEAKERS_NOTICE_FAILED`), not raised. `no-match` and notifying reasons already sent today log `Log.NO_SPEAKER_LABELS` (warning); `no-observer` is silent. `clock=None` raises no notice.
- Four existing tests in `tests/unit/test_processing_use_cases.py` compared `result is <fake transcript>`; they now compare `segments` because the saved transcript is the labelled copy (same intent: which pass was kept).
- Evidence: `pytest` 622 passed, 8 skipped; `mypy` clean.

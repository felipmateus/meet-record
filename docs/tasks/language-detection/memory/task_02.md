# task_02 memory

- Status: implemented and verified (pytest 1263 passed / 10 skipped; mypy clean; IT-004 run with TREC_REAL_WHISPER=1: 2 passed on the dev Mac).
- Files: `src/teams_recorder/adapters/outbound/language_whispercpp.py` (new), `application/ports.py`, `constants.py`, `messages.py`; tests `tests/unit/test_language_whispercpp.py`, `tests/integration/test_language_whispercpp.py`, `tests/unit/test_fake_language_detector.py` (new), `tests/fakes/__init__.py`, `tests/fixtures/fake_whisper_cli.py`, `tests/integration/test_transcriber_whispercpp.py`.
- Real whisper-cli 1.9.4 prints `main: processing 'c_en.wav' (...` then `whisper_full_with_state: auto-detected language: en (p = 0.999790)` per `-f`, to stderr, as the spec says; the path is echoed as passed.
- The adapter treats a missing clip file as unusable (None) and an unreadable WAV as `Err.CLIP_BAD_WAV` (a detection failure). Every ffmpeg/whisper call has its own `timeout` (300 s), as the transcriber does.

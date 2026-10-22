# task_05 memory

- Status: implemented and verified (pytest 1317 passed / 10 skipped; mypy clean; E2E-001 ran with real ffmpeg).
- Files: `adapters/inbound/cli.py` (`_language_line`, `_language_segment`, doctor line in `_check_transcript_health`, `transcribe` now loads `settings` once), `messages.py` (`Cli.LANGUAGE_*`, `Cli.MEETING_LANGUAGE`, `Cli.LANGUAGE_MODE_*`, `Minutes.LANGUAGE`), `application/ports.py`, `adapters/outbound/minutes_markdown.py`, `application/use_cases/processing.py` (`AnalyzeMeeting`, `RenderMinutes` pass `language=`); tests `tests/unit/test_cli_language.py` (new), `test_minutes_markdown.py`, `test_processing_use_cases.py`, `tests/integration/test_cli.py` (E2E-001/002), `tests/fakes/__init__.py` (`FakeMinutesRenderer.languages`, `FakeTranscriber.by_audio`).
- Decisions: `render(..., *, language=None)` is keyword-only. The no-majority tally lists every allowed language in order (zeros included). `too few votes` uses `LanguageRules().min_votes` for "N needed". Status marker goes last, after degraded/rate/unconfirmed markers. UT-063 asserts the warning with `caplog` (reviews-003 issue_003).
- Existing test `test_transcribe_prints_the_speakers_line_after_the_health_line` was renamed/edited: the `Language:` line now sits between `Health:` and `Speakers:` (contract change).
- Not done (task 6): `docs/guide/commands.md` row, gates.

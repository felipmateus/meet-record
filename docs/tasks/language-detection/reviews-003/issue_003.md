---
provider: manual
pr:
round: 3
round_created_at: 2026-10-22T00:30:08Z
status: resolved
file: docs/tasks/language-detection/_dx.md
line: 157
severity: low
author: claude-code
provider_ref:
---

# Issue 003: "see the log" points to a CLI log file that does not exist

## Review Comment

`_dx.md` › Logs (line 157) says the language lines go to "`data/log/daemon.log` (or the CLI's log)". `trec transcribe` prints `Language: pt (fallback: language detection failed; see the log)` (`_dx.md:88`, US-005.AC-4, UT-063). The spec relies on that log to carry whisper's output tail after a format change (`_spec.md:265, 310, 375`; US-003.EC-2).

The CLI has no log. `_setup_logging` (`src/teams_recorder/adapters/inbound/cli.py:795-802`) is called only by the `daemon` command (`cli.py:779`), and a grep of `src/` finds no other logging setup. When `trec transcribe` runs in a terminal:

- `LANGUAGE_DETECTION_FAILED` (warning) reaches only Python's last-resort handler, which prints it bare to stderr. It is written nowhere on disk. `trec transcribe` writes `Transcribing <id>… ` with `nl=False` (`cli.py:448`), so the warning lands in the middle of that line.
- `LANGUAGE_DETECTED` and `LANGUAGE_FALLBACK` (info) are dropped entirely.

Failure mode: after a whisper.cpp upgrade, the operator reruns `trec transcribe <id>`, reads "see the log" and opens `data/log/daemon.log`. That file has nothing about this run. The tail sits only in terminal scrollback, mixed into the `Transcribing…` line. The contract names a place that does not exist.

Suggested fix (spec only), pick one:
1. Make the contract true. `trec transcribe` prints the reason on its own line under `Language:` (for example `  WARNING: <exception>`, like the health warnings). The `_dx.md` Logs section then says the log lines are the daemon's only.
2. Change the wording. For a CLI run, "see the log" becomes "see the warning above" (or the message names stderr), and `_dx.md:157` drops "(or the CLI's log)".

Either way, UT-063 and IT-002 should assert where the tail appears for a CLI run.

## Triage

- Decision: `VALID`
- Notes: Valid. `_setup_logging` is called only by `daemon` (`cli.py:779`); `trec transcribe` echoes `Transcribing <id>… ` with `nl=False` (`cli.py:448`), so the warning reaches stderr through the last-resort handler mid-line and the info lines are dropped. Chose option 2 (wording): configuring CLI logging would change every use-case warning in CLI runs, the retry's included, which is out of scope.
- Verified: `src/teams_recorder/adapters/inbound/cli.py:448, 779, 795-802`.
- Round 4 verification (2026-10-22): not confirmed, set back to `pending`. The wording fix holds: `_dx.md:89, 93-99, 167`, US-003.EC-2, US-005.AC-4 and `_spec.md:310, 378` all say "see the warning above", stderr for a CLI run and `daemon.log` for the daemon only. A real CLI process does put the warning on stderr through the last-resort handler. But UT-063's new assertion (`_tests.md:142`: "Through `CliRunner` … stderr has the `LANGUAGE_DETECTION_FAILED` text") fails under this project's pytest. pytest's logging plugin attaches its capture handlers to the root logger for every test phase, so `logging.lastResort` is never used and nothing reaches `CliRunner`'s stderr. Runtime evidence: a scratch test with a typer command that echoes `nl=False`, logs a warning and echoes again, under `.venv` (pytest 9.1.1, typer 0.27.3), gave `result.stderr == ''` (the record appeared under "Captured log call"). With `-p no:logging` the same test passed: stderr held `language detection of m1 failed; …`. `pyproject.toml` does not disable the plugin. Still needed, spec only: UT-063 should assert the record with `caplog` (level WARNING, the meeting id and the exception message), keep the stdout `Language:` assertion through `CliRunner`, and drop "stderr has". If the stderr placement itself must be pinned, use a subprocess run of `trec transcribe` (the E2E harness) with the scripted detector failing. Cosmetic, same area: `Cli.TRANSCRIBING` is `"Transcribing {meeting_id}…"` with no trailing space (`messages.py:320`). The warning therefore starts right after `…`, not after `… ` as `_dx.md:93, 96` show.
- Verified (round 5, 2026-10-22): resolved. `tests/unit/test_cli_language.py::test_ut063_through_the_cli_a_failing_detector_gives_the_fallback_line_and_the_warning_it_points_to` asserts the stdout line through `CliRunner` and the WARNING record with `caplog` (meeting id, `pt`, the exception object, and its message in `getMessage()`), and it passes. Runtime probe outside pytest: the same CLI run, with no logging plugin, printed `language detection of 2026-10-21_09-30-28 failed; transcribing in pt: whisper-cli printed no language for any of the 8 samples; output tail: …` on stderr, with the `see the warning above` line on stdout and exit code 0. The pointer is true.

### Resolution

The CLI line is now `Language: pt (fallback: language detection failed; see the warning above)` in `_dx.md`, US-005.AC-4, US-003.EC-2, UT-063 and `_spec.md` Integration Points. `_dx.md` shows where the warning lands in a CLI run, and its Logs section says only the daemon writes `daemon.log`. `_spec.md` Monitoring and Observability states the same. UT-063 now asserts through `CliRunner` that stderr carries the `LANGUAGE_DETECTION_FAILED` text with the exception, plus a Coverage Matrix row for US-005.AC-4.

### Resolution (after round 4, 2026-10-21)

UT-063 now asserts the WARNING record with `caplog` (`LANGUAGE_DETECTION_FAILED`, the meeting id, the exception's message) plus the stdout `Language:` line through `CliRunner`. It states why stderr is not asserted (pytest's logging plugin captures the record) and that the real-run stderr placement is stdlib behavior. The Coverage Matrix row for US-005.AC-4 is reworded. The stray space is gone: `_dx.md` shows `Transcribing <id>…language detection …`, and `_spec.md` Monitoring and Observability says "right after `Transcribing <id>…`".

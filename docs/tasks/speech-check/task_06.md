---
status: completed
title: "Task 6: Speech in trec status and trec doctor, the installers' model, and the CLI journeys"
type: feature
complexity: low
---

# Task 6: Speech in trec status and trec doctor, the installers' model, and the CLI journeys

## Overview

The operator sees the check everywhere they look:

- `trec status` marks recordings without speech and counts them;
- `trec doctor` says whether the check can run;
- the installers download the Silero model whenever the check is on.

This task also owns the two end-to-end journeys, which go through `trec transcribe`, `trec status` and `trec analyze`.

## Shippable Outcome

- Outcome:
  - `trec status` prints `  · no speech` on such meetings, with no language marker, and a `Recordings without speech: N` line.
  - `trec doctor` prints the `speech check:` line in its four forms.
  - `scripts/config_tool.py vad_path` returns the Silero model when the check is on.
  - E2E-001 and E2E-002 pass through `CliRunner`.
- Verify in this task: the CLI unit cases, the config-tool case and both journeys.
- Integration verification: none beyond this task; the gates are task 7.

## Requirements

- Contracts:
  - `_dx.md` › CLI › `trec status` and `trec doctor`, and › Errors;
  - `_spec.md` › Impact Analysis rows for `cli.py status, doctor` and for `config.py, config.toml, scripts/config_tool.py`;
  - `_spec.md` › Assumptions (no language marker for a no-speech transcript, whatever the fallback).
- `status`:
  - the marker comes after the other markers;
  - `_language_segment` prints nothing for a no-speech transcript;
  - the count line goes after `Degraded transcripts:` and the optional rate-mismatch line, before `Unconfirmed claims:`, and only when the count is above 0.
- `doctor`: the line sits right after the retry line and before `language:`, and never changes the exit code.
- E2E-001 runs all seven steps of `_tests.md`, the recovery included. Without an id, `trec analyze` skips an `analyzed` meeting; with the id, it re-analyzes it.
- E2E-002 pins auto mode and a 70 s `meta.json` duration, and normalizes the temporary paths before comparing argv.

## Subtasks

- [x] 6.1 `trec status`: marker and count line.
- [x] 6.2 `trec doctor`: the `speech check:` line.
- [x] 6.3 `scripts/config_tool.py vad_path`.
- [x] 6.4 E2E-001 and E2E-002.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/inbound/cli.py:81-130, 197-230, 241-335` — `status`, the language line helpers, `doctor` and `_check_transcript_health`.
- `scripts/config_tool.py:25` — `vad_path`.
- `tests/integration/test_cli.py` — the E2E harness (`_recorded_at`, scripted whisper with `--log`).
- `tests/unit/test_cli_language.py`, `tests/unit/test_cli_speakers.py` — CLI unit patterns.

## Deliverables

- The status and doctor lines, the config-tool change, and the journeys.

## Tests

- [x] UT-026 — `config_tool.vad_path`.
- [x] UT-063 — `trec status` marker and count.
- [x] UT-064 — `trec doctor`, four forms.
- [x] E2E-001 — no speech through transcribe, status, analyze and the recovery.
- [x] E2E-002 — speech, the same argv as with the check off, and no marker.

## Success Criteria

- `pytest` and `mypy` are green.

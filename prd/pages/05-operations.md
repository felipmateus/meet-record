# Operations and diagnostics

> **Commands:** `trec status`, `trec doctor`, `trec purge`, `trec version`
> **Module:** Operations · **Generated:** 2026-10-05

## `trec status`
Lists the data folder, whether the API key is configured, the meetings with their derived state and next pending step, the recording in progress (if any) and the number of open actions.

| Column | Format |
|---|---|
| id | `YYYY-MM-DD_HH-MM-SS` |
| title | when provided |
| state | `recording` · `recorded` · `transcribed` · `analyzed` · `failed` |
| next | `stop` · `transcribe` · `analyze` · empty |

`[TBC]` Summing the month's estimated spend from `llm_usage.jsonl` is planned for phase 7.

## `trec doctor`
Checks, reporting `ok`/`MISSING` (missing)/`info`: ffmpeg, whisper-cli, swift, osascript, the built teams-tap, Claude Code CLI (and the current provider), whisper model, VAD model, API key (required only with the `api` provider), `.env` permission (warning if not 600) and the data folder. Exit code 0 only if everything the current provider requires is present.

## `trec purge`
Deletes `audio.m4a` from meetings older than `planner.retention_days` (30) days that already have `transcript.json`. Lists the affected ids. Transcript and analysis remain.

## `trec version`
Prints the package version.

## Relationships
Inspection and maintenance of the state produced by [Recording](./01-manual-recording.md), [Transcription](./02-transcription.md), [Analysis](./03-analysis.md) and [Automation](./04-automation.md).

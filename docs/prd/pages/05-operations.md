# Operations and diagnostics

> **Commands:** `trec status`, `trec doctor`, `trec purge`, `trec version`
> **Module:** Operations · **Generated:** 2026-10-05

## `trec status`
Lists the data folder, whether the API key is configured, the meetings with their derived state and next pending step, the meetings with a degraded transcript, a Teams track recorded at the wrong sample rate or unconfirmed claims (marked on their line and counted), the recording in progress (if any), the activities summary (`Activities: 7 yours · 3 waiting on others (last pass Mon 19/10 10:12)`, which replaced the open-actions count; `not created yet (trec activities curate --since YYYY-MM-DD)` when there is no document; see [Activities document](./09-activities.md)) and, when story destinations are configured, the stories of the last `[stories] dedup_days` days still waiting to be published.

| Column | Format |
|---|---|
| id | `YYYY-MM-DD_HH-MM-SS` |
| title | when provided |
| state | `recording` · `recorded` · `transcribed` · `analyzed` · `failed` |
| next | `stop` · `transcribe` · `analyze` · empty |

`[TBC]` Summing the month's estimated spend from `llm_usage.jsonl` is planned for phase 7.

## `trec doctor`
Checks, reporting `ok`/`MISSING` (missing)/`info`: ffmpeg, whisper-cli, swift, osascript, the built teams-tap, Claude Code CLI (and the current provider), whisper model, VAD model, the transcript-loop guard (`-mc`, the threshold and the retry), the claim verifier (`off`, or its model, provider and effort; a warning when its prompt is missing), the activities document (`[ok ] Activities document: <path> (ok, last pass <when>)`, `[WARNING]` with the number of meetings analyzed in the last 10 working days that have no successful curation, or `[info]` when the document does not exist yet; information only, it never changes the exit code), API key (required only with the `api` provider), `.env` permission (warning if not 600), free disk, the user story guide (information only), each story destination (`ready`, or `not ready` with its problems; required only when `[stories] publish = true`) and the data folder. Exit code 0 only if everything the current configuration requires is present.

## `trec purge`
Deletes `audio.m4a` from meetings older than `audio.retention_days` (30) days that already have `transcript.json` (a config that still has `[planner] retention_days` and no `[audio]` key keeps working for one release). Prints `Audio files removed: N` and lists the affected ids. Transcript and analysis remain. The daemon runs the same retention once a day ([automation](./04-automation.md)); the command is for running it on demand.

## `trec version`
Prints the package version.

## Relationships
Inspection and maintenance of the state produced by [Recording](./01-manual-recording.md), [Transcription](./02-transcription.md), [Analysis](./03-analysis.md) and [Automation](./04-automation.md).

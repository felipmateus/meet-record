# Relationships between flows and states

```
                 trec start / detector (IN_CALL ≥ 2)
   [—] ──────────────────────────────────────────▶ recording
                                                      │ trec stop / detector (IDLE ≥ 5) / daemon SIGTERM
                                                      ▼
                                                   recorded ──▶ (purge after 30 d deletes only the audio)
                                                      │ trec transcribe / pipeline
                                                      ▼
                                                  transcribed
                                                      │ trec analyze / pipeline
                                                      ▼
                                                   analyzed ──▶ trec plan (phase 6) ──▶ plans/<day>.md + open_actions.json
                                                      │ after_analysis hook (daemon) / curation step of trec analyze / trec activities curate
                                                      ▼
                                                   curator pass ──▶ activities/atividades.md (+ arquivo/, log/activities.jsonl)
                                                      └─ failure ──▶ curation_error.txt (the meeting stays analyzed)
   any step with an error ──▶ failed (error.txt) ──▶ repeating the step clears the error and moves on
   trec cancel while recording ──▶ folder removed
```

## Who triggers what
| Source | Target | Data passed |
|---|---|---|
| Detector → daemon | `StartRecording` | Teams PID |
| Daemon (call end) → pipeline | `StopRecording` → `TranscribeMeeting` → `AnalyzeMeeting` | `ActiveRecording` / meeting id |
| Daemon (startup) → pipeline | `resume_pending` | meetings in `recorded`/`transcribed` |
| `trec stop` (another process) | `StopRecording` | `current_recording.json` pointer |
| Scheduler (phase 6) | `BuildDailyPlan`, `PurgeOldAudio` | the day's date |
| Pipeline (`after_analysis`) → daemon `CuratorWorker` | `CurateMeetings` | meeting id; the worker adds the meetings still pending from the last 2 working days |
| Daemon (startup) → `CuratorWorker` | `CurateMeetings.pending()` | analyzed meetings with no successful pass |
| `trec analyze` (after its loop), `trec activities curate` | `CurateMeetings` | meeting ids, in passes of up to four |
| `trec activities undo` (CLI only, builds no curator) | `UndoLastPass` | the version the preview showed |

## Data couplings
- `open_actions.json` is read and rewritten only by the daily plan; the activities curator never reads it.
- `activities/atividades.md` is written by the curator (and by undo) under the OS lock in `activities/.curator/lock`, and by the user's editor without it; the user's edits are picked up at the next pass by diffing against `base.md`.
- `log/activities.jsonl` is appended only by passes and undo; `trec activities`, `trec status` and `trec doctor` read it (and the `recordings/<id>/curation_error.txt` files) without taking the lock.
- `llm_usage.jsonl` is only appended to by the analyses, the verifier, the plan, the story writer and the curator (`curate:<id>`, `curate-repair:<id>`); `trec status` will start reading it in phase 7.
- `config.toml` is read on every command; the daemon needs `trec agent restart` to reload it.

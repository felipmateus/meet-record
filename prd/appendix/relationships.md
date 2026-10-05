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

## Data couplings
- `open_actions.json` is read and rewritten only by the daily plan.
- `llm_usage.jsonl` is only appended to by the analyses (and by the plan, in phase 6); `trec status` will start reading it in phase 7.
- `config.toml` is read on every command; the daemon needs `trec agent restart` to reload it.

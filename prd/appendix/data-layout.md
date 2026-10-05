# Data layout and schemas

```
<data_dir>/                           # ~/Library/Application Support/teams-recorder when the project lives in iCloud or in Documents/Desktop/Downloads; otherwise <project>/data
├── current_recording.json            # pointer to the active recording (at most one)
├── recordings/<YYYY-MM-DD_HH-MM-SS>/ # one folder per meeting (see dictionary)
├── plans/                           # daily plans
│   ├── YYYY-MM-DD.md / .json         # daily plan (phase 6)
│   └── open_actions.json            # accumulated open actions
├── models/                           # ggml-*.bin (whisper, VAD)
└── log/
    ├── teams-recorder.log            # daemon (daily rotation, 30 days)
    ├── daemon.out.log / daemon.err.log
    ├── capture.log                   # recorders' stderr
    └── llm_usage.jsonl               # one line per LLM call
```

## `meta.json`
```json
{"id": "2026-10-05_12-29-37", "started_at": "2026-10-05T12:29:37", "ended_at": "2026-10-05T12:30:50", "pid": 32663, "title": null}
```

## `current_recording.json`
```json
{"meeting_id": "…", "process_handle": {"pid": 123, "out": "…/tap.wav"}, "mic_handle": {"pid": 124, "out": "…/mic.wav"}}
```

## `transcript.json`
```json
{"language": "pt", "segments": [{"start": 0.0, "end": 3.2, "text": "Bom dia, pessoal."}]}
```
`transcript.txt`: `[hh:mm:ss] text` per segment.

## `analysis.json`
```json
{
  "meeting_id": "…", "summary": "…",
  "decisions": ["…"],
  "my_actions": [{"id": "f5350aee", "description": "Enviar o relatório de integração", "owner": "usuário", "source_meeting": "…", "due": "2026-10-07", "status": "open"}],
  "others_actions": [{"id": "…", "description": "…", "owner": "Mariana", "source_meeting": "…", "due": null, "status": "open"}],
  "deadlines": [{"what": "…", "when": "2026-10-07", "who": "usuário"}],
  "open_questions": ["…"], "next_meetings": ["…"]
}
```

## `plans/YYYY-MM-DD.json` (phase 6)
```json
{"day": "2026-10-06", "markdown": "# …", "priorities": ["…"], "new_actions": [Action…], "completed_action_ids": ["…"], "overdue_action_ids": ["…"]}
```

## `llm_usage.jsonl` (one line per call)
```json
{"ts": "…", "meeting": "…", "provider": "claude-code", "model": "claude-opus-5", "input": 2, "output": 406, "cache_read": 1991, "cache_write": 692, "cost_usd_equiv": 0.054, "stop": "success", "session_id": "…"}
```
With the `api` provider: `request_id` instead of `session_id`, and no `provider`/`cost_usd_equiv`.

## Writes
All JSON files are written atomically (temporary file + rename). `*.tmp` files are ignored in listings.

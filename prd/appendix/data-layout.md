# Data layout and schemas

```
<data_dir>/                           # paths.data_dir in config.toml (relative = inside the project; currently ./data); empty = automatic (Application Support under iCloud/Documents/Desktop/Downloads, else ./data)
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
    ├── speakers.log                  # teams-speakers' stderr (macOS)
    └── llm_usage.jsonl               # one line per LLM call
```

## `meta.json`
```json
{"id": "2026-10-05_12-29-37", "started_at": "2026-10-05T12:29:37", "ended_at": "2026-10-05T12:30:50", "pid": 32663, "title": null}
```

## `tap.stats.json`
Written by `teams-tap --stats` when the Teams recorder stops (macOS only); read by the transcription step to flag a track recorded at the wrong sample rate. Kept after mixing.
```json
{"written_seconds": 709.9, "padded_seconds": 474.9, "short_padded_seconds": 474.9, "gaps": 0, "file_rate": 48000, "device_rates": [16000], "rate_changes": 0}
```

## `speakers.jsonl` (macOS)
Written by `teams-speakers` during the recording, one JSON object per line (`t` is Unix seconds; the `start` event carries the `epoch` every event is relative to): `start`, `window` (`found`/`lost`, `kind` main or compact, the window title), `title` (the meeting subject), `seen` (a participant tile, `me` marks the user's own), `speaking` (name, on/off, window) and `stop` (reason and counters). When the helper could not start, the file has exactly one line written by the recorder: `{"event": "unavailable", "reason": "binary-missing" | "permission-missing" | "start-failed"}`. Deleted with the meeting.
```json
{"t": 1760655201.104, "event": "speaking", "name": "Lucas Huguenin Gurgel de Moura", "speaking": true, "window": "main"}
```

## `energy.json`
The level of each raw track per 100 ms (dBFS, `-120.0` is digital silence), measured before the tracks are deleted; all or nothing. Used to label the user's own lines. Deleted with the meeting.
```json
{"step_seconds": 0.1, "tracks": {"tap.wav": [-120.0, -61.2, -58.9], "mic.wav": [-120.0, -70.3, -38.2]}}
```

## `current_recording.json`
```json
{"meeting_id": "…", "process_handle": {"pid": 123, "out": "…/tap.wav"}, "mic_handle": {"pid": 124, "out": "…/mic.wav"}}
```

## `transcript.json`
```json
{"language": "pt", "segments": [{"start": 0.0, "end": 3.2, "text": "Bom dia, pessoal.", "speaker": "Lucas Huguenin Gurgel de Moura"}],
 "speakers": {"roster": ["Felipe Mateus de Carvalho", "Lucas Huguenin Gurgel de Moura"], "user_label": "Felipe", "labelled": 167, "eligible": 214, "reason": null}}
```
`speaker` appears on labelled segments only; `speakers` is absent on transcripts made before the feature and present, with a `reason`, when nothing was labelled. `transcript.txt`: `[hh:mm:ss] text` per segment, `[hh:mm:ss] Name: text` for a labelled one.

## `minutes.md`
Human-readable minutes rendered from `analysis.json` (see the analysis page). Not part of the meeting status.

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

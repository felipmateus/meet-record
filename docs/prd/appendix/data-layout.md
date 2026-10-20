# Data layout and schemas

```
<data_dir>/                           # paths.data_dir in config.toml (relative = inside the project; currently ./data); empty = automatic (Application Support under iCloud/Documents/Desktop/Downloads, else ./data)
├── current_recording.json            # pointer to the active recording (at most one)
├── recordings/<YYYY-MM-DD_HH-MM-SS>/ # one folder per meeting (see dictionary); curation_error.txt when the last curator pass for it failed
├── activities/                       # the activities document and the curator's state (shadow slice)
│   ├── atividades.md                 # the document the user edits by hand
│   ├── arquivo/YYYY-MM.md            # append-only archive: what left the document, with date and reason
│   └── .curator/                     # internal: lock, base.md, versions/
├── plans/                           # daily plans
│   ├── YYYY-MM-DD.md / .json         # daily plan (phase 6)
│   └── open_actions.json            # accumulated open actions
├── models/                           # ggml-*.bin (whisper, VAD)
└── log/
    ├── teams-recorder.log            # daemon (daily rotation, 30 days)
    ├── daemon.out.log / daemon.err.log
    ├── capture.log                   # recorders' stderr
    ├── speakers.log                  # teams-speakers' stderr (macOS)
    ├── llm_usage.jsonl               # one line per LLM call
    └── activities.jsonl              # one line per curator pass (internal, diagnosis and undo)
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

## `curation_error.txt`
Plain text, one line: `Activity curation failed: <reason>` (for example `Activity curation failed: Claude Code timed out after 900 s`). Written beside `error.txt` in a meeting's folder when the last curator pass that included the meeting failed on its own; removed by a later successful pass. Not part of the meeting status. `trec activities` lists the meeting under `Not curated` with this text.

## `analysis.json`
```json
{
  "meeting_id": "…", "summary": "…",
  "decisions": ["…"],
  "my_actions": [{"id": "f5350aee", "description": "Enviar o relatório de integração", "owner": "usuário", "source_meeting": "…", "due": "2026-10-07", "status": "open"}],
  "others_actions": [{"id": "…", "description": "…", "owner": "Mariana", "source_meeting": "…", "due": null, "status": "open"}],
  "deadlines": [{"what": "…", "when": "2026-10-07", "who": "usuário"}],
  "open_questions": ["…"], "next_meetings": ["…"],
  "status_updates": [{"about": "o timesheet de outubro", "change": "done", "who": "usuário", "evidence": "o timesheet eu já subi", "at": "00:02:55", "new_due": null, "new_owner": null}]
}
```
`status_updates` (progress reported on earlier work) is absent in analyses saved before the curator and loads as empty; each action may also carry `for_whom`. Claim verification adds a `verification` to a status update like to any claim.

## `activities/atividades.md`
Markdown in Brazilian Portuguese: a box (update time and focus) between two marker comments, `## Minhas ações`, `## Aguardando outros`, `## Agenda e prazos`, `## Contexto recente`, and a generated link block between two marker comments. The box's closing marker is `<!-- curador:fim <version> -->`, where `<version>` is the stamp (`YYYYMMDD-HHMMSS`) of the pass that wrote the file. See the [activities page](../pages/09-activities.md).

## `activities/arquivo/YYYY-MM.md`
Append-only, one file per month of the pass that archived. One entry per item, newest last: a heading `### dd/mm/aaaa — <reason>`, the item's lines, and the link definitions it needs (targets one level further up: `../../recordings/<id>/minutes.md`). Undo truncates it only while it still has the size that pass left.

## `activities/.curator/`
Internal; do not edit. `lock` is the empty file the OS lock is taken on. `base.md` is the document as the last pass left it (the next pass diffs the user's edits against it). `versions/` holds, for each of the last `[activities] keep_versions` passes, `<version>_before.md`, `<version>_after.md`, `<version>_base.md`, `<version>_prevbase.md` (the last two only when the pass had a base) and `<version>_pass.json` (the pass record with the archive sizes); `undo` restores from them.

## `log/activities.jsonl`
One JSON object per pass, appended last, so the line is the commit point of a pass (a torn last line counts as absent). Kinds: `meeting`, `undo`, `skipped_empty`, `failed` (see the dictionary).
```json
{"ts": "2026-10-19T10:12:03", "kind": "meeting", "meetings": ["2026-10-19_09-30-11"], "ops_applied": 7, "retried": false, "retried_by_kind": {}, "unaccounted_refs": [], "ignored": 1, "user_removed": 0, "box_rescued": 0, "during_edits": "", "summary": "1 ação nova, 1 possível conclusão", "version": "20261019-101203", "archive_file": null, "archive_bytes_before": null, "archive_bytes_after": null, "carried_edits": "", "undoes": null, "doc_chars": 4210, "error": null}
```
`during_edits` is the diff of what the user changed in the body while the pass ran; `carried_edits` is the part of it the pass received from the previous one; `undoes` names the version an `undo` record restored; `error` holds the reason of a `failed` record.

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
All JSON files are written atomically (temporary file + rename); so are the activities document, `base.md` and the version files. `*.tmp` files are ignored in listings. The archive and the pass log are appended to.

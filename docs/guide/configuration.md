# Configuration and data

## Configuration

### `config.toml`

All settings live in `config.toml` at the project root. It holds no secrets, and every key is commented in the file. **After changing it, run `trec agent restart`** so the daemon picks the change up.

| Section | Key | Default | Meaning |
|---|---|---|---|
| `[paths]` | `data_dir` | `"data"` | Where recordings, the activities document, story drafts, models and logs live. Relative paths resolve against the project. Empty means `./data`, or `~/Library/Application Support/teams-recorder` when the project sits in a protected or iCloud folder |
| `[audio]` | `mic_device` | `"default"` | `default` follows the system input; or an exact device name |
| | `mic_backend` | `"coreaudio"` | `coreaudio` (`teams-tap --mic`) or `ffmpeg` (macOS only) |
| | `teams_process_name` / `_windows` | `"MSTeams"` / `"ms-teams.exe"` | Process the detector and the capture watch |
| | `bitrate_kbps` | `64` | AAC bitrate of `audio.m4a` |
| | `bit_depth` | `16` | Raw WAV tracks: `16` or `32` (float) |
| | `denoise` | `true` | Per-track 80 Hz high-pass and noise reduction before mixing; `false` mixes the raw tracks |
| | `retention_days` | `30` | The daemon deletes `audio.m4a` of transcribed meetings older than this once a day (`trec purge` does it on demand). Falls back to `[planner] retention_days` of an older `config.toml` for one release |
| `[detector]` | `poll_seconds` | `1` | Detector interval |
| | `start_after_positive_polls` | `1` | Readings needed to start recording |
| | `stop_after_negative_polls` | `5` | Readings without a call needed to stop |
| `[transcription]` | `whisper_model` | `"large-v3-turbo-q5_0"` | ggml model name |
| | `language` | `"auto"` | `"auto"` detects each meeting's language before transcribing it: 30-second samples spread over the audio (one per 5 minutes, 3 to 12) go through whisper's language identification, a sample counts when it heard one of `languages` with probability 0.5 or more, and the language more than half of the counted samples heard (at least 2) wins; otherwise, or if detection fails, the first of `languages`. Costs about 2 s per sample (up to about 25 s a meeting on an M1). A code (`"pt"`, `"en"`) fixes the language for every meeting and skips the detection |
| | `languages` | `["pt", "en"]` | The languages detection may choose; the first is the fallback. Checked even when `language` is a code |
| | `models_dir` | `""` | Empty means `<data_dir>/models` |
| | `threads` | `0` | `0` means automatic |
| | `speech_check` | `true` | Before transcribing, Silero VAD measures the speech in the whole recording (a conversion and one run of `whisper-vad-speech-segments`: about 25 s for an 86-minute meeting on an M1). A recording with under 2 s of speech is not sent to whisper: its transcript is saved empty and marked "no speech", a warning is logged, and a recording of 1 minute or more raises a notification. The check also feeds the language detection: a 30-second sample with under 3 s of speech in it is not sent. `false` transcribes every recording as before, for example to force one through (see [troubleshooting](troubleshooting.md)). A failing check never blocks a transcription |
| | `vad`, `vad_model` | `false`, `"silero-v5.1.2"` | Voice activity detection on every pass. `vad_model` is also the model of the speech check, so the installers download it while `speech_check` is on |
| | `max_context` | `0` | whisper `-mc`; `0` keeps a hallucination loop from carrying over, `-1` is whisper's default |
| | `max_loop_share` | `0.10` | Share of segments in repetition loops above which a transcript is degraded. A loop is 5 copies of a line within 30 segments; a line of at most 2 words ("Okay.") counts only when it also sits in a run of 3 or more such repeated short lines in a row |
| | `retry_on_loop`, `retry_vad` | `true`, `true` | Transcribe a degraded transcript once more (`-mc 0`, with VAD) |
| `[llm]` | `provider` | `"api"` | `api` or `claude-code` |
| | `model` | `"claude-opus-5-5"` | Model for the `api` provider |
| | `cli_model` | `"opus"` | Model alias for `claude-code` |
| | `effort` | `"high"` | Reasoning effort (`low` … `max`) |
| | `max_tokens` | `16000` | Output cap (API) |
| `[verification]` | `enabled` | `true` | Check each analysis's claims against the transcript (one more call per meeting) |
| | `model`, `cli_model` | `"claude-sonnet-5-5"`, `"sonnet"` | Verifier model for `api` / `claude-code` (same provider as `[llm]`) |
| | `effort` | `"medium"` | Verifier reasoning effort |
| `[speakers]` | `enabled` | `true` | Read who is speaking from the Teams window during each recording and label the transcript lines (macOS; needs `teams-speakers` and its Accessibility permission). `false` starts no helper and writes no `speakers.jsonl`; your own lines are still labelled from the microphone track |
| `[activities]` | `enabled` | `true` | Update the activities document after each analyzed meeting (the daemon's worker and the step of `trec analyze`); `false` leaves the `trec activities` commands working |
| | `model`, `cli_model` | the `[llm]` model, `"opus"` | Curator model for `api` / `claude-code` (same provider as `[llm]`) |
| | `effort` | `"medium"` | Curator reasoning effort (`low` … `max`) |
| | `notify` | `true` | Notify when a pass changed something of yours |
| | `keep_versions` | `50` | Passes kept for `trec activities undo` |
| `[user]` | `name` | `""` | Your name as said in meetings, sent to the model; also the label of your own lines when set |
| `[confirmation]` | `enabled`, `timeout_seconds` | `true`, `30` | Keep-or-discard dialog |
| `[stories]` | `guide` | `"prompts/user_story_guide.md"` | Your story-writing rules; drafting fails if it is missing or empty |
| | `destinations` | `[]` | Boards to publish to; `["backlog-md"]` or empty for drafts only |
| | `publish` | `false` | Publish today's drafts right after `trec stories` drafts them |
| | `dedup_days` | `30` | Days of earlier stories shown to the model |
| `[stories.backlog_md]` | `project_dir`, `status`, `labels` | `"."`, `"Triagem"`, `["teams-recorder"]` | Backlog.md project, intake column and labels |

### Environment variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | API key for the `api` provider. Lives in `.env` (git-ignored, permission 600); copy `.env.example` to create it |
| `TREC_LLM_PROVIDER` | Overrides `llm.provider` (`api` \| `claude-code`) |
| `TEAMS_RECORDER_DIR` | Overrides the project folder (used in tests) |
| `TREC_TEAMS_PROCESS` | Overrides the watched process name (`tests/fixtures/fake_call.py` simulates a call as `python3.11`) |
| `TREC_REAL_WHISPER`, `TREC_REAL_CLAUDE`, `TREC_REAL_CLAUDE_CLI`, `TREC_REAL_BACKLOG` | Enable the slow integration tests against the real tools |

### Prompts

| File | Used by |
|---|---|
| `prompts/analyze_system.md` | Meeting analysis, including the rules for action kinds |
| `prompts/verify_system.md` | Claim verifier (checks the analysis against the transcript) |
| `prompts/curate_system.md` | Activities curator |
| `prompts/stories_system.md` | Story drafting (your guide is appended to it) |
| `prompts/user_story_guide.md` | Your story-writing rules; edit freely |

The prompts are written in English and ask the model for Brazilian Portuguese output, whatever language the meeting was held in; a literal quote keeps the words said, in the language they were said in. When a transcript is not in Portuguese, the analyzer and the verifier are told its language.

## Data, privacy and retention

### What leaves your machine

- **Audio and transcription never leave the Mac.** whisper.cpp runs locally.
- **Only the transcript text and the prompt** are sent to Claude, through the API or your local Claude Code. With speaker labels the text includes the participants' display names (as shown in Teams) before their lines. The curator and story steps send the analyses (and, for the curator, short transcript excerpts around progress statements), not the audio.
- Stories go to a local Backlog.md board with no network access, and they are never versioned.
- Telling participants you are recording, and following company policy and LGPD (Brazil's data protection law), are your responsibility. Native Teams recording may be disabled in corporate tenants; this tool does not change that policy.

### Data layout

```
data/                                   # paths.data_dir (git-ignored)
├── current_recording.json              # pointer to the active recording (at most one)
├── recordings/<YYYY-MM-DD_HH-MM-SS>/   # one folder per meeting
│   ├── meta.json                       # id, start, end, PID, title
│   ├── tap.wav, mic.wav                # raw tracks, only until mixed
│   ├── tap.stats.json                  # teams-tap's counters for the Teams track (padding, device rates)
│   ├── speakers.jsonl                  # teams-speakers' events: who spoke when, the roster, the subject (macOS)
│   ├── energy.json                     # level of each raw track per 100 ms, kept after the tracks are deleted
│   ├── audio.m4a                       # mono AAC 48 kHz mix
│   ├── transcript.json, transcript.txt # lines carry the speaker name when known
│   ├── analysis.json, minutes.md
│   ├── error.txt                       # "step: message" after a failure
│   ├── curation_error.txt              # why the activities curator could not take this meeting (not part of its state)
│   └── debug/                          # raw copies kept on a track anomaly
├── activities/
│   ├── atividades.md                   # the activities document (edit it freely)
│   ├── arquivo/YYYY-MM.md              # append-only archive: what left the document, with date and reason
│   └── .curator/                       # internal: lock, base.md, versions of the last passes (undo)
├── plans/
│   └── YYYY-MM-DD.stories.md / .json   # story drafts and where they were published
                                        # (older plans, YYYY-MM-DD.md / .json and open_actions.json, are no longer read)
├── models/                             # ggml-*.bin
├── run/                                # teams-speakers' launchd job definition (macOS), the recorders' stop files (Windows)
├── notices/                            # the day each once-a-day notification last fired
├── tasks/                              # Task Scheduler definitions written on install (Windows)
└── log/
    ├── teams-recorder.log              # daemon (daily rotation, 30 days)
    ├── daemon.out.log, daemon.err.log
    ├── capture.log                     # recorders' stderr, padded gaps
    ├── speakers.log                    # teams-speakers' stderr (permission, windows and tiles found, counters)
    ├── llm_usage.jsonl                 # one line per model call
    └── activities.jsonl                # one line per curator pass (diagnosis, undo)
```

A meeting's state comes from its files, checked from top to bottom:

| State | Condition | Next step |
|---|---|---|
| `failed` | `error.txt` exists | Fix the cause and re-run the step |
| `analyzed` | `analysis.json` exists | None (the curator takes it into the activities document) |
| `transcribed` | `transcript.json` exists | `trec analyze` |
| `recorded` | `audio.m4a` exists | `trec transcribe` |
| `recording` | only `meta.json` (and raw tracks) | `trec stop` |

All JSON files are written atomically (temporary file, then rename), and so is the activities document. A `.lock` file stops two processes from working on the same meeting at once; one OS lock (`activities/.curator/lock`) does the same for the activities document.

### Retention

The daemon deletes `audio.m4a` from meetings older than `audio.retention_days` (30) that already have a transcript, once a day on its first tick, in the background; `trec purge` does the same on demand. Transcripts, analyses, minutes, the activities document and story drafts are kept. The daemon needs `trec agent restart` to start doing it.

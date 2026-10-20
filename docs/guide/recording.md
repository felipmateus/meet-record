# Recording and transcription

## Recording

### Manual recording

```bash
trec start --title "Daily"   # Teams must be open; or use --pid
trec status                  # shows the recording in progress
trec stop                    # mixes into data/recordings/<id>/audio.m4a
```

Only one recording runs at a time, manual or automatic. The daemon adopts a manual recording that is already running instead of starting a second one. Recordings started with `trec start` are not asked about.

### Keep or discard

When the daemon starts a recording, a dialog opens centered on the main screen, above other windows, with **Keep recording** (the default, chosen with Return) and **Discard**.

- Recording starts before the answer, so the beginning of the meeting is never lost.
- **Discard** stops the recording, deletes its files and ignores the rest of that call. The next call is asked again.
- No answer within 30 seconds keeps the recording. If the dialog cannot be shown, the recording is also kept.
- If the call ends while the dialog is open, the capture stops at hang-up and transcription waits for the answer.

Configure it under `[confirmation]`: `enabled = false` turns the question off, and `timeout_seconds` sets the wait. If Teams is in full screen, the dialog may appear on another desktop.

### Tracks, alignment and mixing

- `teams-tap --pid` captures Teams: the main process and the helper processes that actually emit audio, since Teams' main process emits none. `teams-tap --mic default` records the microphone through AVAudioEngine. It follows the system default input (so it switches to a headset) and survives the reconfiguration Teams performs when it opens the microphone. `teams-tap --list` shows the current audio clients.
- Both tracks share the meeting start as their epoch. Every buffer is placed at its Core Audio timestamp, and missing time is written as silence, so the tracks keep the real call length and stay in sync. Each gap is logged in `data/log/capture.log` as `gap of X s at Y s`.
- On macOS the daemon also starts `teams-speakers` right after the two recorders, as its own launchd job (`local.teams-recorder.speakers`, definition in `<data_dir>/run/`), and stops it with them. It never blocks a recording: when the helper is not built, lacks the Accessibility permission or fails to start, the recording goes on and one line saying why is written to `speakers.jsonl`. `trec start` prints a `Speakers:` line when it started, or why it did not. See [Speaker labels](speaker-labels.md).
- Raw tracks are 16-bit WAV (about 1 GB per hour). `audio.bit_depth = 32` records 32-bit float instead (about 2 GB per hour), with no gain for transcription.
- When the call ends, the recorders stop at once and the "recording in progress" marker is released. Before mixing, the level of each raw track per 100 ms is saved to `energy.json` (the tracks are gone afterwards); a failure is logged and mixing goes on. Mixing writes `audio.partial.m4a` and renames it only on success, with a time limit of twice the meeting length (at least 10 minutes). If mixing fails or the daemon stops first, the raw tracks stay and the next daemon start mixes them again.
- A track that is missing or under 1 KB is dropped, and the mix uses the other one. If one track is shorter than half the other, raw copies are kept in `<meeting>/debug/` for diagnosis.
- A notification warns when a recording starts with room for less than 2 hours, and again during a call if less than 1 GB is left.
- If the daemon crashes during a recording, it finalizes the orphaned recording when it starts again and resumes stalled meetings.

The ffmpeg microphone backend is still available (`audio.mic_backend = "ffmpeg"`), but it stops recording a few seconds after Teams opens the microphone.

## Transcription

```bash
trec transcribe                      # every recorded meeting not yet transcribed
trec transcribe 2026-10-06_14-00-00  # one meeting
```

The M4A is converted to 16 kHz mono WAV and passed to `whisper-cli` with the language fixed to `pt` and no text context between windows (`-mc 0`). The output is `transcript.json` (segments with start, end and text, plus the transcript's health) and `transcript.txt`. On a MacBook Air M1, long meetings transcribe at about a quarter of their length.

**Hallucination loops.** On long audio whisper can get stuck repeating one line: in an 86-minute meeting held largely in English, "A CIDADE NO BRASIL" filled 70% of the transcript and the first 59 minutes had no usable text. `-mc 0` (`transcription.max_context = 0`) stops a loop from carrying over and leaves Portuguese accuracy unchanged. After whisper, a health check measures the share of segments in repetition loops (the same text 5+ times within 30 consecutive segments) and the minutes that have speech text:

- Above `transcription.max_loop_share` (10%), the transcript is **degraded** and is transcribed once more with `-mc 0` and Silero VAD (about 30% slower). A pass that is not degraded is kept when it has at least 85% of the other's minutes of text; otherwise the one with more text, so a retry that loses more than 15% of the text, an empty one included, never replaces the first pass. A Teams track recorded at the wrong sample rate gets no retry, since VAD cannot repair it.
- If it is still degraded, it is saved anyway and the analysis runs on it. You get a "Degraded transcript" notification with the time ranges that have no text, `minutes.md` opens with a warning banner, and `trec status` marks the meeting.
- `trec transcribe` prints a health line for each meeting, and `trec doctor` shows whether the retry is on.
- If the Teams track itself was recorded at the wrong sample rate (more than 5% of it padded with short silences; it happened with a Bluetooth headset in a call before 2026-10-14), the transcript is flagged instead: a "Teams audio recorded at the wrong rate" notification, a banner in `minutes.md`, and a mark in `trec status`. `scripts/recover-rate-mismatch.sh <meeting folder>` writes an `audio.recovered.m4a` with the remote speech back at its normal speed (see the script for its limits).

Voice activity detection (Silero) is off on the first pass. In a test with short sentences it cut off speech, and the noise reduction in the mix is what improved the text. The installer downloads the VAD model for the retry; to use VAD on every pass, set `transcription.vad = true`.

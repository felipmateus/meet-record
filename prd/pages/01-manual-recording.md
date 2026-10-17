# Manual recording

> **Commands:** `trec start [--pid N] [--title T]`, `trec stop`, `trec cancel`
> **Module:** Recording · **Generated:** 2026-10-05 · **Updated:** 2026-10-17 (speaker observer and track energy)

## Overview
Lets the user record a Teams call under their own control, without relying on the automatic detector. It is also the fallback path when the detection heuristic fails. It records two separate tracks (what Teams plays and what the microphone picks up) and, on stop, combines them into a single compressed file.

## Preconditions
- Teams running (to locate the process), or an explicit `--pid`.
- Native `teams-tap` binary built (`scripts/build-native.sh`, which also builds `teams-speakers`, the optional speaker observer).
- No other recording in progress (only one at a time).

## Fields and options

| Option | Type | Required | Default | Rules | Description |
|---|---|---|---|---|---|
| `--pid` | integer | No | PID of the running `MSTeams` process | Error if neither Teams nor the PID exists | Process whose audio is captured (it and its descendants) |
| `--title` | text | No | empty | — | Title shown in status and used as context in the analysis |

## Interactions

### Start (`trec start`)
- **Trigger:** the user runs the command.
- **Behavior:** creates the meeting folder with `meta.json`; starts capturing Teams (`tap.wav`) and the microphone (`mic.wav`); then, on macOS with `[speakers] enabled = true`, starts the speaker observer (below); writes a pointer `data/current_recording.json` with the recorders' PIDs (and the observer's); notifies "Recording started". The command prints a `Speakers:` line (`speakers.jsonl` and the observer's PID, or `not running (<reason>; see trec doctor)`); with the feature off there is no line.
- **Validations:** if a recording is already active, fails with "a recording is already in progress" (a recording is already in progress); if the Teams capture fails, nothing is left behind (folder removed); if the microphone fails, the Teams capture is stopped and the folder removed.
- **Waiting for audio:** Teams creates the call assertion before initializing audio; the recorder waits up to 20 s for the process (or a descendant) to become an audio client before giving up.
- **Microphone:** follows the system default input (`mic_device = "default"`), so it tracks a switch to a headset; it survives the reconfiguration Teams performs when opening the microphone by restarting the capture without losing the file.

### Stop (`trec stop`)
- **Trigger:** the user runs the command, from any terminal (the on-disk pointer allows stopping a recording started by another process).
- **Behavior:** stops the speaker observer first (its last events are on disk when it returns), then shuts down both recorders with a clean signal; an untitled meeting takes the subject the observer read from the Teams window as its title (a `--title` wins); logs the duration and levels (dB) of each track; measures the level of each raw track per 100 ms into `energy.json`; mixes into `audio.m4a` (AAC 64 kbps, mono, 48 kHz), applying an 80 Hz high-pass filter and noise reduction per track, then loudness normalization (-18 LUFS) and a limiter at -1 dBTP on the result; deletes the raw tracks; writes `ended_at`; clears the pointer; notifies "Recording stopped" (recording ended) with the duration; suggests the transcription command.
- **Rules:** a missing track, or one smaller than 1 KB, is discarded and the mix proceeds with the other; if one track is shorter than half the duration of the other, raw copies are preserved in `<meeting>/debug/` for diagnosis.
- **Failure:** if no track is usable, error "no usable audio track to mix" (no usable audio track); the folder stays in the "recording" state for inspection.

### Cancel (`trec cancel`)
- **Trigger:** the user runs the command.
- **Behavior:** shuts down the recorders (best effort), deletes the meeting folder and the pointer; notifies "Recording cancelled". No files are kept.

## Speaker observer
On macOS the recorder also starts `teams-speakers` (`native/teams-speakers`, built by `scripts/build-native.sh`) right after the two recorders and stops it with them. It reads the Teams meeting windows (main and compact view) through the Accessibility API twice per second and writes `speakers.jsonl` in the meeting folder: who is speaking and when (a participant's tile frame shows while they speak), the names seen, the user's own tile name and the meeting subject. It is read-only on Teams.
- **Process identity:** the daemon starts it as its own launchd job (`local.teams-recorder.speakers`), because macOS judges the Accessibility permission by the process responsible for the helper: spawned by the daemon's Python it would need the Python's grant; as its own job the helper's own grant applies. The user adds `native/teams-speakers/.build/release/teams-speakers` to System Settings > Privacy & Security > Accessibility by hand (a background job's request creates no entry); a rebuild may require adding it again.
- **Never blocks a recording:** a missing binary (`binary-missing`), missing permission (`permission-missing`) or a helper that exits right after starting (`start-failed`) leaves one line `{"event":"unavailable","reason":…}` in `speakers.jsonl` and the recording goes on; a helper that dies mid-call is logged once. Starting takes about 1.5 s (a startup grace), after the active-recording pointer is saved.
- **Constraint:** a Teams window that is fully covered stops updating, so the user must keep one visible (the compact view Teams keeps on top counts). With `[speakers] enabled = false`, on Windows, or without the helper, only the user's own lines are labelled, from the track energy.
- **Testing note:** the same account on two devices is one Teams participant, so a test needs the second device to join as someone else (a guest).
- **Track energy:** before the raw tracks are deleted, the RMS level of each is saved per 100 ms in `energy.json` (all-or-nothing; a failure is logged and mixing proceeds). It labels the user's lines.

## Aligned tracks
Both recorders receive the meeting start as a shared epoch (`--epoch`). Each audio buffer is written at its Core Audio host-time position; missing time (recorder start-up, or delivery pausing during the call) is filled with silence and logged as `gap of X s at Y s`, so the Teams and microphone tracks keep the real call duration and stay in sync.

The Teams track is read at the rate the output device really runs at (16 kHz for a Bluetooth headset in a call, which can change mid-call) and resampled to 48 kHz. Until 2026-10-14 it was written at the tap's nominal 48 kHz, so with a headset in a call it came out 3x fast and chopped. When recording stops, `teams-tap` writes its counters to `tap.stats.json` (seconds written, silence padded, padding in short pads, logged gaps, device rates). The transcription step reads them to flag a track recorded at the wrong rate (see Transcription).

## Integrations
| Integration | Use | Notes |
|---|---|---|
| `teams-tap --pid` (Core Audio Process Tap) | Audio emitted by Teams | Captures the process and its audio-client descendants; WAV (16-bit by default, `--bits 32` for float), 48 kHz stereo resampled from the output device's rate; counters in `tap.stats.json` (`--stats`) |
| `teams-tap --mic` (AVAudioEngine) | Microphone | 32-bit float WAV, 48 kHz mono; alternative `ffmpeg` backend available through configuration |
| `teams-speakers` (Accessibility API) | Who is speaking, names seen, meeting subject | macOS only; own launchd job; needs the Accessibility permission; `speakers.jsonl`, helper log in `data/log/speakers.log` |
| ffmpeg | Mixing and encoding; the level of each raw track per 100 ms | See the integrations appendix for the filter chain |

## Relationships
- **To:** [Transcription](./02-transcription.md) (state becomes `recorded`).
- **With:** [Automation](./04-automation.md) — the daemon adopts a manual recording in progress instead of starting another one.

## Business rules
- A single active recording at a time, whether manual or automatic.
- Raw tracks are ephemeral; only the M4A remains (except when preserved because of an anomaly). `energy.json` and `speakers.jsonl` stay with the meeting, like the transcript, and are deleted with it.
- The observer never fails or delays a recording; the reason it did not run is recorded and shown by the transcription step.

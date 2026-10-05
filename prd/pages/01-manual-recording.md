# Manual recording

> **Commands:** `trec start [--pid N] [--title T]`, `trec stop`, `trec cancel`
> **Module:** Recording · **Generated:** 2026-10-05

## Overview
Lets the user record a Teams call under their own control, without relying on the automatic detector. It is also the fallback path when the detection heuristic fails. It records two separate tracks (what Teams plays and what the microphone picks up) and, on stop, combines them into a single compressed file.

## Preconditions
- Teams running (to locate the process), or an explicit `--pid`.
- Native `teams-tap` binary built (`scripts/build-native.sh`).
- No other recording in progress (only one at a time).

## Fields and options

| Option | Type | Required | Default | Rules | Description |
|---|---|---|---|---|---|
| `--pid` | integer | No | PID of the running `MSTeams` process | Error if neither Teams nor the PID exists | Process whose audio is captured (it and its descendants) |
| `--title` | text | No | empty | — | Title shown in status and used as context in the analysis |

## Interactions

### Start (`trec start`)
- **Trigger:** the user runs the command.
- **Behavior:** creates the meeting folder with `meta.json`; starts capturing Teams (`tap.wav`) and the microphone (`mic.wav`); writes a pointer `data/current_recording.json` with the recorders' PIDs; notifies "Recording started".
- **Validations:** if a recording is already active, fails with "a recording is already in progress" (a recording is already in progress); if the Teams capture fails, nothing is left behind (folder removed); if the microphone fails, the Teams capture is stopped and the folder removed.
- **Waiting for audio:** Teams creates the call assertion before initializing audio; the recorder waits up to 20 s for the process (or a descendant) to become an audio client before giving up.
- **Microphone:** follows the system default input (`mic_device = "default"`), so it tracks a switch to a headset; it survives the reconfiguration Teams performs when opening the microphone by restarting the capture without losing the file.

### Stop (`trec stop`)
- **Trigger:** the user runs the command, from any terminal (the on-disk pointer allows stopping a recording started by another process).
- **Behavior:** shuts down both recorders with a clean signal; logs the duration and levels (dB) of each track; mixes into `audio.m4a` (AAC 64 kbps, mono, 48 kHz), applying an 80 Hz high-pass filter and noise reduction per track, then loudness normalization (-18 LUFS) and a limiter at -1 dBTP on the result; deletes the raw tracks; writes `ended_at`; clears the pointer; notifies "Recording stopped" (recording ended) with the duration; suggests the transcription command.
- **Rules:** a missing track, or one smaller than 1 KB, is discarded and the mix proceeds with the other; if one track is shorter than half the duration of the other, raw copies are preserved in `<meeting>/debug/` for diagnosis.
- **Failure:** if no track is usable, error "no usable audio track to mix" (no usable audio track); the folder stays in the "recording" state for inspection.

### Cancel (`trec cancel`)
- **Trigger:** the user runs the command.
- **Behavior:** shuts down the recorders (best effort), deletes the meeting folder and the pointer; notifies "Recording cancelled". No files are kept.

## Integrations
| Integration | Use | Notes |
|---|---|---|
| `teams-tap --pid` (Core Audio Process Tap) | Audio emitted by Teams | Captures the process and its audio-client descendants; 32-bit float WAV, 48 kHz stereo |
| `teams-tap --mic` (AVAudioEngine) | Microphone | 32-bit float WAV, 48 kHz mono; alternative `ffmpeg` backend available through configuration |
| ffmpeg | Mixing and encoding | See the integrations appendix for the filter chain |

## Relationships
- **To:** [Transcription](./02-transcription.md) (state becomes `recorded`).
- **With:** [Automation](./04-automation.md) — the daemon adopts a manual recording in progress instead of starting another one.

## Business rules
- A single active recording at a time, whether manual or automatic.
- Raw tracks are ephemeral; only the M4A remains (except when preserved because of an anomaly).

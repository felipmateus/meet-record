# Transcription

> **Command:** `trec transcribe [id]`
> **Module:** Transcription · **Generated:** 2026-10-05

## Overview
Converts a meeting's audio into timestamped Portuguese text, entirely on the Mac. This is the step that makes the meeting searchable and feeds the analysis.

## Fields and options
| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | text | No | all meetings in state `recorded` | Specific meeting to transcribe |

## Interactions
- **Trigger:** manual command, or the automatic pipeline after `stop`.
- **Pre-processing:** the M4A is converted to 16 kHz mono WAV (the format whisper accepts) in a temporary folder.
- **Voice activity detection (optional, off by default):** with `transcription.vad = true` and the Silero model present, whisper only transcribes segments containing speech. In a test with short sentences it made the text worse, so it stays off until it is measured on long meetings.
- **Transcription:** model `large-v3-turbo-q5_0`, language fixed to `pt`, threads = half the cores by default.
- **Output:** `transcript.json` (segments with start, end and text) and `transcript.txt` (one line per segment, `[hh:mm:ss] text`). Blank segments are discarded.
- **Locking:** a `.lock` file in the folder prevents two simultaneous transcriptions of the same meeting.
- **No argument:** processes all pending meetings, reporting `ok (N segmentos, M min)` (N segments, M minutes) per meeting; failures become `error.txt` and the command exits with code 1 if any occurred. At the end it suggests `trec analyze`.
- **Clear errors:** missing model (with the command to download it), missing audio, missing whisper-cli (with the Homebrew command), timeout (3 h).

## Integrations
| Integration | Use | Notes |
|---|---|---|
| ffmpeg | Conversion to 16 kHz mono | — |
| whisper-cli (whisper.cpp 1.9.x) | Speech recognition | `-oj` JSON; optional `--vad -vm` |
| ggml models | whisper and VAD weights | `scripts/download-model.sh [name]` |

## Relationships
- **From:** [Manual recording](./01-manual-recording.md) or [Automation](./04-automation.md).
- **To:** [Analysis](./03-analysis.md) (state becomes `transcribed`).

## Business rules
- Observed performance on a MacBook Air M1: 15 s of speech in ~30 s including model load; long meetings approach 1:4.
- The transcript remains even after the audio is deleted by retention.
- Whisper hallucinations on silence ("Tchau, tchau", "Legenda por …") are handled by dropping short transcripts in the analysis and by the noise reduction in the mix. `[TBC]` The effect of VAD on long meetings has not been measured yet.

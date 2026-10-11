# Transcription

> **Command:** `trec transcribe [id]`
> **Module:** Transcription · **Generated:** 2026-10-05 · **Updated:** 2026-10-11 (hallucination-loop guard)

## Overview
Converts a meeting's audio into timestamped Portuguese text, entirely on the Mac. This is the step that makes the meeting searchable and feeds the analysis.

## Fields and options
| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | text | No | all meetings in state `recorded` | Specific meeting to transcribe |

| `[transcription]` key | Default | Description |
|---|---|---|
| `max_context` | `0` | whisper `-mc`: text of the previous window kept as context. `0` = none, so a hallucinated line cannot carry over; `-1` = whisper's default |
| `max_loop_share` | `0.10` | Above this share of segments in repetition loops the transcript is degraded |
| `retry_on_loop` | `true` | Transcribe a degraded transcript once more with the anti-loop settings |
| `retry_vad` | `true` | Use Silero VAD on that retry (needs `vad_model`, downloaded by the installer) |

## Interactions
- **Trigger:** manual command, or the automatic pipeline after `stop`.
- **Pre-processing:** the M4A is converted to 16 kHz mono WAV (the format whisper accepts) in a temporary folder.
- **Voice activity detection (optional, off by default):** with `transcription.vad = true` and the Silero model present, whisper only transcribes segments containing speech. In a test with short sentences it made the text worse, so it stays off until it is measured on long meetings.
- **Transcription:** model `large-v3-turbo-q5_0`, language fixed to `pt`, threads = half the cores by default, no text context between windows (`-mc 0`).
- **Health check:** after whisper, the transcript's health is computed: the share of segments inside repetition loops (the same text, ignoring case and punctuation, 5 or more times within 30 consecutive segments; a phrase written twice in one segment counts as the phrase) and the minutes that have speech text outside the loops. Whisper's non-speech markers (`[BLANK_AUDIO]`, `(música)`, `♪`) are not text, and minutes after the last segment count as uncovered when the meeting's length is known. Above `max_loop_share` the transcript is **degraded**.
- **Retry:** a degraded transcript is transcribed once more with `-mc 0` and Silero VAD (about 30% slower), and the healthier result is kept: more minutes with text first, then not degraded, then fewer loops, so a retry that comes back empty or cut short never replaces a first pass with text. The retry is skipped when it would only repeat the first pass (VAD already on, `retry_vad = false` with `max_context = 0`, or the VAD model missing); a retry that fails for any reason keeps the first pass.
- **Still degraded:** the transcript is saved anyway with its health marked degraded, the analysis runs on it, a notification ("Degraded transcript") names the time ranges without text, and `minutes.md` opens with a warning banner listing them.
- **Output:** `transcript.json` (segments with start, end and text, plus `health`: loop share, minutes with text, uncovered minute ranges, degraded, retried) and `transcript.txt` (one line per segment, `[hh:mm:ss] text`). Blank segments are discarded. Transcripts made before 2026-10-11 have no health.
- **Locking:** a `.lock` file in the folder prevents two simultaneous transcriptions of the same meeting.
- **No argument:** processes all pending meetings, reporting `ok (N segments, M min)` per meeting and a health line (`Health: X% of segments in repetition loops, text in N of M min`, plus a warning with the ranges without text when degraded); failures become `error.txt` and the command exits with code 1 if any occurred. A degraded transcript is not a failure. At the end it suggests `trec analyze`.
- **Status and doctor:** `trec status` marks each meeting with a degraded transcript and counts them; `trec doctor` shows `max_context`, the threshold and whether the retry is on (with VAD, without it, or off and why).
- **Clear errors:** missing model (with the command to download it), missing audio, missing whisper-cli (with the Homebrew command), timeout (3 h).

## Integrations
| Integration | Use | Notes |
|---|---|---|
| ffmpeg | Conversion to 16 kHz mono | — |
| whisper-cli (whisper.cpp 1.9.x) | Speech recognition | `-oj` JSON; `-mc`; optional `--vad -vm` (always on the retry when the VAD model exists) |
| ggml models | whisper and VAD weights | `scripts/download-model.sh [name]` |

## Relationships
- **From:** [Manual recording](./01-manual-recording.md) or [Automation](./04-automation.md).
- **To:** [Analysis](./03-analysis.md) (state becomes `transcribed`).

## Business rules
- Observed performance on a MacBook Air M1: 15 s of speech in ~30 s including model load; long meetings approach 1:4.
- The transcript remains even after the audio is deleted by retention.
- Whisper hallucinations on silence ("Tchau, tchau", "Legenda por …") are handled by dropping short transcripts in the analysis and by the noise reduction in the mix.
- **Hallucination loops (2026-10-08 incident):** an 86-minute client meeting held largely in English, transcribed as `pt` with whisper's default text context, came out with "A CIDADE NO BRASIL" 1,761 times (70% of the lines) and no usable text in minutes 0–58; nothing warned the user. Re-transcribed with `-mc 0`: 4% repeated segments (natural "Ok.") and text in all 86 minutes; with VAD as well: 3% and 84 minutes, 30% slower. `-mc 0` left the word error rate of nine synthetic Portuguese meetings unchanged (2.9% → 2.8%). Hence `-mc 0` on every pass and VAD only on the retry. Evidence: `tasks/prd-llm-wiki/evaluation.md` §14.1 and §14.7.
- **Why a window, not a global count:** counting a text's repeats over the whole meeting also counts natural fillers: "Entendeu?" and "Tá" made 9.8% of the segments of a healthy real 29-minute meeting (07/10), just under the 10% threshold. With the 30-segment window every healthy transcript measured 0% (13 real, 81 synthetic), the looped one 68% (text in 28 of 86 minutes), and its `-mc 0` re-transcription 1.0% (86 of 86). The window catches loops cycling through up to 7 lines; 30 is the widest that keeps the healthy meetings at 0%.
- **The 2026-10-08 meeting retranscribed by the product (2026-10-11):** the first pass with `-mc 0` came out healthy (text in 86 of 86 minutes, 12 min 47 s, no retry needed), and its new analysis covers the whole meeting instead of the last half hour.
- VAD stays off on the first pass: in a test with short sentences it cut off speech. Its effect on long meetings was measured only on the 2026-10-08 audio (above).

# External integrations

| Integration | Type | How it is used | Failure handled as |
|---|---|---|---|
| `teams-tap` (Swift, Core Audio Process Tap) | own binary | `--pid N --out tap.wav --wait-audio 20`: enumerates audio-client processes, filters the target and its descendants, creates a tap + private aggregate device, writes WAV; `--list` for diagnostics; `--mic default|name --out mic.wav` records the microphone through AVAudioEngine | `CaptureError` (missing binary, immediate exit, no audio client after the wait) |
| ffmpeg 9 | CLI | Mixing: per track `highpass=f=80,afftdn=nf=-25:tn=1`; sum `amix … normalize=0`; master `loudnorm=I=-18:TP=-2:LRA=11,alimiter=limit=0.891`; output `-ac 1 -ar 48000 -c:a aac -b:a 64k`. Conversion to 16 kHz mono before whisper. Duration/level measurement (`volumedetect`) | `CaptureError` / `TranscriptionError` |
| whisper.cpp 1.9 (`whisper-cli`) | CLI | `-m ggml-large-v3-turbo-q5_0.bin -l pt -t N -oj -of prefix -np [--vad -vm ggml-silero-v5.1.2.bin -vt 0.5 -vsd 300 -vp 150]` | `TranscriptionError` |
| Models (Hugging Face) | download | `ggerganov/whisper.cpp` for the whisper weights; `ggml-org/whisper-vad` for Silero | script fails with curl's exit code |
| Claude API (`anthropic` 1.x) | HTTP | `client.beta.messages.create(model, max_tokens, system=[{text, cache_control}], messages, output_config={effort, format: json_schema}, betas=[server-side-fallback-2026-07-01], fallbacks="default")` | `AnalysisError` per SDK error class, refusal, truncation, schema |
| Claude Code CLI | subprocess | `claude -p --output-format json --no-session-persistence --restricted --tools "" --model M --effort E --system-prompt S --json-schema J` with the message on stdin; reads `structured_output` | `AnalysisError` |
| `pmset -g assertions` | CLI | Teams call signal | `CallState.unknown` |
| `pgrep -x` | CLI | Teams PID (fallback) | `None` |
| launchd (`launchctl`) | CLI | `bootstrap gui/<uid> plist`, `bootout`, `kickstart -k`, `print` | `RuntimeError` with stderr |
| `osascript` | CLI | `display notification` | ignored (never brings down the pipeline) |

## Required macOS permissions
| Permission | Granted to | Without it |
|---|---|---|
| Microphone | the responsible process (the daemon's python / Claude in manual use) | microphone track silent |
| Screen & System Audio Recording | `teams-tap` (embedded Info.plist with `NSAudioCaptureUsageDescription`) | Teams track silent |

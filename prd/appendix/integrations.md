# External integrations

| Integration | Type | How it is used | Failure handled as |
|---|---|---|---|
| `teams-tap` (Swift, Core Audio Process Tap) | own binary | `--pid N --out tap.wav --wait-audio 20`: enumerates audio-client processes, filters the target and its descendants, creates a tap + private aggregate device, writes WAV; `--list` for diagnostics; `--mic default|name --out mic.wav` records the microphone through AVAudioEngine | `CaptureError` (missing binary, immediate exit, no audio client after the wait) |
| `teams-speakers` (Swift, Accessibility API) | own binary | `--out speakers.jsonl --epoch T [--interval 0.5] [--verbose]` reads the Teams meeting windows (read-only: sets no accessibility attribute) and appends JSON lines (`start`, `window`, `title`, `seen`, `speaking`, `stop`); `--check [--prompt]` reports the Accessibility permission (exit 0 granted, 3 missing); run by the daemon as the launchd job `local.teams-recorder.speakers`, definition in `<data_dir>/run/`, stderr to `data/log/speakers.log` | `SpeakersUnavailable` (`binary-missing`, `permission-missing`, `start-failed`) recorded in `speakers.jsonl`; never fails the recording |
| ffmpeg 9 | CLI | Mixing: per track `highpass=f=80,afftdn=nf=-25:tn=1`; sum `amix … normalize=0`; master `loudnorm=I=-18:TP=-2:LRA=11,alimiter=limit=0.891`; output `-ac 1 -ar 48000 -c:a aac -b:a 64k`. Conversion to 16 kHz mono before whisper. Duration/level measurement (`volumedetect`); RMS level per 100 ms of each raw track (`asetnsamples`, `astats`/`ametadata`) for `energy.json` | `CaptureError` / `TranscriptionError` |
| whisper.cpp 1.9 (`whisper-cli`) | CLI | `-m ggml-large-v3-turbo-q5_0.bin -l pt -t N -oj -of prefix -np [--vad -vm ggml-silero-v5.1.2.bin -vt 0.5 -vsd 300 -vp 150]` | `TranscriptionError` |
| Models (Hugging Face) | download | `ggerganov/whisper.cpp` for the whisper weights; `ggml-org/whisper-vad` for Silero | script fails with curl's exit code |
| Claude API (`anthropic` 1.x) | HTTP | `client.beta.messages.create(model, max_tokens, system=[{text, cache_control}], messages, output_config={effort, format: json_schema}, betas=[server-side-fallback-2026-07-01], fallbacks="default")` | `AnalysisError` per SDK error class, refusal, truncation, schema |
| Claude Code CLI | subprocess | `claude -p --output-format json --no-session-persistence --restricted --tools "" --model M --effort E --system-prompt S --json-schema J` with the message on stdin; reads `structured_output` | `AnalysisError` |
| `pmset -g assertions` | CLI | Teams call signal | `CallState.unknown` |
| `pgrep -x` | CLI | Teams PID (fallback) | `None` |
| launchd (`launchctl`) | CLI | `bootstrap gui/<uid> plist`, `bootout`, `kickstart -k`, `print` | `RuntimeError` with stderr |
| `osascript` | CLI | `display notification` | ignored (never brings down the pipeline) |
| Backlog.md 1.53 (`backlog`) | CLI | `task create --desc D -s Triagem -l L… [--priority P] [--ac C…] --plain -- <title>` run in the board's project folder; id read from `Task <ID> - ` in the plain output. One-time `init --no-git --defaults --integration-mode none` | `PublishError` (missing binary, exit ≠ 0, timeout, no id); `problems()` for an unready board |
| `git check-ignore -q` | CLI | Confirms the board folder is git-ignored when it sits inside a work tree | anything but "ignored" refuses publishing (fails closed) |

## Required macOS permissions
| Permission | Granted to | Without it |
|---|---|---|
| Microphone | the responsible process (the daemon's python / Claude in manual use) | microphone track silent |
| Screen & System Audio Recording | `teams-tap` (embedded Info.plist with `NSAudioCaptureUsageDescription`) | Teams track silent |
| Accessibility | `teams-speakers` itself (embedded Info.plist, bundle id `local.teams-recorder.teams-speakers`); added by hand with the **+** button because a background job's request creates no entry; the helper must be its own responsible process, hence its own launchd job (a spawn from the daemon's Python would be judged by the Python's grant); a rebuild of the ad-hoc-signed binary may drop the grant | No speaker labels from the window (recording unaffected; your own lines still labelled); `trec doctor` and a daily notification say so |

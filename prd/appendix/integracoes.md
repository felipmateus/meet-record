# Integrações externas

| Integração | Tipo | Como é usada | Falha tratada como |
|---|---|---|---|
| `teams-tap` (Swift, Core Audio Process Tap) | binário próprio | `--pid N --out tap.wav --wait-audio 20`: enumera os processos clientes de áudio, filtra o alvo e descendentes, cria tap + dispositivo agregado privado, grava WAV; `--list` diagnostica; `--mic default|nome --out mic.wav` grava o microfone via AVAudioEngine | `CaptureError` (binário ausente, saída imediata, sem cliente de áudio após a espera) |
| ffmpeg 9 | CLI | Mixagem: por trilha `highpass=f=80,afftdn=nf=-25:tn=1`; soma `amix … normalize=0`; master `loudnorm=I=-18:TP=-2:LRA=11,alimiter=limit=0.891`; saída `-ac 1 -ar 48000 -c:a aac -b:a 64k`. Conversão para 16 kHz mono antes do whisper. Medição de duração/níveis (`volumedetect`) | `CaptureError` / `TranscriptionError` |
| whisper.cpp 1.9 (`whisper-cli`) | CLI | `-m ggml-large-v3-turbo-q5_0.bin -l pt -t N -oj -of prefix -np [--vad -vm ggml-silero-v5.1.2.bin -vt 0.5 -vsd 300 -vp 150]` | `TranscriptionError` |
| Modelos (Hugging Face) | download | `ggerganov/whisper.cpp` para os pesos do whisper; `ggml-org/whisper-vad` para o Silero | script falha com código do curl |
| Claude API (`anthropic` 1.x) | HTTP | `client.beta.messages.create(model, max_tokens, system=[{text, cache_control}], messages, output_config={effort, format: json_schema}, betas=[server-side-fallback-2026-07-01], fallbacks="default")` | `AnalysisError` por classe de erro do SDK, recusa, truncamento, esquema |
| Claude Code CLI | subprocesso | `claude -p --output-format json --no-session-persistence --restricted --tools "" --model M --effort E --system-prompt S --json-schema J` com a mensagem em stdin; lê `structured_output` | `AnalysisError` |
| `pmset -g assertions` | CLI | sinal de chamada do Teams | `CallState.unknown` |
| `pgrep -x` | CLI | PID do Teams (reserva) | `None` |
| launchd (`launchctl`) | CLI | `bootstrap gui/<uid> plist`, `bootout`, `kickstart -k`, `print` | `RuntimeError` com stderr |
| `osascript` | CLI | `display notification` | ignorada (nunca derruba o pipeline) |

## Permissões do macOS exigidas
| Permissão | Para quem | Sem ela |
|---|---|---|
| Microfone | processo responsável (python do daemon / Claude no uso manual) | trilha do microfone em silêncio |
| Gravação de Tela e Áudio do Sistema | `teams-tap` (Info.plist embutido com `NSAudioCaptureUsageDescription`) | trilha do Teams em silêncio |

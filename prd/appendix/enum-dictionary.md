# State and enumeration dictionary

## Meeting state (`MeetingStatus`) — derived from the files in the folder
| Value | Condition (precedence from top to bottom) | Next step |
|---|---|---|
| `failed` | `error.txt` exists | fix and repeat the step (the pipeline clears the error when resuming) |
| `analyzed` | `analysis.json` exists | none (goes into the daily plan) |
| `transcribed` | `transcript.json` exists | `analyze` |
| `recorded` | `audio.m4a` exists | `transcribe` |
| `recording` | only `meta.json` (and raw tracks) | `stop` |

Note: `audio.m4a` may have been deleted by retention without changing `transcribed`/`analyzed`.

## Files of a meeting
| File | When it exists | Content |
|---|---|---|
| `meta.json` | always | id, start, end, target PID, title |
| `tap.wav`, `mic.wav` | only during recording | raw tracks (deleted after the mix) |
| `audio.m4a` | after `stop` | mono AAC 48 kHz mix |
| `transcript.json`, `transcript.txt` | after `transcribe` | segments / timestamped text |
| `analysis.json` | after `analyze` | structured record |
| `error.txt` | after a failure | `step: message` |
| `.lock` | during a step | PID of the process doing the processing |
| `debug/*.wav` | track anomaly | preserved raw copies |

## Detector state (`CallState`)
| Value | Meaning |
|---|---|
| `in_call` | watched process holds a call assertion |
| `idle` | no assertion |
| `unknown` | `pmset` reading failed (neutral in the hysteresis) |

## Action status (`ActionStatus`)
| Value | Meaning |
|---|---|
| `open` | pending |
| `done` | completed (marked by the daily plan) |
| `overdue` | deadline passed as of the plan date |

## Meeting type (`MeetingType`, in `analysis.json`)
| Value | Meaning | Minutes label |
|---|---|---|
| `standup` | daily status round | Daily |
| `client` | with a customer or external party | Reunião com cliente |
| `project_review` | progress, risks, milestones | Revisão de projeto |
| `one_on_one` | two people, personal follow-up | 1:1 |
| `other` | anything else (default) | Reunião |

## Action priority (`Priority`)
| Value | Set when | Minutes label |
|---|---|---|
| `high` | urgency stated ("urgente", "o quanto antes") | 🔴 Alta |
| `medium` | some urgency implied | 🟡 Média |
| `low` | explicitly deferrable | 🟢 Baixa |
| *(null)* | nobody said | — |

## LLM provider (`llm.provider`)
| Value | Transport | Billing |
|---|---|---|
| `api` | Claude API, official SDK | prepaid credit |
| `claude-code` | headless `claude -p` | Claude Code subscription |

## Microphone backend (`audio.mic_backend`)
| Value | Implementation | Notes |
|---|---|---|
| `coreaudio` (default) | `teams-tap --mic` (AVAudioEngine) | tolerates device reconfiguration; follows the default input |
| `ffmpeg` | avfoundation | stopped recording when Teams opened the microphone |

## Power assertions recognized as a call
`PreventUserIdleDisplaySleep`, `PreventUserIdleSystemSleep`, `NoIdleSleepAssertion`, `NoDisplaySleepAssertion`. `UserIsActive` and others do not count.

## CLI exit codes
| Code | Meaning |
|---|---|
| 0 | success |
| 1 | runtime error, or at least one meeting failed |
| 2 | command from a phase not yet available |

## macOS notifications
Shown verbatim in Portuguese, as the user sees them: "Recording started", "Recording stopped" (recording ended, with minutes), "Recording cancelled", "Transcription failed", "Analysis failed", "Daily plan ready" (plan of the day ready; phase 6).

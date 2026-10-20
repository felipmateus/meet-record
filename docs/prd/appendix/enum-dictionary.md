# State and enumeration dictionary

## Meeting state (`MeetingStatus`) — derived from the files in the folder
| Value | Condition (precedence from top to bottom) | Next step |
|---|---|---|
| `failed` | `error.txt` exists | fix and repeat the step (the pipeline clears the error when resuming) |
| `analyzed` | `analysis.json` exists | none (the curator takes it into the activities document) |
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
| `speakers.jsonl` | during recording (macOS, observer wired) | who spoke when, names seen, meeting subject; not part of the status |
| `energy.json` | after `stop` | level of each raw track per 100 ms; not part of the status |
| `transcript.json`, `transcript.txt` | after `transcribe` | segments (with `speaker` when known) / timestamped text, plus the labelling summary |
| `analysis.json` | after `analyze` | structured record |
| `error.txt` | after a failure | `step: message` |
| `curation_error.txt` | when the activities curator could not take this meeting | `Activity curation failed: <reason>`; cleared by a later successful pass; not part of the status (a meeting with only this file is still `analyzed`) |
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
| `done` | completed |
| `overdue` | **decode only**: the planner that set it was removed on 2026-10-20; old `analysis.json` files may hold it, and nothing sets or reads it any more |

## Action kind (`ActionKind`, in `analysis.json` actions and in `plans/<day>.stories.json` stories)
| Value | Meaning | In a story draft |
|---|---|---|
| `feature` | a change in how the product behaves | user story |
| `bug` | something that should work and does not | user story (the guide's bug format) |
| `technical` | engineering work without direct user value: estimate, spike, mock | task card |
| `operation` | deploy, access, infrastructure, environment | task card |
| `management` | process, reports, metrics, prioritisation | not drafted: left out with "<tipo>: não vira história nem card" |
| `communication` | e-mail, meeting, follow-up, review | not drafted, same |

The analysis gives every action a kind (older analyses have none); nothing routes by it any more. The story writer sets the kind of each story from the item the user tagged.

## Progress change (`StatusChange`, in `analysis.json` `status_updates`)
| Value | Meaning | Minutes label |
|---|---|---|
| `done` | finished, delivered, deployed, sent | concluído |
| `in_progress` | being worked on right now, no problem | em andamento |
| `blocked` | cannot move until something else happens | bloqueado |
| `delayed` | will be late (a new date when one was said) | atrasado |
| `due_changed` | a new date was agreed | prazo alterado |
| `reassigned` | someone else will do it now (`new_owner`) | reatribuído |
| `cancelled` | dropped, no longer needed | cancelado |

## Pass kind (`PassKind`, in `log/activities.jsonl`)
| Value | Meaning |
|---|---|
| `meeting` | a curator pass that changed the document (the only kind with version files; the target of `undo`) |
| `undo` | a restore made by `trec activities undo` (`undoes` names the pass it undid) |
| `skipped_empty` | the batch had nothing to curate: no call, document unchanged |
| `failed` | the pass failed: document unchanged (`error` holds the reason) |

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
Shown verbatim in Portuguese, as the user sees them: "Recording started", "Recording stopped" (recording ended, with minutes), "Recording cancelled", "Transcription failed", "Analysis failed", "Activities updated" (the body is the curator's one-line summary in Portuguese) and "Activity curation failed".

# Meeting analysis

> **Command:** `trec analyze [id]`
> **Module:** Analysis · **Generated:** 2026-10-05

## Overview
Turns the transcript into a structured record of what matters to the user: summary, decisions, the user's own actions, third-party actions to follow up on, deadlines, open questions and upcoming meetings. It is the input for the daily plan.

## Fields and options
| Argument / config | Type | Default | Description |
|---|---|---|---|
| `id` | text | all in state `transcribed` | Specific meeting |
| `llm.provider` | `api` \| `claude-code` | `api` | Transport: Claude API (key in `.env`) or headless Claude Code (subscription). Overridable through `TREC_LLM_PROVIDER` |
| `llm.model` / `llm.cli_model` | text | `claude-opus-5-5` / `opus` | Model per provider |
| `llm.effort` | low…max | `high` | Reasoning depth |
| `llm.max_tokens` | integer | 16000 | Output cap (API) |

## Structured output (schema)
| Field | Type | Extraction rule |
|---|---|---|
| `summary` | text | 3 to 6 sentences, objective |
| `decisions[]` | text | only what was actually decided |
| `my_actions[]` | description, owner (`usuário`), ISO due date or null | the user's commitments; verb in the infinitive |
| `others_actions[]` | description, owner, due date | third-party tasks that affect the user; `indefinido` (undetermined) when the owner cannot be identified |
| `deadlines[]` | what, when (ISO or null), who | relative expressions resolved against the meeting date given in the prompt |
| `open_questions[]` | text | unanswered questions |
| `next_meetings[]` | text | agreed follow-up meetings |

Each action receives a short unique id and `status = open`. The prompt explicitly instructs the model not to invent tasks, deadlines or decisions.

## Interactions
- **Pre-validation:** the `api` provider requires the key; `claude-code` requires the `claude` executable on the PATH. Messages point to the alternative.
- **Short circuit:** an empty transcript, or one with fewer than 20 words, receives a local analysis ("Transcript too short …", transcript too short) with no model call.
- **Call (API):** fixed, cached system prompt; user message with date, weekday, time, title, duration and the timestamped transcript; output forced by JSON Schema (closed objects, all fields required); server-side fallback for occasional safety-classifier refusals; client-side Pydantic validation.
- **Call (Claude Code):** same prompt and schema through `claude -p --output-format json --json-schema`, restricted mode and no tools.
- **Explicit errors:** final refusal, truncated response, output outside the schema, authentication, rate limit, connection. They become `error.txt` in the meeting folder.
- **Usage logging:** input/output/cache tokens and cost (or equivalent) in `data/log/llm_usage.jsonl`.
- **Terminal output:** provider in use, counts, summary and the list of the user's actions with due dates.

## Integrations
| Integration | Use |
|---|---|
| Claude API (`anthropic` SDK 1.x) | `beta.messages.create` with `output_config.format`, `cache_control`, `fallbacks="default"` |
| Claude Code CLI | headless `claude -p` |

## Relationships
- **From:** [Transcription](./02-transcription.md). **To:** [Daily plan](./06-daily-plan.md) (state `analyzed`).

## Business rules
- Only the transcript text and the prompt leave the Mac.
- With Claude Code there is no refusal fallback, and the analysis depends on a logged-in session on the Mac (relevant for the daemon).

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
| `title` | text | short title (≤ 8 words) inferred from the content; names untitled automatic recordings |
| `purpose` | text | one sentence: why the meeting happened |
| `meeting_type` | enum | `standup`, `client`, `project_review`, `one_on_one`, `other` |
| `participants[]` | text | names mentioned or addressed (no guessing; no diarization yet) |
| `summary` | text | 3 to 6 sentences, objective |
| `topics[]` | title, points[] | main discussion topics in order, 1 to 4 key points each |
| `decisions[]` | text | only what was actually decided |
| `my_actions[]` | description, owner (`usuário`), ISO due date or null | the user's commitments; verb in the infinitive |
| `others_actions[]` | description, owner, due date | third-party tasks that affect the user; `indefinido` (undetermined) when the owner cannot be identified |
| `deadlines[]` | what, when (ISO or null), who | relative expressions resolved against the meeting date given in the prompt |
| `open_questions[]` | text | unanswered questions |
| `next_meetings[]` | text | agreed follow-up meetings |
| `risks[]` | text | risks, blockers and issues raised |

Decisions are `{text, at}` and actions carry `priority` (`high`/`medium`/`low`, only when urgency was stated) and `at`, the `HH:MM:SS` transcript timestamp where it was said, so the user can verify each item. The message to the model starts with the user's name (`[user] name` in `config.toml`), and the prompt lists Portuguese cue phrases for actions and decisions. Old analyses (plain-string decisions, no new fields) still load with defaults.

## Minutes (`minutes.md`)
Written next to `analysis.json` after each analysis by `MarkdownMinutesRenderer` (no LLM call), in the structure of the `meeting-notes` skill: title, date and time, participants, type, purpose, summary, topics, decisions with timestamps, an action table (owner — the user shown by name, `⚠️ sem responsável` when unknown — due date, priority, timestamp), risks, open questions and next steps; empty sections are omitted. `trec minutes [id] [--all]` re-renders from existing analyses.

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

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
| `participants[]` | text | people who speak or are addressed directly, not people only talked about (no guessing); when the transcript carries a roster read from the Teams window, exactly that list. Owners are taken from the speaker label of a line when it has one (the user's label gives `usuário`); the first-person heuristic applies only to unlabelled lines |
| `summary` | text | 3 to 6 sentences, objective |
| `topics[]` | title, points[] | main discussion topics in order, 1 to 4 key points each |
| `decisions[]` | text | only what was actually decided; tentative statements are not decisions |
| `my_actions[]` | description, owner (`usuário`), ISO due date or null, kind | the user's commitments; verb in the infinitive |
| `others_actions[]` | description, owner, due date, kind | third-party tasks that affect the user; `indefinido` (undetermined) unless the transcript makes the owner evident |
| `deadlines[]` | what, when (ISO or null), who | relative expressions resolved against the meeting date given in the prompt |
| `open_questions[]` | text | unanswered questions |
| `next_meetings[]` | text | agreed follow-up meetings |
| `risks[]` | text | risks, blockers and issues raised |

Every action (the user's and others') also carries a **kind**, which decides where it goes after the plan: `feature` or `bug` (product work → user story), `technical` (estimates, investigations, mocks, refactoring) or `operation` (deploys, access, infrastructure) → task card on the board, `management` (process, reports, metrics, tickets) or `communication` (e-mails, meetings, follow-ups, reviews) → stays in the daily plan. The rules are in `prompts/analyze_system.md`; actions extracted before 2026-10-10 have no kind. Decisions are `{text, at}` and actions carry `priority` (`high`/`medium`/`low`, only when urgency was stated) and `at`, the `HH:MM:SS` transcript timestamp where it was said, so the user can verify each item. The message to the model starts with the user's name (`[user] name` in `config.toml`), and the prompt lists Portuguese cue phrases for actions and decisions. Fidelity rules (fidelity guard task 6.0, from the errors measured in the evaluation): another person is named as owner only when the transcript makes it evident (named or addressed as the one who will do it, or clearly taking it on), else `indefinido`; a first-person commitment stays the user's, and the verifier marks it when the owner is not evident; tentative statements are never decisions; no sensitive personal data in any field (the list is in the prompt), and an absence is written without its reason. Old analyses (plain-string decisions, no new fields) still load with defaults.

## Minutes (`minutes.md`)
Written next to `analysis.json` after each analysis by `MarkdownMinutesRenderer` (no LLM call), in the structure of the `meeting-notes` skill: title, date and time, participants, type, purpose, summary, topics, decisions with timestamps, an action table (owner — the user shown by name, `⚠️ sem responsável` when unknown — due date, priority, timestamp), risks, open questions and next steps; empty sections are omitted. `trec minutes [id] [--all]` re-renders from existing analyses. A degraded transcript (see [Transcription](./02-transcription.md)) opens the minutes with a warning banner. Each decision, action, deadline and participant that claim verification did not confirm in the transcript is kept, marked "⚠️ _a confirmar: <reason>_", with a legend under the title; nothing is removed, and minutes of unverified analyses look as before.

## Claim verification
After the analysis and before `analysis.json` and the minutes are saved, `VerifyAnalysis` checks each claim (fidelity guard, tasks 3.0 and 7.0). One call to a smaller model (`[verification]`: Sonnet at medium effort, on the `[llm]` provider) reads the transcript, whole or around each claim's timestamp when long, and judges every decision, action, deadline and participant; code turns the verdict into confirmed or unconfirmed with a reason in Portuguese. Two checks in code can also mark a claim unconfirmed: sensitive personal data, and a participant who neither speaks nor is addressed. The call is logged in `llm_usage.jsonl` as `verify:<meeting>`. A failed call leaves its claims unverified, and the analysis is saved anyway.

A transcript that cannot be trusted (still degraded after the retry, or made from a Teams track recorded at the wrong sample rate) is not sent to the verifier, which would confirm what the analysis took from the same hallucinated text. Its claims stay unverified (the code checks still apply), and the minutes' and drafts document's banners add that no item was confirmed from it. The meeting still yields stories. `[verification] enabled = false` turns off the model call; the two code checks still run.

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

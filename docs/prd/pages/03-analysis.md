# Meeting analysis

> **Command:** `trec analyze [id]` (after its loop it also runs the activities curator on the meetings it analyzed: see [Activities document](./09-activities.md))
> **Module:** Analysis · **Generated:** 2026-10-05

## Overview
Turns the transcript into a structured record of what matters to the user: summary, decisions, the user's own actions, third-party actions to follow up on, deadlines, open questions and upcoming meetings, plus what the meeting said about work that already existed (progress reported). It is the input for the [activities document](./09-activities.md) and for the story drafts the user asks for.

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
| `my_actions[]` | description, owner (`usuário`), ISO due date or null, kind, for whom | the user's commitments; verb in the infinitive |
| `others_actions[]` | description, owner, due date, kind, for whom | third-party tasks that affect the user; `indefinido` (undetermined) unless the transcript makes the owner evident |
| `status_updates[]` | about, change, who, evidence, at, new date, new owner | what the meeting said happened to work that existed before it, one entry per statement; see below |
| `deadlines[]` | what, when (ISO or null), who | relative expressions resolved against the meeting date given in the prompt |
| `open_questions[]` | text | unanswered questions |
| `next_meetings[]` | text | agreed follow-up meetings |
| `risks[]` | text | risks, blockers and issues raised |

Every action (the user's and others') also carries a **kind**: `feature` or `bug` (product work), `technical` (estimates, investigations, mocks, refactoring), `operation` (deploys, access, infrastructure), `management` (process, reports, metrics, tickets) or `communication` (e-mails, meetings, follow-ups, reviews). It is stored in `analysis.json`; since the planner was removed nothing routes by it, and the story writer decides each story's kind from the item the user tagged (see [User story drafts](./08-user-stories.md)). The rules are in `prompts/analyze_system.md`; actions extracted before 2026-10-10 have no kind. Decisions are `{text, at}` and actions carry `priority` (`high`/`medium`/`low`, only when urgency was stated) and `at`, the `HH:MM:SS` transcript timestamp where it was said, so the user can verify each item. The message to the model starts with the user's name (`[user] name` in `config.toml`), and the prompt lists Portuguese cue phrases for actions and decisions. Fidelity rules (fidelity guard task 6.0, from the errors measured in the evaluation): another person is named as owner only when the transcript makes it evident (named or addressed as the one who will do it, or clearly taking it on), else `indefinido`; a first-person commitment stays the user's, and the verifier marks it when the owner is not evident; tentative statements are never decisions; no sensitive personal data in any field (the list is in the prompt), and an absence is written without its reason. Old analyses (plain-string decisions, no new fields) still load with defaults.

**Progress on earlier work (`status_updates`) and `for_whom`.** A status update is a statement about work that existed before the meeting, not a new task: something finished, under way, blocked, late, with a new date, passed to someone else or dropped. Each entry has `about` (the work, in the meeting's own words and specific enough to be found in a list of tasks), `change` (`done`, `in_progress`, `blocked`, `delayed`, `due_changed`, `reassigned`, `cancelled`), `who` (the same owner rules as for actions: `usuário`, a name only when evident, else `indefinido`), `evidence` (the literal quote, at most 20 words, hedges kept), `at` (the `HH:MM:SS` of that line), and `new_due` / `new_owner` when a date or a person was said. An intention is not progress ("vou subir o timesheet" is an action, never `done`), a hedge ("acho que já enviei") is never recorded as `done`, and a question is not a statement. `for_whom` on an action is the person or party who receives the result or waits for it, only when the meeting said so; it is not the owner. The analyzer never sees the activities document: matching a statement to an item is the curator's job. Analyses saved earlier have neither field and load with empty defaults.

**Transcript language.** A meeting held in English is analyzed like any other and the output stays in Brazilian Portuguese; only a literal quote (`evidence`, a decision's or a claim's quoted words) keeps the language it was said in. When the transcript's language is not Portuguese, the message to the analyzer and to the claim verifier carries one header line naming it (`Transcript language: English`); a Portuguese transcript's message is unchanged. The verifier's participant check also accepts English greetings (`hi`, `hello`, `hey`, `thanks`, `thank you`) when no speaker labels exist.

## Minutes (`minutes.md`)
Written next to `analysis.json` after each analysis by `MarkdownMinutesRenderer` (no LLM call), in the structure of the `meeting-notes` skill: title, date and time, participants, type, purpose, summary, topics, decisions with timestamps, an action table (owner — the user shown by name, `⚠️ sem responsável` when unknown — due date, priority, timestamp), risks, open questions and next steps; empty sections are omitted. After the actions, a **🔄 Andamento informado** section lists the status updates, one line each: who (`Você` for the user, `Alguém` when undetermined), the change in Portuguese (`concluído`, `em andamento`, `bloqueado`, `atrasado`, `prazo alterado`, `reatribuído`, `cancelado`), about what, the new date or owner when there is one, the quote and its timestamp, for example `- Diego: concluído — conversão de unidade no relatório de estoque · "o fix já tá em homologação" [00:06:40]`; the section is omitted when there are none. `trec minutes [id] [--all]` re-renders from existing analyses. A transcript that is not in Portuguese adds one line after the date, `🗣️ **Idioma:** inglês`. A degraded transcript (see [Transcription](./02-transcription.md)) opens the minutes with a warning banner. Each decision, action, deadline and participant that claim verification did not confirm in the transcript is kept, marked "⚠️ _a confirmar: <reason>_", with a legend under the title; nothing is removed, and minutes of unverified analyses look as before.

## Claim verification
After the analysis and before `analysis.json` and the minutes are saved, `VerifyAnalysis` checks each claim (fidelity guard, tasks 3.0 and 7.0). One call to a smaller model (`[verification]`: Sonnet at medium effort, on the `[llm]` provider) reads the transcript, whole or around each claim's timestamp when long, and judges every decision, action, deadline, status update and participant; code turns the verdict into confirmed or unconfirmed with a reason in Portuguese. A status update is checked against its quote and the lines around its timestamp: an intention does not support `done` or `in_progress`, a hedge does not support `done`, a quote about other work or from another person supports nothing, and a stated new date or new owner must be what was said. An unconfirmed status update stays in the minutes ending ` ⚠️ não confirmado: <reason>` and reaches the curator marked unconfirmed, so the 💬 suggestion it produces ends with `⚠️ a confirmar: <reason>`. Two checks in code can also mark a claim unconfirmed: sensitive personal data, and a participant who neither speaks nor is addressed. The call is logged in `llm_usage.jsonl` as `verify:<meeting>`. A failed call leaves its claims unverified, and the analysis is saved anyway.

A transcript that cannot be trusted (still degraded after the retry, or made from a Teams track recorded at the wrong sample rate) is not sent to the verifier, which would confirm what the analysis took from the same hallucinated text. Its claims stay unverified (the code checks still apply), and the minutes' and drafts document's banners add that no item was confirmed from it. Items from that meeting can still be tagged and drafted as stories. `[verification] enabled = false` turns off the model call; the two code checks still run.

Each action receives a short unique id and `status = open`. The prompt explicitly instructs the model not to invent tasks, deadlines or decisions.

## Interactions
- **Pre-validation:** the `api` provider requires the key; `claude-code` requires the `claude` executable on the PATH. Messages point to the alternative.
- **Short circuit:** an empty transcript, or one with fewer than 20 words, receives a local analysis ("Transcript too short …", transcript too short) with no model call.
- **Call (API):** fixed, cached system prompt; user message with date, weekday, time, title, duration and the timestamped transcript; output forced by JSON Schema (closed objects, all fields required); server-side fallback for occasional safety-classifier refusals; client-side Pydantic validation.
- **Call (Claude Code):** same prompt and schema through `claude -p --output-format json --json-schema`, restricted mode and no tools.
- **Explicit errors:** final refusal, truncated response, output outside the schema, authentication, rate limit, connection. They become `error.txt` in the meeting folder.
- **Usage logging:** input/output/cache tokens and cost (or equivalent) in `data/log/llm_usage.jsonl`.
- **Terminal output:** provider in use, counts, summary and the list of the user's actions with due dates.
- **Curation step:** with `[activities] enabled = true`, `trec analyze` then curates the meetings it analyzed successfully (four per pass, oldest first) and prints one `Curating <title> (<dd/mm>)… ok (<n> edits) — <summary>` line per pass, or `… failed: <reason>`. A curation failure leaves the exit code at 0 when every analysis succeeded (the meeting stays `analyzed`, its `curation_error.txt` explains, and the daemon retries it); an analysis failure exits 1 as before and that meeting is not curated.

## Integrations
| Integration | Use |
|---|---|
| Claude API (`anthropic` SDK 1.x) | `beta.messages.create` with `output_config.format`, `cache_control`, `fallbacks="default"` |
| Claude Code CLI | headless `claude -p` |

## Relationships
- **From:** [Transcription](./02-transcription.md). **To:** the [Activities document](./09-activities.md) (state `analyzed`) and, through it, the [story drafts](./08-user-stories.md).

## Business rules
- Only the transcript text and the prompt leave the Mac.
- With Claude Code there is no refusal fallback, and the analysis depends on a logged-in session on the Mac (relevant for the daemon).

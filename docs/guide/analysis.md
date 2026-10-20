# Analysis with Claude

```bash
trec analyze                         # every transcribed meeting not yet analyzed
trec analyze 2026-10-06_14-00-00     # one meeting
```

The model returns a schema-validated record:

| Field | Content |
|---|---|
| `title`, `purpose`, `meeting_type` | Inferred title (names untitled automatic recordings), why the meeting happened, and its type (`standup`, `client`, `project_review`, `one_on_one`, `other`) |
| `participants`, `summary`, `topics` | People who speak or are addressed (not people only talked about), or the roster read from the Teams window when there is one; 3–6 sentence summary, topics with key points |
| `decisions` | Only what was actually decided, with timestamp |
| `my_actions`, `others_actions` | Description, owner, ISO due date, priority (only when urgency was stated), timestamp, and **kind** |
| `status_updates` | What the meeting said about work that already existed: `about`, `change` (`done`, `in_progress`, `blocked`, `delayed`, `due_changed`, `reassigned`, `cancelled`), `who`, the literal quote (at most 20 words, hedges kept), timestamp, and the new date or owner when said |
| `deadlines`, `open_questions`, `next_meetings`, `risks` | Relative dates are resolved against the meeting date |

An action also carries `for_whom` when the meeting said who waits for the result. An intention ("vou subir") is never progress, and a hedge ("acho que já enviei") is never recorded as `done`. Each action also carries a kind (`feature`, `bug`, `technical`, `operation`, `management`, `communication`), kept in `analysis.json`; nothing routes by it since the planner was removed, and the story writer decides the kind of a story from the item you tagged. The rules are in `prompts/analyze_system.md`.

`minutes.md` follows the structure of the `meeting-notes` skill: title, date, participants, type and purpose, summary, topics, decisions, an action table (owner, due date, priority, timestamp), a `🔄 Andamento informado` section with the status updates, risks, open questions and next steps.

Safeguards:

- Transcripts under 20 words are not sent to the model, because whisper hallucinates on silence. They get a local "transcript too short" analysis instead.
- Refusals, truncated responses and schema violations are errors. A partial analysis is never saved.
- The model is told not to invent tasks, deadlines or decisions, to name another person as owner only when the transcript makes it evident (else `indefinido`), not to record tentative statements as decisions, and to keep sensitive personal data (health and private life, for example; the list is in `prompts/analyze_system.md`) out of every field.
- **Claim verification** (`[verification]`, on by default): one more call, Sonnet at medium effort on the same provider, checks every decision, action, deadline, status update and participant against the transcript. What it cannot confirm is kept and marked "⚠️ _a confirmar: <motivo>_" in `minutes.md`, and the story writer never cites it as the source of a criterion. Two checks in code also mark claims with sensitive personal data and participants who neither speak nor are addressed. A failed call leaves the claims unverified and never blocks the analysis. A degraded transcript, or one from a Teams track recorded at the wrong sample rate, is not checked: the verifier would confirm the hallucinations the analysis took from it. Its banners in `minutes.md` and the story drafts say so. `enabled = false` turns off the call; the two code checks still run.
- Every call logs tokens (and cost, or its equivalent) to `data/log/llm_usage.jsonl`; verifier calls are tagged `verify:<meeting>`.

## Provider: API or Claude Code

`llm.provider` in `config.toml` selects the transport. The same provider serves the analysis, the claim verifier, the activities curator and the stories.

| `provider` | Uses | Billing | Notes |
|---|---|---|---|
| `api` (default when unset) | Claude API with `ANTHROPIC_API_KEY` from `.env` | Prepaid credit, about US$ 0.10 per hour of meeting | Cached system prompt, server-side fallback for occasional safety-classifier refusals |
| `claude-code` | Claude Code in headless mode (`claude -p`) | Your Claude Code subscription | Needs a logged-in session on the Mac; no refusal fallback; model alias in `llm.cli_model` |

`TREC_LLM_PROVIDER` overrides the file, for example `TREC_LLM_PROVIDER=claude-code trec analyze`. To set it for the daemon, run `trec agent install --env TREC_LLM_PROVIDER=claude-code`.

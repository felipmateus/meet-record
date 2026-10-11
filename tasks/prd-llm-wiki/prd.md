# PRD: LLM wiki of meetings

> **Status:** draft for approval · **Date:** 2026-10-10 · **Slug:** `llm-wiki`
> **Builds on:** [Analysis](../../prd/pages/03-analysis.md) (`analysis.json`, `minutes.md`), [Daily plan](../../prd/pages/06-daily-plan.md), [User stories](../../prd/pages/08-user-stories.md)
> **Technical design:** [techspec.md](./techspec.md) · **Evaluation protocol:** [evaluation.md](./evaluation.md)
> **Pattern:** Andrej Karpathy's "LLM Wiki" (an LLM compiles raw sources into a persistent, interlinked Markdown wiki it maintains itself). The desktop implementation `nashsu/llm_wiki` was studied and not integrated (§9).

## 1. Problem

Every meeting is analyzed on its own. The daily plan sees one day plus the list of open actions; the story writer sees 30 days of stories, and only to avoid duplicates. Nothing accumulates across meetings: the user cannot ask "what has been decided about project X so far", "what is the *current* deadline of Y", or "what is pending with João across every meeting" without re-reading transcripts or minutes. A deadline that moves is not recorded as a change; names whisper gets wrong are never corrected; the context a later analysis or story could use (who owns what, recurring blockers) is lost.

## 2. Goal

A knowledge base the model compiles once per meeting and keeps current: one page per person, project and topic, with the current state first and a dated history underneath, every claim citing the meeting (and the transcript timestamp) it came from. The daemon feeds it after each analysis; the user reads it in Obsidian and asks questions through Claude Code inside the wiki folder. Before ingest is switched on for good, a repeatable evaluation proves that the wiki answers questions about the meetings better than the simple alternative, which is pasting all the minutes into the model's context.

## 3. User and context

- Same single user and Mac. 13 meetings so far (about 7,000 words of minutes and 26,000 words of transcripts); roughly 100 meetings a month expected. At that scale an `index.md` read by the model is enough to find pages; no embeddings or search engine.
- Content is confidential and stays on the Mac; the model receives only what the analysis already sends today (the transcript text) plus the wiki pages it needs.
- The alternative is real: today all minutes fit in one context window. The wiki is only worth its cost if the evaluation (§7) shows it wins where it should: synthesis across meetings, facts that changed over time, aggregation per person or project.

## 4. Scope

**In scope**
- Ingest of every analyzed meeting into a Markdown wiki, automatically after the analysis (when enabled) and by hand, oldest first for backfills.
- A fixed wiki layout (people, projects, topics, meetings, overview, index, log, schema file) readable in Obsidian and by Claude Code.
- Validation in code of everything the model writes (page type, slug, size, count, sources, frontmatter), a meeting page, index and log written by code, and a record in the meeting folder of what each ingest did.
- Serialization of concurrent ingests, failure isolation from the meeting pipeline, retry and rebuild commands, a code-only lint.
- Visibility in `trec status` and `trec doctor`; an optional local Git history of the wiki.
- An evaluation harness (synthetic corpus with planted facts, repeated runs, calibrated judge, the user's own questions on real meetings) and the decision, based on it, to enable automatic ingest.

**Out of scope (later)**
- Feeding the wiki back into the pipeline: a glossary of names for the analysis, project context for stories and the plan. The port is designed for it (`WikiStore.pages()` exposes titles and aliases).
- `trec wiki ask`: querying is done with Claude Code in the wiki folder (its `CLAUDE.md` holds the workflow) or in Obsidian.
- LLM-based lint (hunting contradictions and stale claims across pages); embeddings or a search index; other raw sources than meetings; several users or shared wikis.

## 5. Functional requirements

| # | Requirement |
|---|---|
| FR1 | Every meeting in state `analyzed` is ingested into the wiki exactly once: automatically right after the analysis when `[wiki] enabled = true`, and by hand with `trec wiki ingest [id] [--force]`. With no id, every analyzed meeting not yet ingested is processed oldest first, continuing after failures (exit 1 if any failed). |
| FR2 | The wiki is a folder of Markdown files with YAML frontmatter and `[[wikilinks]]`: `people/`, `projects/`, `topics/`, `meetings/`, `overview.md`, `index.md`, `log.md` and `CLAUDE.md` (the schema). It opens as an Obsidian vault and as a Claude Code project. |
| FR3 | The model writes and updates person, project, topic and overview pages. Code writes the meeting page (from the minutes), `index.md` (from every page's frontmatter), `log.md` (append-only), and the frontmatter fields `sources`, `created` and `updated`. Every edit is validated in code (allowed type, slug, size, count, non-empty); a rejected edit is recorded in the ingest record and the log, never silently dropped. |
| FR4 | Pages state the current value first and keep a dated history: when a fact changes (deadline, owner, decision), the current value is updated and the previous one stays with the meeting that changed it; a contradiction the model cannot resolve is flagged on the page. |
| FR5 | Every claim is traceable: pages cite the source meeting page and, when the transcript was sent, the `HH:MM:SS` timestamp. `wiki.json` in the meeting folder records when the meeting was ingested, which pages were created or updated and which edits were rejected. |
| FR6 | A wiki failure never changes the meeting's state, never blocks the daily plan and never stops the pipeline for other meetings: it is logged, notified ("Wiki update failed"), written to `wiki_error.txt` in the meeting folder and retried by `trec wiki ingest`. |
| FR7 | Ingests are serialized by a wiki-level lock; a second ingest waits (back-to-back meetings) instead of failing; a stale lock from a dead process is removed. |
| FR8 | `trec wiki lint` reports broken wikilinks, orphan pages, invalid frontmatter, pages whose sources point to missing meetings, analyzed meetings not yet ingested, failed ingests and rejected edits; exit 1 when anything is wrong. |
| FR9 | `trec wiki rebuild [--yes]` recreates the wiki from every analyzed meeting after a schema change: the current wiki is moved aside as a backup, the ingest records are cleared and every meeting is ingested again, oldest first. |
| FR10 | Privacy: the wiki lives under the data folder (git-ignored) or a folder the user configures; publishing is refused inside a Git work tree that would version it; the wiki's own Git history has no remote; the model receives only the analysis, the transcript and wiki pages, through the same provider as the analysis. |
| FR11 | Visibility: `trec status` shows the number of pages and of meetings pending ingest; `trec doctor` shows the folder, whether it is writable and ignored by Git, whether its `CLAUDE.md` matches `prompts/wiki_schema.md`, and whether the Git history is available. |
| FR12 | Evaluation: a repeatable harness compares the wiki with the minutes-in-context baseline on a synthetic corpus and on the user's questions about real meetings, with the metrics and decision rule of [evaluation.md](./evaluation.md). Automatic ingest is enabled only when the criteria in §7 are met. |

## 6. Non-functional requirements

- Two model calls per ingest (select pages, then write them); each call logged in `llm_usage.jsonl` like the others.
- Ingest runs in the background after the analysis and never delays the detection or recording of the next call.
- No new runtime dependency: frontmatter values are written as JSON scalars and arrays (valid YAML, parsed with the standard library); Git is used through the `git` binary, optionally.
- Platform-neutral Python; on Windows it is expected to work but, like the rest of the Windows port, has not run on real hardware.
- Repository conventions: English code and documents, Brazilian Portuguese wiki content (it is a user document built from LLM content), all strings in `messages.py` / `constants.py`, hexagonal layering, `pytest` and `mypy` clean.

## 7. Success criteria

Gates, in order; each one is a go/no-go for the next.

| Gate | Criterion |
|---|---|
| G1 Spike (task 1) | A manual LLM wiki over the 13 existing meetings produces person and project pages the user finds correct and useful on inspection, and the user writes the first ten real questions with their answers. If the pages are not useful, the feature stops here. |
| G2 Synthetic evaluation (task 7) | On the synthetic corpus, over 3 runs per question: the wiki condition passes at least 80% of the "current state after a change" and "aggregation" questions on every run, is never below the minutes baseline in any category, and produces zero fabricated facts (no `must_not_include` hit) across all runs. |
| G3 Real evaluation (task 8) | Run once at least 15 work meetings are recorded (the spike found only 3 so far). On the user's 20 to 30 questions about real meetings, the wiki is at least as good as the baseline overall and better on synthesis, current-state and aggregation questions, judged by the user's answer key and a judge calibrated on the user's labels. A sample of 30 claims from the pages has at least 95% supported by the transcript at the cited timestamp. |
| G4 Operations (task 8) | The backfill of every real meeting completes; a second `trec wiki ingest` writes nothing; a forced failure leaves the meeting `analyzed` and the plan unchanged; `trec wiki lint` is clean; `pytest` and `mypy` are green; nothing under the wiki is tracked by Git. |

When G2 or G3 fails, the outcome is still useful: the harness stays, the wiki keeps growing passively if the user wants (ingest by hand), and the comparison is rerun when the volume justifies it. The decision is recorded in `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10.

## 8. Decisions taken and open questions

Decisions (defaults the user can overturn before approval):

1. **Build it in the project** rather than integrate `nashsu/llm_wiki`: the same `StructuredTransport` (API or Claude Code subscription), validation and traceability in code, no second LLM configuration, no desktop app that must be open for a headless daemon, no generic text ingest that ignores the structured analysis.
2. **The wiki lives in `<data_dir>/wiki`** by default (git-ignored with the rest of the data); `[wiki] dir` can point at an Obsidian vault instead.
3. **The transcript is sent on ingest** (`[wiki] send_transcript = true`) so pages can quote timestamps and the fidelity check has something to verify; `false` sends the analysis only (cheaper).
4. **Local Git history on by default** (`[wiki] git = true`, no remote ever): one commit per ingest gives a diff of what each meeting changed, which the evaluation and the schema tuning rely on.
5. **Automatic ingest off until G3** (`[wiki] enabled = false` in the repository's `config.toml`); `trec wiki ingest` works regardless, like `trec publish` with `publish = false`.
6. **Page content in Brazilian Portuguese**, frontmatter keys and the schema file in English.
7. **Three entity folders** (`people`, `projects`, `topics`) plus `overview.md`; decisions live inside project and topic pages, not in pages of their own.

Open questions for the user:

- Should the wiki folder be the Obsidian vault the PRD already mentions as a future integration, or a plain folder under `data/` for now?
- Is one notification per failed ingest acceptable, or should wiki failures stay in the log only?
- Does the user want `trec wiki rebuild` to also re-run the analysis (no: it reuses `analysis.json`; confirm)?

## 9. Alternatives considered

- **`nashsu/llm_wiki`** (Tauri desktop app, GPL-3, local HTTP API and MCP server): good two-step ingest and graph, but no ingest endpoint (file watcher plus rescan), a separate LLM configuration with its own billing, the app must be running, and it ingests raw text generically. Ideas borrowed: the two-step ingest, `sources[]` in every page's frontmatter, an `overview.md`, a hash to skip unchanged sources.
- **Let Claude Code edit the wiki with its own tools** during ingest: simpler prompt, but no validation in code, no traceability guarantees, and the `api` provider could not do it. Rejected for ingest; it is exactly how the user *queries* the wiki.
- **RAG with embeddings**: solves retrieval, not synthesis; nothing accumulates. Possibly a later addition for search over hundreds of pages.
- **Do nothing and keep pasting minutes**: this is the baseline the evaluation compares against, and the fallback if the wiki does not win.

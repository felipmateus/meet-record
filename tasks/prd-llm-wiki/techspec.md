# Tech spec: LLM wiki of meetings

> **Status:** draft for approval · **Date:** 2026-10-10 · **Slug:** `llm-wiki`
> **Requirements:** [prd.md](./prd.md) (FR1–FR12) · **Evaluation:** [evaluation.md](./evaluation.md) · **Conventions:** [AGENTS.md](../../AGENTS.md)
> **Starting point:** `main` after the story publishing wave (8c)

## 1. Summary

Add an `IngestMeetingIntoWiki` use case that, for one analyzed meeting, asks the model in two calls which wiki pages to read and then what to write, validates the result in code and writes it into a Markdown wiki under the data folder. Three new ports: `WikiWriter` (the model, over the shared `StructuredTransport`), `WikiStore` (the files) and `WikiHistory` (optional local Git). The pipeline runs the ingest as a post-step after the analysis without touching the meeting's state; `trec wiki ingest|lint|rebuild` drive it by hand. Code owns everything structural: the meeting page, `index.md`, `log.md`, frontmatter `sources`, the lock and the validation; the model owns the prose of person, project, topic and overview pages.

## 2. Architecture

```
analysis.json ──▶ Pipeline.process() ──▶ IngestMeetingIntoWiki ──▶ WikiWriter.plan()     (call 1: which pages to read / create)
transcript.txt       (post-step)              │                 ──▶ WikiWriter.compose()  (call 2: full content of the pages)
trec wiki ingest ─────────────────────────────┤  validate_edits() (domain)
                                              ├─▶ WikiStore: meeting page, entity pages, index.md, log.md   (<data_dir>/wiki)
                                              ├─▶ WikiHistory.commit()                                      (git, fail-soft)
                                              └─▶ MeetingRepository: wiki.json | wiki_error.txt             (meeting folder)
```

| Layer | New or changed |
|---|---|
| domain | `domain/wiki.py`: `PageType`, `PageRef`, `PageMeta`, `PageEdit`, `IngestPlan`, `WikiSource`, `PageWrite`, `RejectedEdit`, `WikiIngest`, the wiki layout, slug and edit validation, frontmatter and index/log rendering, lint rules; `WikiError`; `status.py` gains `WIKI`, `WIKI_ERROR` (not part of the status) |
| application | ports `WikiWriter`, `WikiStore`, `WikiHistory`; `MeetingRepository.save_wiki_ingest / load_wiki_ingest / mark_wiki_failed / clear_wiki_failed`; use case `IngestMeetingIntoWiki`, helpers `wiki_pending`, `RebuildWiki`; `Pipeline` post-step and resume |
| adapters | `wiki_fs.FsWikiStore`, `wiki_git.GitWikiHistory`, `wiki_claude.ClaudeWikiWriter`; `git_ignore.py` extracted from `publisher_backlogmd` and shared; `codec` (wiki.json); `repository_fs` (new methods); `fake_claude_cli.py` answers the two wiki schemas |
| prompts | `prompts/wiki_schema.md` (the wiki's rules, also dropped into the wiki as `CLAUDE.md`), `prompts/wiki_ingest_system.md` (the two-call contract) |
| config / container / CLI | `[wiki] enabled, dir, send_transcript, git`; `Container.wiki_store / wiki_writer / wiki_history`, `ingest_meeting()`, `pipeline()` wiring; `trec wiki ingest|lint|rebuild`; `doctor` and `status` lines; `Notify.WIKI_FAILED` |

Import direction `domain ← application ← adapters/container` is unchanged. `wiki_claude` sits in the LLM stack (uses `llm_schema`, `llm_transport`, `codec`) like `stories_claude`.

**Why the model does not touch files.** Both providers go through `StructuredTransport.complete()` (text in, schema-validated JSON out, no tools), so the same adapter works with the API and with Claude Code, every edit passes `validate_edits()` before it reaches the disk, and traceability (`sources`, the meeting page, the log) cannot be forgotten by the model. Querying is the opposite: the user runs Claude Code *inside* the wiki with its tools, guided by `CLAUDE.md` (§8).

## 3. Domain (`domain/wiki.py`, `domain/status.py`, `domain/errors.py`)

The wiki layout is a domain rule (validation depends on it), so, like the meeting file names in `status.py`, it lives in the domain:

```python
class PageType(StrEnum): PERSON = "person"; PROJECT = "project"; TOPIC = "topic"; MEETING = "meeting"; OVERVIEW = "overview"
FOLDERS = {PERSON: "people", PROJECT: "projects", TOPIC: "topics", MEETING: "meetings"}   # OVERVIEW: the root, slug "overview"
INDEX, LOG, SCHEMA_FILE, WIKI_LOCK = "index.md", "log.md", "CLAUDE.md", ".lock"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"); MAX_SLUG = 60
```

- `PageRef(type, slug)` (frozen) with `path` (`people/joao-silva.md`, `overview.md`, `meetings/<meeting id>.md`; meeting slugs are meeting ids and are the one exception to `SLUG`).
- `PageMeta(ref, title, summary, aliases, sources, created, updated)`: what the frontmatter holds; `pages()` returns these and `render_index()` consumes them.
- `PageEdit(ref, title, summary, aliases, body, change)`: what the model returns for one page (`change`: one line for the log). `IngestPlan(read, create, notes)`: the output of call 1.
- `WikiSource(meeting, analysis, transcript_text: str | None, previous: WikiIngest | None)`: everything the writer receives; `previous` is set on `--force` so the model reconciles instead of duplicating.
- `PageWrite(ref, action: created|updated, change)`, `RejectedEdit(ref | None, reason)`, `WikiIngest(meeting_id, ingested_at, schema_version, analysis_hash, pages, rejected)`: the record saved as `wiki.json`.
- `validate_edits(edits, existing: set[PageRef], max_pages, max_chars) -> tuple[list[PageEdit], list[RejectedEdit]]`: rejects `MEETING` type (code-only), invalid or too long slugs, empty title or body, bodies over `max_chars`, a second edit of the same ref, and everything past `max_pages`; strips frontmatter the model may have written in `body`.
- `render_frontmatter(meta)` / `parse_frontmatter(text) -> tuple[dict, str]`: `key: <JSON scalar or array>` lines between `---` fences. JSON scalars and arrays are valid YAML (Obsidian and Dataview read them) and parse with `json.loads`, so no YAML dependency. `parse_frontmatter` raises `WikiError` on a malformed file; lint reports it.
- `render_index(metas, labels)`: sections per type in the order people, projects, topics, meetings; one line per page: `- [[path|title]] — summary (fontes: N, atualizado YYYY-MM-DD)`; overview linked at the top. `render_log_entry(when, meeting, title, writes, rejected, labels)`: `## [YYYY-MM-DD HH:MM] ingest | <title> (<id>)` plus one bullet per page and per rejection. Labels come from `messages.WikiDoc` (Portuguese: a user document).
- `wikilinks(body) -> list[str]` and `lint(metas, bodies, meeting_ids) -> list[LintProblem]`: broken links, orphans (no inbound link other than the index), sources pointing to unknown meetings, duplicate titles across pages.
- `status.py`: `WIKI = "wiki.json"`, `WIKI_ERROR = "wiki_error.txt"`; `derive_status` ignores both (a wiki failure must not remove the meeting from the daily plan, which counts `analyzed` meetings).
- `errors.py`: `WikiError(TeamsRecorderError)`.

## 4. Application (`application/ports.py`, `application/use_cases/wiki.py`, `application/pipeline.py`)

### 4.1 Ports

```python
class WikiWriter(Protocol):
    def plan(self, source: WikiSource, index: str) -> IngestPlan: ...
    def compose(self, source: WikiSource, index: str, pages: dict[PageRef, str], plan: IngestPlan) -> list[PageEdit]: ...

class WikiStore(Protocol):
    def initialize(self, schema: str) -> None: ...                   # folders, empty index/log, CLAUDE.md (rewritten when it differs)
    def lock(self, timeout: float) -> AbstractContextManager[None]: ...  # waits; removes a stale lock; WikiError on timeout
    def pages(self) -> list[PageMeta]: ...                           # from the frontmatter of every page
    def exists(self, ref: PageRef) -> bool: ...
    def read(self, ref: PageRef) -> str: ...
    def write(self, ref: PageRef, text: str) -> None: ...            # atomic
    def write_index(self, text: str) -> None: ...
    def append_log(self, text: str) -> None: ...
    def backup(self) -> Path: ...                                    # moves the wiki aside (rebuild); returns the backup path
    def problems(self) -> list[str]: ...                             # empty = ready; shown by `trec doctor`

class WikiHistory(Protocol):
    def commit(self, message: str) -> bool: ...                      # False when nothing changed; WikiError on a git failure
    def problems(self) -> list[str]: ...
```

`MeetingRepository` gains `save_wiki_ingest(meeting_id, record)`, `load_wiki_ingest(meeting_id) -> WikiIngest | None`, `mark_wiki_failed(meeting_id, message)`, `clear_wiki_failed(meeting_id)`; `files()` already exposes `wiki.json` / `wiki_error.txt`.

### 4.2 `IngestMeetingIntoWiki(repo, store, writer, minutes, clock, schema, send_transcript, history=None, lock_timeout, max_pages, max_chars, max_transcript_chars)`

`execute(meeting_id, force=False) -> IngestOutcome` (`record: WikiIngest`, `skipped: bool`):

1. `existing = repo.load_wiki_ingest(meeting_id)`; when set and not `force` → `IngestOutcome(existing, skipped=True)` (nothing else happens).
2. Load meta and analysis (`RepositoryError` if the meeting is not analyzed); transcript text when `send_transcript` (missing transcript = `None`, never an error; truncated at `max_transcript_chars` with `Prompt.TRUNCATED`).
3. `with store.lock(lock_timeout)`: `store.initialize(schema)`; `repo.clear_wiki_failed(meeting_id)`; `index = render_index(store.pages())`.
4. `plan = writer.plan(source, index)`; refs in `plan.read` are validated (type, slug) and the valid ones that exist are read: `pages = {ref: store.read(ref)}` (at most `max_pages`).
5. `edits = writer.compose(source, index, pages, plan)`; `accepted, rejected = validate_edits(edits, existing refs, max_pages, max_chars)`.
6. Write the meeting page `meetings/<id>.md`: frontmatter (`title`, `type: meeting`, `summary`, `sources: [<id>]`, `date`, `participants`) and the minutes rendered by `MinutesRenderer`, plus a "Páginas relacionadas" section linking every accepted page. Then each accepted page: frontmatter from the edit with `sources` = previous sources ∪ {meeting id}, `created` kept from the previous frontmatter or today, `updated` today (`clock`), and the body. `write_index(render_index(store.pages()))`; `append_log(render_log_entry(...))`.
7. `history.commit(...)` when `history` is set: a `WikiError` here is logged and ignored (the wiki is already written).
8. `record = WikiIngest(meeting_id, clock.now(), schema_version=sha256(schema)[:12], analysis_hash=sha256 of the analysis JSON[:12], pages, rejected)`; `repo.save_wiki_ingest(meeting_id, record)`.

Any `TeamsRecorderError` in steps 3–6 → `repo.mark_wiki_failed(meeting_id, message)` and re-raise. The use case never notifies: the pipeline and the CLI do (like publishing). The lock is held through the model calls on purpose: two ingests interleaving their reads and writes would corrupt pages; back-to-back meetings simply wait (the timeout, 15 min, is longer than one ingest).

`wiki_pending(repo) -> list[str]`: ids of meetings whose status is `analyzed` and whose folder has no `wiki.json`, oldest first (`list_meetings()` order).

`RebuildWiki(repo, store, ingest)`: `store.backup()` (returns the path for the CLI to print), delete `wiki.json` and `wiki_error.txt` from every meeting folder (`repo.delete_file`), then `ingest.execute()` for every analyzed meeting oldest first, collecting failures (same report shape as the CLI loop).

### 4.3 `Pipeline`

- New field `ingest: IngestMeetingIntoWiki | None = None`. In `process()`, when the loop ends with `ANALYZED`, `ingest` is set and `WIKI` is not among the files: run it under `try/except Exception`; on failure log `Log.STEP_FAILED` with `Step.WIKI`, notify `Notify.WIKI_FAILED` and still return `MeetingStatus.ANALYZED` (FR6). `Step.WIKI` is never written to `error.txt`.
- `resume_pending()`: a meeting in `ANALYZED` without `wiki.json` is processed too when `ingest` is set (the post-step runs; nothing else). Meetings in `FAILED` are not touched, as today.
- `Container.pipeline()` passes `ingest_meeting()` only when `settings.wiki_enabled`; `trec wiki ingest` uses the use case directly, enabled or not.

## 5. Adapters

### 5.1 `wiki_fs.FsWikiStore(root)`

- All file access through `fs_retry.retry_io`; writes are atomic (`<name>.tmp` + `os.replace`, as in `repository_fs`); `initialize()` creates the folders, an empty `index.md`/`log.md` when missing and writes `CLAUDE.md` whenever its content differs from the schema (the repository file is the source of truth; the README says to edit `prompts/wiki_schema.md`, not the copy).
- `pages()` walks the four folders and `overview.md`, parses each frontmatter (`parse_frontmatter`) and skips `.tmp` files; a malformed page raises `WikiError` naming the file (lint reports it; ingest fails loudly rather than rebuilding a broken index).
- `lock(timeout)`: `.lock` with the PID, polled every 0.5 s until free; a lock whose PID is not alive (`os.kill(pid, 0)`, Windows: `winproc`) is removed; `WikiError(Err.WIKI_LOCKED)` after `timeout`.
- `backup()` renames `root` to `<root>.bak-<YYYYMMDD-HHMMSS>` next to it and recreates `root`.
- `problems()`: root cannot be created or written; root inside a Git work tree and **not** ignored, or Git unable to answer, through the shared `git_ignore.git_ignore_state` (fails closed, like the board); `CLAUDE.md` differs from the schema (info only: the next ingest refreshes it).

### 5.2 `wiki_git.GitWikiHistory(root, git_bin, runner)`

- `commit(message)`: `git init -q` when `root/.git` is missing (then `git config user.name/user.email` locally to the app name, so a Mac without a global identity still commits); `git add -A`; `git commit -q -m <message>`; returns `False` when `git status --porcelain` is empty. Arguments as a list, `cwd=root`, `Wiki.GIT_TIMEOUT`, `NO_WINDOW`. Failures → `WikiError` with the stderr tail.
- `problems()`: `git` missing (info: history off), a configured remote (`git remote` non-empty → problem: the wiki must never leave the Mac). The adapter never adds a remote, pushes or fetches.
- Built only when `[wiki] git = true` and `git` is found; otherwise `wiki_history = None` and `doctor` says history is off.

### 5.3 `wiki_claude.ClaudeWikiWriter(transport, schema_path, prompt_path, user_name, max_pages)`

- `_system()` = `load_prompt(prompt_path)` (`prompts/wiki_ingest_system.md`) + `Prompt.WIKI_SCHEMA_HEADER` + the schema re-read on every call (edits apply to the next ingest; missing or empty schema = `AnalysisError`, like the story guide).
- Pydantic outputs, schemas tightened by `strict_schema`: `PageRefOut(type, slug)`; `PlanOut(notes, read: list[PageRefOut], create: list[PageRefOut])`; `PageOut(type, slug, title, summary, aliases, body, change)`; `ComposeOut(pages: list[PageOut])`. Field descriptions in `messages.Prompt` (`FIELD_WIKI_*`).
- `build_plan_message(source, index, user_name)`: user name, meeting header (id, date, weekday, start, duration, title), `Prompt.WIKI_INDEX` + the index, `Prompt.WIKI_ANALYSIS` + `codec.analysis_to_dict` as JSON, `Prompt.WIKI_TRANSCRIPT` + the transcript when present, and on `--force` `Prompt.WIKI_PREVIOUS` listing the pages the previous ingest wrote. `build_compose_message(...)` adds `Prompt.WIKI_PLAN` (the notes and refs of call 1) and `Prompt.WIKI_PAGES` with each page's full text under its path. Both kept in functions so tests can inspect them.
- `plan()` and `compose()` call `transport.complete(...)` with tags `wiki-plan:<id>` / `wiki-compose:<id>` and `extra={"meeting": id}`; `to_edits()` maps `PageOut` → `PageEdit` (type parsed with the enum; an unknown type becomes a rejection in `validate_edits`, not an exception).

### 5.4 Prompts

- `prompts/wiki_schema.md`: purpose of the wiki; the page types and the sections each one has (person: role, projects, open items with the user, history; project: current state, people, decisions with dates, deadlines with history, risks, open questions, history; topic: what it is, current understanding, references; overview: a short map of the wiki); conventions: current value first, `Histórico` with dated entries and `[[meetings/<id>]]` links, `([[meetings/<id>]] HH:MM:SS)` citations, `⚠️ Conflito` for contradictions, Brazilian Portuguese prose, no invented facts; the query workflow (read `index.md`, open pages, answer with citations, say so when the wiki does not know) and the lint workflow, because the same file is the wiki's `CLAUDE.md`. Written in task 1 from the spike and refined in task 8.
- `prompts/wiki_ingest_system.md`: the two-call contract (call 1: discuss the meeting's takeaways in `notes`, list existing pages to read and new pages to create, by type and slug; call 2: return the full content of every page to write, merging new facts into existing text, never dropping content that is still true, moving changed values to the history); slugs are ASCII lowercase with hyphens, Portuguese names transliterated; meeting pages are never written by the model; limits.

### 5.5 Shared code and persistence

- `adapters/outbound/git_ignore.py`: `GitIgnore` and `git_ignore_state(path, git_bin, runner)` moved out of `publisher_backlogmd` (which imports them from there; behavior and tests unchanged). AGENTS.md forbids adapters importing each other's internals, hence the move.
- `codec`: `wiki_ingest_to_dict / from_dict` (ISO datetime, refs as `{type, slug}`); `repository_fs`: the four methods (`wiki.json` atomic; `wiki_error.txt` plain text `wiki: <message>`).
- `tests/fixtures/fake_claude_cli.py` inspects `--json-schema`: a schema with `read`/`create` answers a plan, one with `pages` answers a compose (two pages: one person, one project), so the CLI integration tests run the whole ingest; `FAKE_CLAUDE_MODE=wiki_bad_slug` returns an accented slug to exercise rejection.

## 6. Configuration (`config.py`, `config.toml`, `constants.py`)

```toml
[wiki]
# A knowledge base the model keeps from every analyzed meeting: one Markdown page per person,
# project and topic, with the current state and a dated history, each claim citing its meeting.
# Open the folder in Obsidian, or run `claude` inside it to ask questions (CLAUDE.md there explains).
enabled = false          # ingest right after each analysis (the daemon). `trec wiki ingest` works either way.
dir = ""                 # empty = <data_dir>/wiki; a relative path is resolved against the data dir
send_transcript = true   # the model also receives the transcript (quotes with timestamps); false = analysis only
git = true               # one local Git commit per ingest (history and diffs); never a remote
```

`Settings`: `wiki_enabled`, `wiki_dir: Path`, `wiki_send_transcript`, `wiki_git`; property `wiki_schema_path` (`prompts_dir / Files.WIKI_SCHEMA_PROMPT`). `constants.Wiki`: `ENABLED=False`, `SEND_TRANSCRIPT=True`, `GIT=True`, `MAX_READ_PAGES=15`, `MAX_WRITE_PAGES=20`, `MAX_PAGE_CHARS=20_000`, `MAX_TRANSCRIPT_CHARS=150_000`, `LOCK_TIMEOUT=900.0`, `LOCK_POLL=0.5`, `GIT_TIMEOUT=60.0`, `BACKUP_SUFFIX`. `Files`: `WIKI_DIR="wiki"`, `WIKI_SCHEMA_PROMPT`, `WIKI_INGEST_PROMPT`. `Env.REAL_WIKI="TREC_REAL_WIKI"`. `Step.WIKI`, `Notify.WIKI_FAILED/_BODY`, `Err.WIKI_*`, `Cli.WIKI_*`, `Log.WIKI_*`, `messages.WikiDoc` (index, log and meeting-page labels in Portuguese).

## 7. CLI, doctor and status (`adapters/inbound/cli.py`)

- `wiki_app = typer.Typer(...)`, `app.add_typer(wiki_app, name="wiki")`.
- `trec wiki ingest [id] [--force]`: `_check_llm_prerequisites`; one id → `ok (N pages: C created, U updated, R rejected)` or `skipped (already in the wiki; use --force)`; no id → `wiki_pending()` oldest first, one line per meeting, failures notified and reported, exit 1 if any failed, like `transcribe`/`analyze`. Prints the wiki path at the end.
- `trec wiki lint`: lists every `LintProblem`, plus pending ingests (`wiki_pending`), meetings with `wiki_error.txt` (with the message) and rejected edits found in `wiki.json` files; exit 1 when the list is not empty.
- `trec wiki rebuild [--yes]`: confirms (`Ask.WIKI_REBUILD`, with the number of meetings) unless `--yes`; prints the backup path; then the ingest loop.
- `trec status`: `Wiki: N pages, M meetings pending ingest` whenever the wiki folder exists or `enabled` is true.
- `trec doctor`: `[ok|MISSING|info] wiki: <dir> (N pages; history on|off; CLAUDE.md in sync|stale)` plus one line per store/history problem; a problem fails the doctor only when `enabled = true`, mirroring the destinations check.

## 8. Data

```
<data_dir>/wiki/                     # or [wiki] dir
├── CLAUDE.md                        # copy of prompts/wiki_schema.md (query and lint workflow for Claude Code)
├── index.md                         # generated: every page by type, one line each
├── log.md                           # append-only: one entry per ingest
├── overview.md                      # model-maintained map of the wiki
├── people/<slug>.md  projects/<slug>.md  topics/<slug>.md
├── meetings/<meeting id>.md         # generated from the minutes; links to the pages the ingest touched
├── .lock                            # PID while an ingest runs
└── .git/                            # when [wiki] git = true (no remote)
```

Frontmatter (every value a JSON scalar or array, valid YAML):

```
---
title: "Projeto Aurora"
type: "project"
summary: "Portal do cliente; entrega da fase 2 em 2026-10-22"
aliases: ["Aurora", "portal"]
sources: ["2026-10-05_12-29-37", "2026-10-09_09-30-52"]
created: "2026-10-05"
updated: "2026-10-09"
---
```

`wiki.json` (meeting folder): `{"meeting_id", "ingested_at", "schema_version", "analysis_hash", "pages": [{"type", "slug", "action", "change"}], "rejected": [{"type", "slug", "reason"}]}`. `wiki_error.txt`: `wiki: <message>`, removed at the next attempt.

## 9. Spike (task 1): what it must settle

The spike is a manual LLM wiki built with Claude Code over the 13 real meetings, with a hand-written `CLAUDE.md`. It answers, and the answers are recorded here before task 2 starts:

1. Which page types and sections make the pages useful (the first `prompts/wiki_schema.md`).
2. Whether the analysis JSON alone is enough for good pages or the transcript is needed (the `send_transcript` default).
3. How many pages one meeting touches (sizing `MAX_READ_PAGES` / `MAX_WRITE_PAGES`) and how large pages get (`MAX_PAGE_CHARS`).
4. How the model handles a fact that changed between two real meetings, if the data has one, and how the schema should instruct it.
5. The user's first ten questions with answers for the real-data evaluation (`data/wiki-eval/questions.toml`).

Results: _to be filled by task 1_.

## 10. Failure modes

| Situation | Behavior |
|---|---|
| Meeting not analyzed | `RepositoryError`; `trec wiki ingest <id>` says so; the pending loop never selects it |
| Already ingested | skipped unless `--force`; nothing written |
| Model call fails (refusal, truncation, schema, auth, timeout) | `AnalysisError` → `wiki_error.txt`, notification, meeting stays `analyzed`; the lock is released by the context manager |
| Every edit rejected (bad slugs, wrong types) | the ingest still succeeds: meeting page, index and log written, rejections in `wiki.json` and the log, CLI shows `R rejected`; lint lists them |
| Malformed page in the wiki (user edit) | `WikiError` naming the file before any write; lint reports it |
| Lock held by a live process | waits up to `LOCK_TIMEOUT`, then `WikiError` → retried by `trec wiki ingest` |
| Lock from a dead process | removed and taken |
| Git failure (not installed, commit error) | logged, ingest succeeds; doctor shows the problem |
| Wiki folder inside a tracked Git tree | `problems()` non-empty; ingest refuses before any write (`Err.WIKI_NOT_IGNORED`) |
| Schema file missing or empty | `AnalysisError` with the path, like the story guide |
| Daemon killed mid-ingest | pages written so far stay (each write atomic), `wiki.json` missing → the meeting is pending again; `--force` semantics apply on the retry because the index already lists its pages (the retry sees them and merges) |

## 11. Security and privacy

- The wiki is under `data/` (ignored) by default; a configured folder is refused when Git would version it (fail-closed check shared with the board).
- The wiki's Git repository has no remote; the adapter never runs network commands; a remote found later is a doctor problem.
- Model calls use the same transport as the analysis (no tools on either provider); only the analysis, the transcript and wiki pages are sent.
- Backups from `rebuild` stay next to the wiki (same ignored folder); the CLI prints their path so the user can delete them.
- Nothing from the real wiki is used in tests; the evaluation corpus is fictional.

## 12. Testing strategy

| Component | Unit | Integration | E2E / opt-in |
|---|---|---|---|
| Domain (`slug`, `page_path`, `validate_edits`, frontmatter round trip and JSON escaping, `render_index`, `render_log_entry`, `wikilinks`, `lint`) | `test_wiki_domain.py` | — | — |
| Codec / repository (`wiki.json` round trip, `wiki_error.txt`, status unaffected) | `test_status.py` | `test_repository_fs.py` | — |
| `IngestMeetingIntoWiki` (skip, force, lock held through the calls, meeting page, sources merge, created/updated, rejections recorded, failure writes `wiki_error.txt`, git failure ignored, transcript off/missing/truncated), `wiki_pending`, `RebuildWiki` | `test_wiki_use_cases.py` on `FakeWikiStore`, `FakeWikiWriter`, `FakeWikiHistory` | — | — |
| `Pipeline` (post-step after analysis, failure keeps `analyzed` and notifies, no post-step when `wiki.json` exists, resume picks pending ingests) | `test_pipeline.py` | — | — |
| `FsWikiStore` (initialize, CLAUDE.md refresh, pages parsing, `.tmp` ignored, malformed page, blocking lock and stale lock, backup, problems incl. git-ignore) | — | `test_wiki_fs.py` (tmp_path) | — |
| `GitWikiHistory` (init with local identity, commit, nothing to commit, remote → problem, git missing) | `test_wiki_git.py` with a scripted runner | `test_wiki_git_real.py` with the real `git` on tmp_path | — |
| `ClaudeWikiWriter` (both messages, schemas, `to_edits`, unknown type, limits) | `test_wiki_claude.py` | — | `TREC_REAL_CLAUDE_CLI=1` on one fixture meeting |
| Config (`[wiki]` keys, dir resolution against the data dir) / container (wiring, history None when git off) | `test_config.py`, `test_container_platforms.py` | — | — |
| CLI (`wiki ingest` single/pending/force with the fake `claude`, rejected slug, `lint` exit codes, `rebuild` confirmation and backup, doctor and status lines) | — | `test_cli.py` | — |
| Evaluation harness (corpus loads, checks evaluate, report renders) | `test_wiki_eval.py` on canned answers | — | `TREC_REAL_WIKI=1 pytest -m slow tests/integration/test_wiki_eval_real.py` |
| Whole flow on real data | — | — | task 8 with the user (backfill, questions, fidelity sample) |

`test_no_hardcoded_strings.py` and `mypy` stay clean.

## 13. Implementation order

1. Spike and first schema (§9), go/no-go.
2. Domain, status names, codec, repository methods, configuration.
3. `FsWikiStore`, `GitWikiHistory`, the `git_ignore` extraction.
4. Ports, `IngestMeetingIntoWiki`, `wiki_pending`, `RebuildWiki`, `Pipeline` post-step, fakes.
5. `ClaudeWikiWriter` and the ingest prompt.
6. Container, `trec wiki`, doctor, status, notifications.
7. Evaluation harness and the synthetic run (G2).
8. Real-data validation (G3, G4), schema tuning, `enabled = true` on the user's OK, documentation.

## 14. Out of scope

Feedback loops into analysis/stories/plan; `trec wiki ask`; LLM-based lint; embeddings; sources other than meetings; the nashsu app; multi-user.

## 15. References

- Existing code to mirror: `application/use_cases/planning.py` (`DraftUserStories`, `PublishUserStories`), `adapters/outbound/stories_claude.py` (guide appended to the system prompt, deterministic validation of the model's output), `publisher_backlogmd.py` (`problems()`, Git-ignore check, scripted CLI tests), `repository_fs.py` (atomic writes, lock), `pipeline.py`, `tests/fixtures/fake_claude_cli.py`.
- The pattern: Karpathy's gist (three layers, ingest/query/lint, `index.md` and `log.md`, Obsidian as the viewer); `nashsu/llm_wiki` (two-step ingest, `sources[]`, `overview.md`, source hashing).
- Evaluation method: `ai-evals-course/evals-skills` (error discovery, code evals, binary judge with critique, judge validation against human labels); Anthropic's "Demystifying evals for AI agents" (pass@k / pass^k).

# Tech spec: Story publishing to a Markdown board (Backlog.md)

> **Status:** draft for approval · **Date:** 2026-10-10 · **Slug:** `story-publishing`
> **Requirements:** [prd.md](./prd.md) (FR1–FR10) · **Conventions:** [AGENTS.md](../../AGENTS.md)
> **Starting point:** branch `feat/story-drafts` (story drafts, `trec stories`, `[stories]` config)

## 1. Summary

Add a `StoryPublisher` port and a `PublishUserStories` use case that send each drafted story to every configured destination, record where it went, and never send it twice. The first adapter, `BacklogMdPublisher`, creates a task in a local Backlog.md project through the `backlog` CLI, in the **Triagem** status. Drafting gains a duplicate check against recent stories and refuses to redraft a published day. Destinations are chosen by `[stories] destinations` through a registry in the composition root.

## 2. Architecture

```
trec plan / trec stories ──▶ DraftUserStories ──▶ PublishUserStories ──▶ [StoryPublisher, …]
         trec publish ─────────────────────────────┘          │                    │
                                                              ▼                    ▼
                                         plans/<day>.stories.json        BacklogMdPublisher
                                         (publications recorded)         └▶ `backlog task create … -s Triagem`
```

Layer placement (import direction `domain ← application ← adapters/container` is unchanged):

| Layer | New or changed |
|---|---|
| domain | `Publication`; `UserStory.publications`; `SkippedAction.duplicate_of`; `PublishError` |
| application | port `StoryPublisher`; `StoryWriter.draft(…, existing)`; repository method `recent_story_drafts`; use case `PublishUserStories`; `DraftUserStories` gains the redraft lock and passes existing stories |
| adapters | `publisher_backlogmd.BacklogMdPublisher`; `stories_claude` (duplicates); `stories_markdown` (publications, duplicates); `codec` and `repository_fs` (new fields, recent drafts) |
| config / container / CLI | `[stories] publish`, `destinations`, `dedup_days`, `[stories.backlog_md]`; publisher registry; `trec publish`; `doctor` and `status` lines |

**The switch.** The publishers are strategies selected by configuration in `container.py`, the same way `llm.provider` selects a transport (`build_transport`) and `audio.mic_backend` selects the microphone. A dict `StoryDestination → builder(settings)` builds one publisher per configured destination. Fan-out to several destinations happens in `PublishUserStories`, not in a composite adapter, because idempotency is tracked per destination and is an application rule.

## 3. Domain (`domain/models.py`, `domain/errors.py`)

- `Publication` (frozen dataclass): `destination: str`, `ref: str` (the destination's id for the item, e.g. a Backlog.md task id), `published_at: datetime`.
- `UserStory.publications: list[Publication]` (default empty) and `UserStory.publication(destination) -> Publication | None`.
- `StoryDrafts.has_publications` (property): true when any story was published anywhere. Used for the redraft lock (FR5).
- `SkippedAction.duplicate_of: str | None = None`: id of an existing story that already covers the action (FR6, FR10).
- `PublishError(TeamsRecorderError)`: a destination could not take a story.

The JSON written before this change (no `publications`, no `duplicate_of`) must still load, with empty defaults.

## 4. Application (`application/ports.py`, `application/use_cases/planning.py`)

### 4.1 Ports

```python
class StoryPublisher(Protocol):
    destination: StoryDestination
    def publish(self, story: UserStory, day: date) -> str: ...   # returns the destination's ref; raises PublishError
    def problems(self) -> list[str]: ...                         # empty = ready; shown by `trec doctor`

class StoryWriter(Protocol):
    def draft(self, day: date, actions: list[Action], analyses: list[Analysis], existing: list[UserStory]) -> StoryDrafts: ...
```

`MeetingRepository` gains `recent_story_drafts(before: date, days: int) -> list[StoryDrafts]` (drafts of the days in `[before - days, before)`, oldest first).

### 4.2 `PublishUserStories(repo, publishers, renderer, notifier, clock)`

`execute(day, only: list[int] | None = None) -> PublishReport`

1. Load the day's drafts; none → `RepositoryError(Err.STORIES_MISSING)`.
2. Select the stories: all, or the 1-based numbers in `only` (the numbers of the drafts document); an out-of-range number → error before publishing anything.
3. For each selected story, for each publisher: skip when `story.publication(destination)` exists; otherwise call `publish`, append a `Publication(destination, ref, clock.now())` and **save the drafts (JSON and re-rendered Markdown) immediately**, so an interrupted run never loses a ref (FR3, reliability).
4. A `PublishError` (or any `TeamsRecorderError`) is collected in the report and the loop goes on (FR4).
5. Notify once: published count, or the failure count.

`PublishReport`: `published: list[(story, destination, ref)]`, `already: int`, `failures: list[(story, destination, error)]`.

### 4.3 `DraftUserStories` changes

- **Redraft lock (FR5):** if drafts already exist for the day and `has_publications` → `RepositoryError(Err.STORIES_ALREADY_PUBLISHED)` before calling the writer.
- **Existing stories (FR6):** pass `[s for d in repo.recent_story_drafts(day, dedup_days) for s in d.stories]` to the writer. `dedup_days` comes from settings through the container.
- The renderer is also needed by `PublishUserStories` (step 3); both use cases receive it.

## 5. Adapters

### 5.1 `publisher_backlogmd.BacklogMdPublisher`

Constructor: `binary` (from `find_tool(Bin.BACKLOG, …)`), `project_dir: Path`, `status: str`, `labels: tuple[str, …]`, injected runner (default: `process_control`, so tests can fake it and Windows gets `NO_WINDOW`).

- **`command(story, day) -> list[str]`** (kept in one method so tests can inspect it, as AGENTS.md asks):
  `backlog task create <title> --desc <body> -s <status> -l <labels,day> [--priority high|medium|low] [--ac <criterion> …] --plain`, run with `cwd=project_dir`, arguments as a list (no shell, so multi-line `--desc` is safe).
- **Body (`--desc`):** story sentence; the guide's other sections (`details`); open questions; a traceability block (plan day, source meetings, source action ids, path of the drafts file). Labels for the block come from `messages.StoryDoc` (Portuguese, a user document).
- **Acceptance criteria:** one `--ac` per criterion (the CLI documents repeated `--ac` on `task edit` and a comma-separated form on `create`). Criteria contain commas ("Dado …, quando …, então …"), so the behavior of `--ac` with commas on `create` must be confirmed in the spike (§9); fallback: create without `--ac` and add each criterion with `backlog task edit <id> --ac …`.
- **Priority:** `Priority.HIGH/MEDIUM/LOW` → `high/medium/low` (Backlog.md default priorities are High, Medium, Low); none → flag omitted.
- **Ref:** parsed from the `--plain` output with a regex in `constants.Parse.BACKLOG_TASK_ID`. The output format is not documented (examples show `task-1`, `BACK-7`, `7`); the spike fixes the regex. No id found → `PublishError` that includes the output tail.
- **Errors:** missing binary, non-zero exit, timeout (`Proc.BACKLOG_TIMEOUT`) → `PublishError` with a message that says what to do (install command, `backlog init`, add the status).
- **`problems()`:** binary not found (with `npm i -g backlog.md` / `brew install backlog-md`); `project_dir` not set or missing; not a Backlog.md project (no `backlog/config.yml`, `.backlog/config.yml` or `backlog.config.yml`); `status` not in the config's `statuses` line (Backlog.md cannot change `statuses` with `backlog config set`: the message tells the user to edit the file); `autoCommit` or `remoteOperations` enabled in the config; and, when the backlog folder is inside a Git work tree, the folder is **not** ignored (`git check-ignore -q <backlog folder>` fails) — the message says to add it to `.gitignore`. The config checks are plain text searches: no YAML dependency.
- **Guard in `publish`:** the Git-ignore check also runs before every `publish` call (cheap), so a story is never written where it could be committed.
- **Never** edits, moves, archives or deletes tasks (FR8).

### 5.2 `stories_claude.ClaudeStoryWriter` (duplicates)

- User message gains a section "Existing stories (do not duplicate)": id, title and story sentence of each existing story (`Prompt.STORIES_EXISTING`).
- `SkippedOut` gains `duplicate_of: str | None`; kept only when it is the id of an existing story (invented ids dropped, like action ids).
- `prompts/stories_system.md` gains one rule: an action already covered by an existing story goes to `skipped` with `duplicate_of`, never into a new story.

### 5.3 `codec`, `repository_fs`, `stories_markdown`

- `codec`: `publications` (destination, ref, ISO `published_at`) and `duplicate_of`, with defaults for old files.
- `repository_fs.recent_story_drafts`: reads `plans/????-??-??.stories.json` in the window (`Files.STORIES_GLOB`).
- `stories_markdown`: under each story, a line per publication (`StoryDoc.PUBLISHED`: destination and ref); skipped lines show the covering story when `duplicate_of` is set (`StoryDoc.DUPLICATE_OF`).

## 6. Configuration (`config.py`, `config.toml`, `constants.py`)

```toml
[stories]
enabled = true
guide = "prompts/user_story_guide.md"
publish = true                  # publish right after drafting
destinations = ["backlog-md"]   # any of: backlog-md (github and azure later)
dedup_days = 30                 # existing stories the model sees when drafting

[stories.backlog_md]
project_dir = "."               # the Backlog.md project root; "." = this project, files in ./backlog (git-ignored)
status = "Triagem"              # must be one of its statuses (columns)
labels = ["teams-recorder"]
```

**Location (user decision, 2026-10-10):** the Backlog.md project lives in this repository's folder. Its files (`backlog/` and, if Backlog.md creates it, `backlog.config.yml`) are listed in `.gitignore`, so stories are never versioned. `data/backlog` (already ignored with `data/`) was considered; a top-level `backlog/` was chosen because it is where Backlog.md and its MCP server look by default.

**One-time setup** (documented in the README, checked by `trec doctor`): add the entries to `.gitignore`; run `backlog init --no-git` at the project root without agent instructions (so Backlog.md does not edit `AGENTS.md` / `CLAUDE.md`; exact flag confirmed in the spike); add `Triagem` to `statuses` in the generated config. No-git mode keeps `autoCommit`, `remoteOperations` and `checkActiveBranches` off, which matters inside this Git repository.

- `constants.StoryDestination(StrEnum)`: `BACKLOG_MD = "backlog-md"`. `Bin.BACKLOG = "backlog"`. `Stories.PUBLISH = False`, `Stories.DEDUP_DAYS = 30`, `Stories.BACKLOG_STATUS = "Triagem"`, `Stories.BACKLOG_LABELS`.
- `Settings`: `stories_publish`, `story_destinations: tuple[StoryDestination, …]`, `story_dedup_days`, `backlog_project_dir: Path | None` (relative to the project dir, `~` expanded, like `story_guide`), `backlog_status`, `backlog_labels`. An unknown destination → `ValueError(Err.INVALID_DESTINATION)` through `_parse_enum`.
- Defaults keep current behavior: without the new keys nothing is published.

## 7. Composition root (`container.py`)

- `_PUBLISHERS: dict[StoryDestination, Callable[[Settings], StoryPublisher]]` and `build_story_publishers(settings) -> list[StoryPublisher]` (configured order).
- `Container.story_publishers: list[StoryPublisher]`; `Container.publish_user_stories()`; `draft_user_stories()` passes `dedup_days`.

## 8. CLI (`adapters/inbound/cli.py`)

- `trec publish [--date YYYY-MM-DD] [--only 1,3]`: prints one line per published story (`title → destination ref`), skipped ones as "already published", failures; exit 1 on any failure. No LLM prerequisites needed.
- `trec stories` and `trec plan`: after a successful draft, publish when `stories_publish`; a publishing failure exits 1 after the purge (same pattern as drafting failures) and never undoes the plan or the drafts.
- `trec doctor`: one line per configured destination with `problems()` (ok, or each problem); counts in the exit code only when `stories_publish` is true.
- `trec status`: "Stories waiting to be published: N" over the last `dedup_days` days, when publishing is configured.
- All new strings in `messages.Cli`, `Notify`, `Err`, `StoryDoc`. Help texts avoid square brackets (Typer's rich markup swallows `[...]`).

## 9. Spike before the adapter (risks to confirm with the real CLI)

Run once against a throwaway project (`backlog init --no-git` in a temporary folder) and record the answers in this file:

1. The exact `task create --plain` output and the task id format → `Parse.BACKLOG_TASK_ID`.
2. Whether `--ac "Dado x, quando y, então z"` on `create` keeps one criterion or splits at commas → `--ac` on create, or the `task edit` fallback.
3. That `-s Triagem` works once `Triagem` is in `statuses`, and the error when it is not.
4. The accepted `--priority` values.
5. The `statuses` line format in `config.yml`, for the doctor check.
6. That `backlog init --no-git` at the root of this Git repository writes only inside `backlog/` (or `backlog.config.yml`), leaves `AGENTS.md` and `CLAUDE.md` untouched with the right agent-instructions flag, and saves `autoCommit: false` and `remoteOperations: false`; `git status` shows nothing new once the `.gitignore` entries exist.
7. That the CLI run from the project root finds the project without extra flags.

## 10. Error handling and notifications

| Situation | Behavior |
|---|---|
| No drafts for the day (`trec publish`) | `error: no story drafts for <day>; run trec stories --date <day>`, exit 1 |
| Redraft of a published day | drafting refused (`Err.STORIES_ALREADY_PUBLISHED`); `trec plan` still saves the plan, exit 1 |
| Destination not ready (binary, project, status) | `PublishError` per story with the fix; other destinations go on; doctor shows the same problems |
| CLI failure / timeout / id not found | `PublishError` with the output tail; recorded in the report |
| Interrupted run | refs saved per story; rerun publishes only what is missing |
| Any failure | one notification `Notify.PUBLISH_FAILED` with counts; success: `Notify.STORIES_PUBLISHED` |

## 11. Security and privacy

- No network: Backlog.md runs locally (the adapter never calls `backlog browser` or remote Git operations).
- The backlog lives in this public repository's folder but is git-ignored: `problems()` and `publish` refuse a backlog folder that Git would version, and a Backlog.md config with `autoCommit` or `remoteOperations` on.
- `.gitignore` gains `backlog/` and `backlog.config.yml` in the same change that introduces the adapter.
- Arguments are passed as a list, never through a shell (story text comes from the model).

## 12. Testing strategy

| Component | Unit | Integration | E2E / opt-in |
|---|---|---|---|
| Domain (`Publication`, helpers, defaults) | `test_models.py` | — | — |
| Codec / repository (new fields, old JSON, `recent_story_drafts` window, glob not matching plans) | — | `test_repository_fs.py` | — |
| `PublishUserStories` (idempotency, `--only`, partial failure keeps refs, save after each success, notifications) | `test_planning_use_cases.py` with `FakeStoryPublisher` | — | — |
| `DraftUserStories` (redraft lock, existing stories passed) | `test_planning_use_cases.py` | — | — |
| Writer duplicates (message section, `duplicate_of` validation) | `test_stories_claude.py` | — | `TREC_REAL_CLAUDE_CLI=1` on a fixture plan with a repeated topic |
| Renderer (publication and duplicate lines) | `test_stories_markdown.py` | — | — |
| `BacklogMdPublisher` (`command()` shape, body, priority mapping, id parsing, error mapping, `problems()` incl. the git-ignore and autoCommit checks, publish refused when not ignored) | `test_publisher_backlogmd.py` | scripted stand-in `tests/fixtures/fake_backlog_cli.py` (records arguments, prints a task id, waits for a readiness file like the other fakes) | `TREC_REAL_BACKLOG=1 pytest -m slow tests/integration/test_publisher_backlogmd_real.py`: real `backlog init --no-git` + publish + `backlog task list --json` shows the task in Triagem with its criteria |
| Config (`[stories]` keys, `[stories.backlog_md]`, invalid destination, path resolution) | `test_config.py` | — | — |
| Container registry (one publisher per destination, order) | `test_container_platforms.py` | — | — |
| CLI (`publish` without drafts, with the fake CLI on `PATH`, `--only`, exit codes, doctor and status lines, plan → draft → publish chain) | — | `test_cli.py` | — |
| Whole flow on real data | — | — | manual, with the user: plan of 2026-10-09 → drafts → Backlog.md board |

The hardcoded-strings guard (`test_no_hardcoded_strings.py`) must stay green; `mypy` clean.

## 13. Implementation order

1. Domain and persistence (publications, duplicates, `recent_story_drafts`).
2. Duplicate check in drafting (writer, prompt, renderer) and the redraft lock.
3. Publisher port and `PublishUserStories`.
4. Configuration and the destination registry.
5. Spike (§9), `.gitignore` entries and one-time setup, then `BacklogMdPublisher`.
6. CLI (`publish`, chaining after drafts, doctor, status).
7. Real-data validation and documentation (PRD page 08, §10 of the requirements, README, AGENTS port table, COMMITS wave).

## 14. Out of scope

GitHub Projects and Azure Boards adapters; reading approvals or completion back from the board; updating or moving tasks after creation; an MCP-based publisher (the CLI is enough and testable).

## 15. References

- Existing code: `application/use_cases/planning.py` (`DraftUserStories`), `adapters/outbound/stories_claude.py`, `stories_markdown.py`, `repository_fs.py`, `codec.py`, `container.py` (`build_transport` as the model for the registry), `adapters/inbound/cli.py` (`_draft_stories`), `tests/fixtures/fake_claude_cli.py` (model for the fake `backlog` CLI).
- Backlog.md: README, CLI-INSTRUCTIONS.md and ADVANCED-CONFIG.md in `github.com/MrLesk/Backlog.md` (`task create` flags `-d/--desc`, `--ac`, `-l`, `-s`, `--priority`, `--plain`; `statuses` default `[To Do, In Progress, Done]`, edited in the config file; `init --no-git`; `autoCommit` false by default).

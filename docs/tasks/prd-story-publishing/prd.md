# PRD: Story publishing to a Markdown board (Backlog.md)

> **Status:** draft for approval · **Date:** 2026-10-10 · **Slug:** `story-publishing`
> **Builds on:** [User story drafts](../../prd/pages/08-user-stories.md) (delivered on branch `feat/story-drafts`)
> **Technical design:** [techspec.md](./techspec.md)

## 1. Problem

teams-recorder already drafts user stories from the daily plan into `data/plans/<day>.stories.md`, following the user's story guide. The drafts are a file the user has to open, read and copy somewhere by hand: there is no board where stories wait for approval, nothing stops the same topic from producing a new story every day it comes up, and nothing records where a story ended up.

## 2. Goal

Every drafted story lands, without manual copying, in a kanban board the user already opens, in a **Triagem** column where the user approves or rejects it. The way stories are published is a switch in `config.toml`, so other boards (GitHub Projects, Azure Boards) can be added later without changing the flow.

## 3. User and context

- One user (the recording owner) who attends several meetings a day and keeps a personal backlog of work coming out of them.
- The board is local and free: **Backlog.md**, a Markdown kanban (one `.md` file per task, columns configured in its `config.yml`, board in the terminal and in the browser, an MCP server so Claude can also read and move cards).
- Meeting content is confidential: stories stay on the user's machine (no network). The Backlog.md project lives in this repository's folder (`backlog/`), but it is git-ignored and never versioned, because `meet-record` is a public repository.

## 4. Scope

**In scope**
- Publish each drafted story as a Backlog.md task in the **Triagem** status of a configured Backlog.md project.
- A destinations switch: `[stories] destinations` lists where stories go; `backlog-md` is the first destination.
- Publish automatically right after drafting (so the 6 pm planner does it) and by hand.
- Never publish the same story twice to the same destination; never redraft a day whose stories were already published.
- Avoid duplicate stories across days.
- Visibility in `trec doctor`, `trec status` and the drafts document.
- Validation with real data (a real plan, the real model and a real Backlog.md project).

**Out of scope (later)**
- GitHub Projects and Azure Boards destinations (the switch is designed for them).
- Reading the board back (an approved or done task does not update `open_actions.json`).
- Editing, moving or deleting a task after it is created.
- Several users or shared boards.

## 5. Functional requirements

| # | Requirement |
|---|---|
| FR1 | Each drafted story becomes one task in the configured Backlog.md project, with status **Triagem**, the story title, the story sentence and the guide's other sections in the description, the acceptance criteria as Backlog.md acceptance criteria, the open questions, the priority (when the source actions stated one), configured labels, and traceability: the plan day, the source meetings and the source action ids. |
| FR2 | With `[stories] publish = true`, publishing runs right after drafting, in `trec plan` (and so the scheduled planner) and in `trec stories`. `trec publish [--date YYYY-MM-DD] [--only 1,3]` publishes a day's drafts by hand; `--only` takes the story numbers shown in the drafts document. |
| FR3 | Publishing is idempotent: a story already published to a destination is skipped for that destination; running again only sends what is missing. |
| FR4 | A failure on one story or one destination does not stop the others. The command reports every failure, exits with code 1 and sends one notification; the stories that were published stay recorded. |
| FR5 | Drafting a day again (`trec stories --date`, `trec plan --date`) is refused when any story of that day was already published, with a message explaining why; the plan itself is still rebuilt. |
| FR6 | When drafting, the stories of the previous `[stories] dedup_days` days (default 30) are given to the model; an action already covered by one of them is left out with a reference to that story instead of becoming a new one. |
| FR7 | `[stories] destinations` is a list; an unknown value fails when the configuration loads. Adding a destination means one new adapter, one new value and one registry entry, with no change to the use cases. |
| FR8 | Approval happens on the board: moving a task from Triagem to To Do approves it; archiving it rejects it. teams-recorder never changes a task after creating it. |
| FR9 | `trec doctor` checks each configured destination (for Backlog.md: the `backlog` binary, an initialized project, the Triagem status in its columns, a backlog folder that Git ignores). `trec status` shows how many drafted stories are waiting to be published. |
| FR10 | The drafts document shows, under each story, where it was published (destination and task id) and, for left-out actions, the existing story that already covers them. |

## 6. Non-functional requirements

- **Privacy:** no network calls; the Backlog.md files live in `backlog/` at the project root and are listed in `.gitignore`; teams-recorder refuses to publish into a folder that Git would version (the repository is public and stories contain meeting content).
- **Reliability:** state stays in files (`data/plans/<day>.stories.json`); the publication of each story is saved as soon as it succeeds, so an interrupted run resumes without duplicates.
- **Portability:** works on macOS and Windows (the Backlog.md CLI is cross-platform); process spawns go through the project's retrying helpers.
- **Conventions:** hexagonal layering, strings in `messages.py` / `constants.py`, English in the repository and Brazilian Portuguese in the content, as in [AGENTS.md](../../AGENTS.md).
- **Quality:** every task ships with unit and integration tests; `pytest` and `mypy` stay green.

## 7. Success criteria

- After a weekday 6 pm run with new actions, every drafted story is in the Triagem column of the board when the run ends.
- Running `trec publish` again, or the whole plan again, creates zero duplicate tasks.
- A topic discussed on two different days produces one story, not two.
- On the real plan of 2026-10-09 the user reviews the result on the board and accepts the story quality, or the guide is adjusted until they do.
- `pytest` and `mypy` are clean.

## 8. Decisions already made (interview of 2026-10-10)

1. Stories are drafted from the plan's new actions; the model filters and groups them; the user's guide is always in context (delivered).
2. Review and approval happen on the board, in a Triagem column.
3. The first destination is a Markdown board; the user chose Backlog.md over Obsidian Kanban.
4. Destinations are a switch in configuration (port and adapters, a registry in the composition root), ready for GitHub and Azure.
5. The Backlog.md project lives inside this repository's folder, in `backlog/`, and is excluded from Git with `.gitignore` (stories are never versioned).

## 9. Open questions

- Which labels every published task carries (default: `teams-recorder`).

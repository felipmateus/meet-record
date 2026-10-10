# User story drafts and publishing

> **Commands:** `trec stories [--date YYYY-MM-DD]`, `trec publish [--date YYYY-MM-DD] [--only 1,3]` · drafting also runs right after `trec plan` when `[stories] enabled = true` (so the 6 pm planner drafts them), and publishing right after drafting when `[stories] publish = true`
> **Module:** User stories · **Generated:** 2026-10-10 · **Status:** delivered (drafts; Backlog.md board), publishing by hand (`publish = false`) until the user approves the stories on the board. Requirements and design: `tasks/prd-story-publishing/`

## Overview
Turns the day's new actions into user story drafts for the user's backlog, written by the rules of the user's own instructions document (the story guide), and publishes them to a board where the user approves or rejects each one. The drafts document records each story and where it was published.

## Inputs
| Input | Source | Rule |
|---|---|---|
| Candidate actions | `new_actions` of `data/plans/<day>.json` | the user's new actions of that day; the plan must exist |
| Meeting context | `analysis.json` of each action's source meeting | title, purpose, summary, topics, decisions, others' actions, open questions, risks; missing meetings are skipped |
| Story guide | `[stories] guide` (default `prompts/user_story_guide.md`) | sent on every call, re-read each time; missing or empty = error |

## Output
| Artifact | Content |
|---|---|
| `data/plans/<day>.stories.md` | Review document: one section per story (title; priority, due date and meetings; story sentence; acceptance criteria as a checklist; the guide's other sections; open questions; source actions with the transcript timestamp), then the actions that did not become stories and why |
| `data/plans/<day>.stories.json` | The same drafts, structured: id, title, narrative, acceptance criteria, details, open questions, source action ids and meetings, priority, due date, publications (destination, task id, time); skipped actions with reasons and, for duplicates, the covering story's id |

## Drafting rules
- Actions are routed by the kind the meeting analysis gave them (see [Analysis](./03-analysis.md)): `feature` and `bug` go to the model as story candidates; `technical` and `operation` become task cards with no model call (the action's text as the title, no story sentence or criteria); `management` and `communication` are left out with "<tipo>: fica só no plano do dia". Actions without a kind (extracted before classification) go to the model, which applies the guide's definition.
- The model writes the stories (bugs in the guide's bug format), groups actions that deliver the same outcome and writes the text in Brazilian Portuguese unless the guide says otherwise.
- The code keeps the traceability: a story may only cite action ids it received (others are dropped; a story left with none is dropped); every action that is in no story is listed as left out, with the model's reason or "o modelo não incluiu esta ação em nenhuma história"; priority is the strongest and the due date the earliest among the story's source actions.
- No story candidates in the plan: the model is not called. Every card shows its kind (Feature, Bug, Tarefa técnica, Operação) in the document and as a label on the board.

## Interactions
- `trec stories` without a date: today's plan. With `--date`: that day's plan; redrafting replaces that day's drafts, unless they were already published (see below).
- After `trec plan`, with `[stories] enabled = true`: prints `Drafting user stories for <day>… ok (N stories, M actions left out)` and the titles. A failure prints the error, sends "User story drafts failed" and makes the command exit with code 1 after the purge; the plan itself is kept.
- Notification "User story drafts ready: N draft(s) to review, M action(s) left out" when at least one story was drafted.
- `trec doctor` shows whether the guide exists (`MISSING` only when drafting is enabled).

## Integrations
Drafting: same provider as the analysis and the plan (API or Claude Code), with schema-constrained structured output. Publishing: the Backlog.md CLI and `git check-ignore` (see the [integrations appendix](../appendix/integrations.md)).

## Duplicates and redrafting
- The writer also receives the stories of the previous `[stories] dedup_days` days (default 30). An action already covered by one of them is left out with `duplicate_of` pointing to that story (only ids it was given are kept); the drafts document shows the covering story's title.
- A day whose stories were already published is never drafted again ("the stories of <day> were already published…"); the plan itself is still rebuilt and the command exits 1.

## Publishing
| Item | Behavior |
|---|---|
| Destinations | `[stories] destinations` (a list; `backlog-md` today, GitHub and Azure later); an unknown name fails when the configuration loads |
| Backlog.md task | One per story, in `[stories.backlog_md] status` (default Triagem): title, description with the story sentence, the guide's other sections, open questions and the origin (plan day, meetings, action ids, drafts file), one acceptance criterion per `--ac`, priority when stated, labels plus the plan day |
| Review | On the board: move to To Do to approve, archive to reject. teams-recorder never edits, moves or deletes a task |
| Idempotency | Each publication (destination, task id, time) is saved in `plans/<day>.stories.json` as soon as it succeeds; a rerun skips what each destination already has |
| Failures | One story or destination failing does not stop the others; the command lists every failure, exits 1 and notifies "Publishing user stories failed"; in `trec plan` the purge still runs and the plan and drafts are kept |
| Safety | The board lives in `./backlog`, git-ignored (public repository). Publishing is refused when Git would version the board or cannot confirm it is ignored, when Backlog.md would commit or reach remotes, or when the binary is a Windows command shim |
| Visibility | `trec doctor` shows each destination as ready or with its problems (failing only when publishing is automatic); `trec status` shows the stories still waiting; the drafts document lists where each story was published |

## Relationships
- **From:** [Daily plan](./06-daily-plan.md). **To:** the Backlog.md board, where the user approves or rejects each story. Reading approvals back into the open actions is not done.

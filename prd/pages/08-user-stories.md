# User story drafts

> **Command:** `trec stories [--date YYYY-MM-DD]` · also runs right after `trec plan` when `[stories] enabled = true` (so the 6 pm planner drafts them)
> **Module:** User stories · **Generated:** 2026-10-10 · **Status:** drafts delivered; publishing to boards pending

## Overview
Turns the day's new actions into user story drafts for the user's backlog, written by the rules of the user's own instructions document (the story guide). The drafts are a document to review; nothing is sent to any board.

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
| `data/plans/<day>.stories.json` | The same drafts, structured: id, title, narrative, acceptance criteria, details, open questions, source action ids and meetings, priority, due date; skipped actions with reasons |

## Drafting rules
- The model decides which actions are stories (by the guide's definition), groups actions that deliver the same outcome and writes the text in Brazilian Portuguese unless the guide says otherwise.
- The code keeps the traceability: a story may only cite action ids it received (others are dropped; a story left with none is dropped); every action that is in no story is listed as left out, with the model's reason or "o modelo não incluiu esta ação em nenhuma história"; priority is the strongest and the due date the earliest among the story's source actions.
- No new actions in the plan: an empty set is written and the model is not called.

## Interactions
- `trec stories` without a date: today's plan. With `--date`: that day's plan; redrafting replaces that day's drafts.
- After `trec plan`, with `[stories] enabled = true`: prints `Drafting user stories for <day>… ok (N stories, M actions left out)` and the titles. A failure prints the error, sends "User story drafts failed" and makes the command exit with code 1 after the purge; the plan itself is kept.
- Notification "User story drafts ready: N draft(s) to review, M action(s) left out" when at least one story was drafted.
- `trec doctor` shows whether the guide exists (`MISSING` only when drafting is enabled).

## Integrations
Same provider as the analysis and the plan (API or Claude Code), with schema-constrained structured output.

## Relationships
- **From:** [Daily plan](./06-daily-plan.md). **To:** the user reviews the Markdown. Publishing to GitHub Projects, Azure Boards or other destinations (one adapter per destination, several at once through a composite) is the next step.

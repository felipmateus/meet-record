# Daily plan

> **Command:** `trec plan [--date YYYY-MM-DD] [--purge]` · scheduled Mon–Fri at 6 pm (`planner.hour`) through the `local.teams-recorder.planner` LaunchAgent
> **Module:** Planning · **Generated:** 2026-10-05 · **Status:** delivered (phase 6); validation with a real meeting pending

## Overview
Once a day, consolidates the analyses of the day's meetings, the previous day's plan and the accumulated list of open actions into a Markdown activity plan, and updates the action list (new, completed, overdue).

## Inputs
| Input | Source | Rule |
|---|---|---|
| Day's analyses | meetings with `started_at` on that day and state `analyzed` | only analyzed meetings count |
| Previous plan | the latest `data/plans/<date>.json` before that day | may not exist |
| Open actions | `data/plans/open_actions.json` | list accumulated across days |

## Output
| Artifact | Content |
|---|---|
| `data/plans/YYYY-MM-DD.md` | Title with weekday and date; sections **Prioridades** (3 to 5), **Ações novas**, **Vencidas** (only the computed overdue ids), **Aguardando terceiros** (others' actions to follow up), **Agenda** (next meetings and dated milestones) and **Conflitos e alertas** (conflicting deadlines, overload, actions without owner, risks); empty sections omitted except Prioridades |
| `data/plans/YYYY-MM-DD.json` | priorities, new actions, completed ids, overdue ids, markdown |
| updated `open_actions.json` | removes completed actions, flags overdue ones (`status = overdue`), appends new ones without duplicating ids |

## Planning rules (prompt already written in `prompts/plan_system.md`)
- Prioritizes by deadline and impact: overdue/due soon first, then whatever unblocks others, then the rest.
- Does not invent actions: every new action comes from one of the day's analyses; completed/overdue must match an id in the open list.
- Marks an action completed only on a clear indication in some analysis; overdue when the deadline has passed as of the plan date.
- Brazilian Portuguese, direct.

## Interactions
- `trec plan` without a date: today. With `--date`: rebuilds that day's plan (replaces that day's files). `--purge` applies audio retention afterwards.
- Division of labor: new actions (the user's actions in the day's analyses whose ids are not in the open list) and overdue ones (due date < day) are computed by the code; the model receives everything and returns Markdown, priorities and completed ids, filtered against the existing ids.
- A day with no analyses and no open actions: a minimal plan generated locally, with no model call. A day with only open actions: the model is called to re-prioritize.
- Same pre-validation as the analysis (key or `claude`). Notification "Daily plan ready: N meeting(s), M new action(s)" (plan of the day ready: N meeting(s), M new action(s)).
- Scheduler: `trec agent install` also registers the planner (`StartCalendarInterval` Mon–Fri at `planner.hour`), which runs `trec plan --purge`; `agent status` shows whether it is scheduled.

## Integrations
Same provider as the analysis (API or Claude Code), with schema-constrained structured output.

## Relationships
- **From:** [Analysis](./03-analysis.md). **To:** the user reads the Markdown; integrations (To Do, Obsidian) are left for after phase 7.

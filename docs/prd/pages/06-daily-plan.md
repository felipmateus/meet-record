# Daily plan (removed)

> **Command:** none · `trec plan` and the 6 pm planner were removed on 2026-10-20
> **Module:** Planning (retired) · **Status:** removed; replaced by the [activities document](./09-activities.md)

## What happened
Until 2026-10-20 the product consolidated the day's analyses, the previous plan and a list of open actions (`open_actions.json`) into a Markdown plan once a day at 6 pm. The user decided it should go ("pode remover o plano das 18h") after the activities document had run beside it: the plan had no section for an open action that was neither new nor overdue, showed an overdue one once, never accumulated other people's actions and ignored meetings analyzed after 6 pm.

## What replaced each part
| Before | Now |
|---|---|
| `trec plan`, scheduled Mon–Fri at 6 pm | Nothing is scheduled. A curator agent updates the [activities document](./09-activities.md) after each analyzed meeting |
| `plans/<day>.md` and `.json`, `open_actions.json` | `activities/atividades.md`, its archive and its pass log (see the [data layout](../appendix/data-layout.md)). Old plan files stay on disk and are not read |
| Overdue and completed actions computed from the open list | The document's dates and the user's own ticks; a meeting that says something is done adds a 💬 suggestion, and only the user ticks |
| Stories drafted from the plan's new actions, also by `trec plan` | Stories drafted from the items the user tags `#história`, only with `trec stories` (see [User story drafts](./08-user-stories.md)) |
| Audio retention applied by `trec plan --purge` | The daemon runs the retention once a day; `trec purge` runs it on demand (see [Operations](./05-operations.md)) |
| The `local.teams-recorder.planner` LaunchAgent (Windows task `planner`) | Removed by `trec agent install`, `restart` and `uninstall` and by the installers, whichever finds it |

## Relationships
- **From:** [Analysis](./03-analysis.md). **To:** [Activities document](./09-activities.md).

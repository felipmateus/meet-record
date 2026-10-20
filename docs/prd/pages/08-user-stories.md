# User story drafts and publishing

> **Commands:** `trec stories`, `trec publish [--date YYYY-MM-DD] [--only 1,3]` · publishing also runs right after drafting when `[stories] publish = true`
> **Module:** User stories · **Generated:** 2026-10-10, rewritten 2026-10-20 · **Status:** delivered (drafts from tagged items; Backlog.md board), publishing by hand (`publish = false`) until the user approves the stories on the board. Requirements and design: `docs/tasks/prd-story-publishing/` and `docs/tasks/activities-curator/`

## Overview
Turns the items of the [activities document](./09-activities.md) that the user tags `#história` into user story drafts for their backlog, written by the rules of the user's own instructions document (the story guide), and publishes them to a board where the user approves or rejects each one. Nothing is drafted unless the user tagged it. The drafts document records each story and where it was published. Until 2026-10-20 the stories came from the new actions of the daily plan, drafted by `trec plan` and the 6 pm planner; the plan is gone (see [Daily plan](./06-daily-plan.md)).

## Inputs
| Input | Source | Rule |
|---|---|---|
| Tagged items | the body of `data/activities/atividades.md` | a line that carries `#história` (as a whole word) plus the lines indented under it, up to a blank line or a line as shallow as the tagged one; the title box and the generated link block are not items; no document = error |
| Items already handled | the recent drafts (`data/plans/*.stories.json`) | an item whose tagged line is already in a story's `source_text` or a skip's `source_line` is not sent to the model again |
| Meeting context | `analysis.json` of each meeting the item's links point to | title, purpose, summary, topics, decisions, the user's and others' actions, deadlines, open questions, risks; a link to a meeting that no longer exists is skipped |
| Recent stories | the drafts of the previous `[stories] dedup_days` days (default 30) and today's | so an item that repeats a story is recognised |
| Story guide | `[stories] guide` (default `prompts/user_story_guide.md`) | sent on every call, re-read each time; missing or empty = error |

## Output
| Artifact | Content |
|---|---|
| `data/plans/<day>.stories.md` | Review document: one section per story (title; priority, due date and meetings; story sentence; acceptance criteria as a checklist; the guide's other sections; open questions; the tagged item quoted as the user wrote it, under "Item de origem"), then the tagged items that did not become stories and why |
| `data/plans/<day>.stories.json` | The same drafts, structured: id, title, kind, narrative, acceptance criteria, details, open questions, source text and meetings, priority, due date, publications (destination, task id, time); skipped items with their tagged line, the reason and, for duplicates, the covering story's id |
| `atividades.md` | Each drafted item's tag becomes `história: [rascunho dd/mm](../plans/<day>.stories.md)`; a duplicate's becomes `história: já existe ("<title>")`. An item the model left out keeps its tag |

Drafts of the same day are merged into one file: new stories are appended and earlier numbering never changes. Drafts written before 2026-10-20 (from a plan, with source action ids) are still read and rendered; a planner-era story's origin on the board reads "plano de <day>".

## Drafting rules
- One model call writes the stories of all the new tagged items of a run. Each item gets a ref (`b1`, `b2`, …) for that call; the model must cite the ref of the item a story comes from, and a ref it was not given is dropped.
- The model decides each story's **kind** from the item (`feature`, `bug`, `technical`, `operation`, `management` or `communication`): `feature` and `bug` become user stories (bugs in the guide's bug format); `technical` and `operation` become task cards (a short title and the details the guide asks for, no story sentence); `management` and `communication` are left out with "<tipo>: não vira história nem card". An item that is none of these is left out with the model's reason.
- It sets `priority` only when the item or its meetings stated or clearly implied the urgency, and `due` only when they gave a date for the work; otherwise both stay empty.
- The model groups nothing across items: one item gives one story (the guide's size rules may split it), and two items are never merged.
- The code keeps the traceability: every item that ends up in no story is listed as left out, with the model's reason or "o modelo não incluiu este item em nenhuma história".
- Every card shows its kind (Feature, Bug, Tarefa técnica, Operação) in the document and as a label on the board.

## Interactions
- `trec stories` takes no date and no option. It prints `Drafting N tagged items…` before the model call, then `ok (…)` with how many stories, task cards, items that already exist and items left out, one line per story title and per left-out item with its reason, and the path of today's drafts document. With nothing tagged it prints `Nothing tagged #história in <path>.` and calls no model; with no document it fails with `No activities document yet: <path>` (exit 1).
- Tag replacement: after the drafts are saved, each tag is replaced under the activities lock, which the command does not wait for. When a curator pass holds it, the command says the tags are replaced by the next run (the drafts are not lost, and the next run does not redraft them). A tagged line edited meanwhile keeps its tag, and the command says so.
- With `[stories] publish = true` the command publishes today's drafts right after drafting (see Publishing); `[stories] enabled` is no longer read.
- A failure prints the error, sends "User story drafts failed" and exits 1.
- The command runs in the CLI process: no daemon restart is needed.
- `trec doctor` shows whether the guide exists (information only) and each story destination.
- **Provenance of every criterion** (fidelity guard, FR6): each acceptance criterion shows where it comes from, the transcript time of the action or decision it is based on (`[00:03:10]`) or "(sugestão)" when the model proposes it and nobody said it, in the drafts document and in the board task's criteria. A cited time that is not a line of the story's source meetings is shown as "(sugestão)". The story writer is also asked to end each line of the other sections with its source. Drafts made before 2026-10-14 show their criteria as before.
- **Degraded transcripts** (whisper loop that survived the retry, see [Transcription](./02-transcription.md)): the drafts document opens with a banner for each source meeting whose transcript is degraded or was recorded at the wrong sample rate, with a line saying nothing was confirmed from it, because what came from it may be incomplete. The stories are still drafted (fidelity-guard decision 9).
- **Unconfirmed claims**: the story writer is told never to cite a claim the verifier did not confirm as the source of a criterion or detail (it may raise it as an open question). The "⚠️ A confirmar na transcrição" mark on a task card and the "não confirmada" listing belonged to the plan's actions and exist only on planner-era drafts.

## Integrations
Drafting: same provider as the analysis and the activities curator (API or Claude Code), with schema-constrained structured output. Publishing: the Backlog.md CLI and `git check-ignore` (see the [integrations appendix](../appendix/integrations.md)).

## Duplicates and redrafting
- The writer also receives the stories of the previous `[stories] dedup_days` days. An item already covered by one of them is left out with `duplicate_of` pointing to that story (only ids it was given are kept); its tag becomes `história: já existe ("<title>")`, and the drafts document shows the covering story's title.
- There is no redrafting: an item whose tagged line is already in the drafts is not sent again, and an edited tagged line that still carries the tag is a new item on the next run (the writer sees the earlier story and may mark it a duplicate).
- A day whose stories were already published can receive new ones: publishing skips what each destination already has.

## Publishing
`trec publish [--date YYYY-MM-DD] [--only 1,3]` reads only `data/plans/<day>.stories.json` (default today, no plan involved) and works on drafts of either era.

| Item | Behavior |
|---|---|
| Destinations | `[stories] destinations` (a list; `backlog-md` today, GitHub and Azure later); an unknown name fails when the configuration loads |
| Backlog.md task | One per story, in `[stories.backlog_md] status` (default Triagem): title, description with the story sentence, the guide's other sections, open questions and the origin (for a story from a tagged item: "atividades de <day>" and the meetings; the drafts file), one acceptance criterion per `--ac`, priority when stated, labels plus the day |
| Review | On the board: move to To Do to approve, archive to reject. teams-recorder never edits, moves or deletes a task |
| Idempotency | Each publication (destination, task id, time) is saved in `plans/<day>.stories.json` as soon as it succeeds; a rerun skips what each destination already has |
| Failures | One story or destination failing does not stop the others; the command lists every failure, exits 1 and notifies "Publishing user stories failed". A day with no drafts is an error that names `trec stories` |
| Safety | The board lives in `./backlog`, git-ignored (public repository). Publishing is refused when Git would version the board or cannot confirm it is ignored, when Backlog.md would commit or reach remotes, or when the binary is a Windows command shim |
| Visibility | `trec doctor` shows each destination as ready or with its problems (failing only when publishing is automatic); `trec status` shows the stories still waiting; the drafts document lists where each story was published |

## Relationships
- **From:** [Activities document](./09-activities.md) (the items the user tags). **To:** the Backlog.md board, where the user approves or rejects each story. Reading approvals back into the activities document is not done.

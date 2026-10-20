# User Stories: Activities curator

Canonical behavior catalog for the activities curator. Companion to `_spec.md`; consumed by
`_spec.md` Part II (component mapping) and `_tests.md` (coverage matrix). There is no UI beyond
the Markdown file the user opens in an editor and the `trec` CLI.

Document text the user reads is Brazilian Portuguese (LLM-built content, allowed by AGENTS.md); CLI output and notification titles are English.

## Personas

- **Felipe (the user)** — attends several Teams meetings a day in Brazilian Portuguese, opens `atividades.md` in VS Code (Obsidian later) to see what is still open, ticks what is done, writes his own lines. Wants one place, no ritual, and the final word on what is finished.
- **Operator (the same person, maintaining the tool)** — restarts the daemon, reruns a meeting, undoes a bad pass, runs the bootstrap, reads logs when something looks wrong.

## Story Index

| ID     | Feature Area   | Persona  | Story |
| ------ | -------------- | -------- | ----- |
| US-001 | Document       | Felipe   | Everything still open is in one document, kept current after every meeting |
| US-002 | Document       | Felipe   | Each item says where it came from |
| US-003 | Document       | Felipe   | A focus at the top says what to do next, with dates that stay true |
| US-004 | Document       | Felipe   | What is not a task still lands somewhere (decisions, questions, risks, ownerless) |
| US-005 | Progress       | Felipe   | What a meeting says about existing work shows up on that item |
| US-006 | Ownership      | Felipe   | Only I close items; the curator suggests |
| US-007 | Ownership      | Felipe   | My edits and my own lines are never overwritten |
| US-008 | Retention      | Felipe   | Nothing is deleted; what leaves goes to an archive with a reason |
| US-009 | Retention      | Felipe   | The document stays short over weeks |
| US-010 | Safety         | Felipe   | I can undo a bad pass |
| US-011 | Safety         | Operator | A failed pass never corrupts the document and is retried by itself |
| US-012 | Safety         | Felipe   | Editing while the curator works never loses my edits or its work |
| US-013 | Analysis       | Felipe   | The minutes show the progress reported in the meeting |
| US-014 | Stories        | Felipe   | A story is written only for an item I tag |
| US-015 | Operation      | Operator | Several meetings ending together are curated together |
| US-016 | Operation      | Operator | Rerun one meeting, or build the first document from past meetings |
| US-017 | Operation      | Felipe   | `trec activities` shows the focus and opens the file |
| US-018 | Migration      | Operator | The 18:00 planner is gone and nothing breaks |
| US-019 | Notifications  | Felipe   | I am notified only when something concerns me |

## Document

### US-001: One current document

**As** Felipe, **I want** everything I still have to do, wait on, or need to remember in one file, updated minutes after each meeting, **so that** I stop losing track of unfinished work from previous days.

Acceptance criteria:

- AC-1: Given a meeting with an action of mine was analyzed, when its curator pass finishes, then `data/activities/atividades.md` lists that action under `## Minhas ações` without me running anything.
- AC-2: Given an item of mine stayed open for days without being mentioned, when I open the document, then it is still there, never dropped; an item the curator wrote gets 💤 after about three weeks without mention, while a line I wrote myself never does.
- AC-3: Given another person's action that I depend on, when the pass finishes, then it is a checkbox line under `## Aguardando outros` naming the person.
- AC-4: Given another person's action that does not affect me, when the pass finishes, then it is not in the document (it stays in the minutes).
- AC-5: Given no document exists, when the first pass runs, then the skeleton (title, box, four sections, link block) is created and filled.

Edge cases:

- EC-1: A meeting under 20 words or with nothing extracted → no curator call; the document is unchanged; the pass log records `skipped_empty`.
- EC-2: Two meetings report the same work in different words → one item with both meeting links, not two items.
- EC-3: A later meeting repeats an item that is in the archive and brings a new fact → it comes back with a sub-line `voltou: arquivado em dd/mm (motivo)`.
- EC-4: Same meeting curated twice (rerun) → no duplicate items; items whose origin is that meeting are recognised.
- EC-5: The document grows to 150 open items → still curated; no hard cap, no warning; size is measured in the evaluation.

### US-002: Provenance on every item

**As** Felipe, **I want** each line to link to the minutes of the meeting it came from, **so that** I can check what was really said.

Acceptance criteria:

- AC-1: Given an item added by the curator, then its line ends with a reference-style link whose text is a short meeting name and date and whose label is the meeting id, e.g. `[Daily 16/10][2026-10-16_09-30-11]`.
- AC-2: Given the document, then a link block at the end defines every label used, pointing to `../recordings/<id>/minutes.md`, and VS Code's preview opens the minutes from it.
- AC-3: Given a 💬 suggestion or a change note, then it carries the meeting and the `hh:mm:ss` where it was said.
- AC-4: Given an item mentioned again later, then at most the origin link plus the two latest mention links appear on its line.

Edge cases:

- EC-1: A label whose meeting folder was deleted → its definition is dropped; the link text stays as plain text.
- EC-2: A line I wrote by hand has no link → it stays without one; when a later meeting mentions it, the mention is a sub-line `citado na [<reunião> <dd/mm>][<id>]`, never a link on my line.

### US-003: Focus with dates that stay true

**As** Felipe, **I want** 3 to 5 lines at the top saying what to do next and why, **so that** I know where to start without reading everything.

Acceptance criteria:

- AC-1: Given a pass, then the box shows `Atualizado <ddd dd/mm hh:mm> · após <meeting title(s)>` and 3–5 focus lines, each naming an item in bold and why now.
- AC-2: Given overdue items of mine, then they are in the focus before anything else.
- AC-3: Given the box text, then every date in it is absolute with weekday (`vence seg 19/10`); it never says only "hoje" or "amanhã", so it stays correct the next morning.
- AC-4: Given an unconfirmed item, then it is in the focus only when overdue.

Edge cases:

- EC-1: I type a line inside the box → it is not lost: the pass moves it into the right section and the box is rewritten; if the pass did not move it, or I typed it while the pass was running, it is put at the top of `## Minhas ações` and the next pass treats it as my line.
- EC-2: Fewer than 3 open items → the focus lists what exists (possibly 1 or 0 lines with "nada pendente").

### US-004: Context that is not a task

**As** Felipe, **I want** recent decisions, open questions, risks and ownerless actions that affect me in one short section, **so that** "not every activity is a task" still has a place.

Acceptance criteria:

- AC-1: Given a decision in a meeting, then a line `- Decisão: … · [link]` appears under `## Contexto recente`.
- AC-2: Given an action with no owner that affects me, then `- Sem dono: …` appears there, not under my actions.
- AC-3: Given a question later answered in another meeting, then the question is archived with reason `respondida na <reunião dd/mm>: …`.
- AC-4: Given entries not mentioned for 7 days, then they are archived; the section holds about 10 lines at most.

Edge cases:

- EC-1: Meetings and milestones with a date go to `## Agenda e prazos`, not here; a past date is archived the next day.

## Progress

### US-005: Progress reported in a meeting shows up on the item

**As** Felipe, **I want** "já mandei", "ficou para sexta", "passa para a Carla" said in a meeting to appear on the matching item, **so that** the document reflects what happened without me retyping it.

Acceptance criteria:

- AC-1: Given an item the curator wrote and a meeting says its date moved, then the date on the line changes and a sub-line reads `prazo mudou de <antes> para <depois> (<reunião dd/mm>, hh:mm:ss)`.
- AC-2: Given a meeting says an item was done, cancelled or reassigned, then a 💬 sub-line quotes who said it, where and when, and asks me to mark it.
- AC-3: Given a progress statement by Bruno, then it only touches items owned by Bruno or waiting on Bruno.
- AC-4: Given a progress statement with unknown speaker, then it becomes a 💬 only, never a direct change.
- AC-5: Given an "in progress" statement, then a sub-line is added only when it says something concrete ("falta só o módulo de reservas").

Edge cases:

- EC-1: Hedged statement ("acho que já mandei") → 💬 keeps the hedge in the quote.
- EC-2: A statement the verifier did not confirm → 💬 with ⚠️ and the reason.
- EC-3: A statement matching no item → not added; logged as ignored, unless it reports a new blocker on my work (→ `Risco:`).
- EC-4: An intention ("a gente precisa terminar X") → not treated as progress.
- EC-5: The item is a line I wrote → the change becomes a 💬, never an edit of my line.

## Ownership

### US-006: Only I close items

**As** Felipe, **I want** to be the only one who ticks `[x]`, **so that** nothing disappears because a model misheard.

Acceptance criteria:

- AC-1: Given any pass, then no `- [ ]` line becomes `- [x]` and no `- [x]` becomes `- [ ]` by the curator.
- AC-2: Given I ticked an item, when the next pass runs, then ` ✔ <ddd dd/mm>` is appended and the item moves to the bottom of its section.
- AC-3: Given an item ticked before the previous working day, then it is archived with reason `concluído`.
- AC-4: Given a waiting-on-others item, then it has a checkbox I can tick when I receive it.

Edge cases:

- EC-1: An edit would remove an open line other than through archiving, or tick, untick or lose a checkbox, even while adding a new item in the same pass → that edit is rejected with the reason (one retry of the failed edits, then nothing is written).

### US-007: My edits stand

**As** Felipe, **I want** whatever I change in the file to stay as I left it, **so that** the document is mine, not the model's.

Acceptance criteria:

- AC-1: Given I reworded an item, then later passes never reword it back; new information goes in sub-lines.
- AC-2: Given I wrote a line by hand, then it is never edited, moved, archived, marked 💤 or given links on its main line by the curator (it may receive a sub-line).
- AC-3: Given I deleted an item, then it is archived as `removido por você` and is not added again unless a new meeting brings a new fact.
- AC-4: Given my line and a curator line are the same work, then my line survives and the curator's is folded into it (or a 💬 `parece duplicado de …` is added).
- AC-5: Given any existing line, then the curator never rewrites its main text; only date, owner or priority fields change, and only on lines it wrote, with a change note.

Edge cases:

- EC-1: An editor saved an old buffer over the file and most of the last pass's additions vanished → they come back with 💬 `voltou: parece que o editor sobrescreveu; apague de novo se não vale`, and I am notified.
- EC-2: I add my own `##` section → the curator reads it and never edits it.

## Retention

### US-008: Nothing is deleted

**As** Felipe, **I want** everything that leaves the document to go to an archive with a reason, **so that** I can always find it again.

Acceptance criteria:

- AC-1: Given an item leaves the document, then `data/activities/arquivo/<AAAA-MM>.md` gains an entry `### dd/mm/aaaa — <motivo>` followed by the verbatim text and the link definitions it uses (paths valid from the archive folder).
- AC-2: Given an open item of mine, then it is never archived for age, only as a duplicate (`duplicado de: <título>`), and the evaluation measures zero other cases.

Edge cases:

- EC-1: Archiving across a month boundary → the entry goes to the month of the pass.

### US-009: Short over weeks

**As** Felipe, **I want** the document to stay readable after weeks of meetings, **so that** I keep opening it.

Acceptance criteria:

- AC-1: Given an item mentioned in many meetings, then it has at most 2 sub-lines; older notes are folded into the link list or dropped (never my own sub-lines).
- AC-2: Given ten working days of meetings, then the document stays around 8k tokens (measured in the evaluation).
- AC-3: Given only three markers in use, then they are 💬 (suggestion for me), ⚠️ (not confirmed), 💤 (not mentioned for about three weeks).

## Safety

### US-010: Undo

**As** Felipe, **I want** to undo the last pass after seeing what it changed, **so that** a bad pass costs me nothing.

Acceptance criteria:

- AC-1: Given passes exist, when I run `trec activities undo`, then I see the diff from the current file back to the version before the last pass and am asked `[y/N]`.
- AC-2: Given I edited the file after that pass, then the prompt warns that those N lines are discarded too.
- AC-3: Given I answer yes, then the document returns to the version before the pass and the archive entries that pass added are removed.
- AC-4: Given I run undo again, then it walks one more pass back.
- AC-5: Given a new pass committed while the diff was on screen, when I answer yes, then nothing is restored and I am told to run undo again (the diff I confirmed is the one that is undone).
- AC-6: Given I deleted, ticked or reworded something before or while the undone pass ran, when the next pass runs after the undo, then it sees those edits as mine again (an item the undone pass had archived as `removido por você` is not lost: the next pass archives it again).

Edge cases:

- EC-1: The curator is working → undo refuses at once with `The curator is working; try again in a few minutes.` (no waiting).
- EC-2: The archive changed after that pass → the archive is left alone and a warning says so.
- EC-3: No pass to undo → message and exit 1.
- EC-4: A new pass committed between the diff and my answer → `A new pass ran while you were deciding; run trec activities undo again.` and exit 1; the document is untouched.

### US-011: Failures are atomic and retried

**As** the operator, **I want** a failed pass to leave the document untouched and to be retried without my help, **so that** an outage never loses a meeting's items.

Acceptance criteria:

- AC-1: Given the model refuses, truncates, times out or breaks the schema, then the document is unchanged, `curation_error.txt` is written in the meeting folder, and I am notified.
- AC-2: Given some edits cannot be applied (target not found exactly once) or break the checkbox rule, then exactly one retry is made with only the failed edits and the reason each failed; if it fails, nothing is written.
- AC-3: Given a meeting analyzed today or in the two working days before has no successful pass (today is day 0), when any later pass runs, then that meeting is included (oldest first) and its error file cleared on success; Monday's pass picks up Friday's meeting.
- AC-4: Given a meeting failed two passes it was curated alone in, then it is no longer included automatically; `trec activities` shows it with the command to retry.
- AC-5: Given the daemon was restarted (or the Mac slept or rebooted) after a meeting was analyzed and before its pass committed, when the daemon starts, then that meeting is queued again without my help.
- AC-6: Given a meeting analyzed in the last 10 working days has no successful pass, whether it failed or was never attempted, then `trec activities` lists it with the command to retry and `trec doctor` counts it.
- AC-7: Given a pass of several meetings fails, then its meetings are re-run one at a time, and only a meeting that fails alone gets an error file, a failed attempt and a notification; one bad meeting never uses up its batch-mates' attempts.

Edge cases:

- EC-1: The daemon dies mid-pass → no partial document; the meeting is picked up by the next pass.
- EC-2: A write fails (disk full, transient file error) → the document, the base, the archive and the versions are as they were before the pass, error recorded.
- EC-3: The daemon is killed in the instant of committing → the next pass finishes or rolls back that commit first; no archive entry is ever missing and the curator never mistakes its own lines for mine, even if I edited the file between the kill and the next pass.

### US-012: Editing during a pass

**As** Felipe, **I want** to keep editing while the curator works, **so that** I never wait for it.

Acceptance criteria:

- AC-1: Given I save the file while a pass is running, then the pass applies its edits to the file as it is when the answer arrives, and my edits outside the touched lines are kept byte for byte.
- AC-2: Given my edit removed a line a pass edit targets, then that edit fails and goes to the one retry; my edit wins.
- AC-3: Given the next pass, then it sees my edits made during the previous pass as my edits, each once (a line I typed in the box counts once), and nothing the curator or the app wrote as mine.
- AC-4: Given I typed a line in the box during a pass, then it is still in the document afterwards.

## Analysis

### US-013: Progress in the minutes

**As** Felipe, **I want** the minutes to list the progress reported in the meeting, **so that** I can check it against the transcript.

Acceptance criteria:

- AC-1: Given a meeting with progress statements, then `minutes.md` has a section `🔄 Andamento informado`, one line per statement: who, change, about, the quote, `[hh:mm:ss]`.
- AC-2: Given a statement the verifier did not confirm, then it carries ⚠️ and the reason.

Edge cases:

- EC-1: A new commitment is listed as an action, not as progress.
- EC-2: A meeting analyzed before this change has no such section and is still curated.

## Stories

### US-014: Stories on demand

**As** Felipe, **I want** a story only for items I tag `#história`, **so that** not every activity becomes a story.

Acceptance criteria:

- AC-1: Given an item line containing `#história`, when I run `trec stories`, then a draft is written into today's drafts and the tag is replaced by `história: [rascunho dd/mm](../plans/<dia>.stories.md)`.
- AC-2: Given the writer judges it a duplicate of a recent story, then the tag becomes `história: já existe ("<título>")`.
- AC-3: Given the writer skips it, then the tag stays and the CLI prints the reason.
- AC-4: Given `trec publish`, then it works on these drafts as before, on any day, with no plan file (the drafts document is re-rendered from what `*.stories.json` stores).
- AC-5: Given no meeting is processed, then no story is ever drafted automatically.

Edge cases:

- EC-1: No tagged line → `nothing tagged #história` and exit 0.
- EC-2: I edited the tagged line while the writer ran → tag stays; the CLI prints the draft path.
- EC-3: Today's drafts already exist → the new drafts are added; existing story numbers are stable for `publish --only`.
- EC-4: The curator is running → `trec stories` never waits for it: it drafts, saves the drafts and says `The curator is working; the drafts are saved. Run trec stories again later to replace the tags.` (exit 0); the next `trec stories` replaces those tags first. A tagged line that already has a story or a skip in the recent drafts is never drafted again, however many times I run `trec stories` meanwhile.
- EC-5: `[stories] publish = true` → the drafts are published right after drafting, as before; the default is false.

## Operation

### US-015: Meetings ending together

**As** the operator, **I want** meetings analyzed close together to be curated in one pass, **so that** fewer calls run and none conflict.

Acceptance criteria:

- AC-1: Given three meetings finished analysis while a pass ran, then the next pass curates them together, oldest first.
- AC-2: Given one pass at a time, then two passes never write the document concurrently.

Edge cases:

- EC-1: More than four queued → four per pass, the rest in the following pass.
- EC-2: A pass of several meetings fails → they are re-run one at a time before any failure is counted (US-011 AC-7).

### US-016: Rerun and bootstrap

**As** the operator, **I want** to rerun one meeting or build the first document from past meetings, **so that** I can recover and start with history.

Acceptance criteria:

- AC-1: Given `trec activities curate <id>`, then that meeting is curated now and its error file cleared on success.
- AC-2: Given `trec activities curate --since 2026-10-05`, then I see how many meetings and passes it will run and confirm `[y/N]`; on yes, passes run chronologically, up to four same-day meetings each.
- AC-3: Given a rerun of an already curated meeting, then no duplicates appear.
- AC-4: Given `trec analyze <id>` (or `trec analyze` for every pending meeting) finished, then the meetings analyzed are curated right after, in batches of four, unless `[activities] enabled = false`; a curation failure is reported on its own line and does not change the exit code of the analysis.

Edge cases:

- EC-1: An id that is not analyzed → error naming the meeting's state, exit 1.
- EC-2: A pass is running → the command prints `waiting for the curator…` and waits.

### US-017: `trec activities`

**As** Felipe, **I want** a command that shows the focus and opens the file, **so that** I can check status from the terminal.

Acceptance criteria:

- AC-1: Given the document exists, then `trec activities` prints its path, the focus, open-item counts per section, the last pass time and summary.
- AC-2: Given meetings not curated (failed or never attempted), then each is listed with its reason and `→ trec activities curate <id>`.
- AC-3: Given `--open`, then the file opens in the default `.md` application.

Edge cases:

- EC-1: No document yet → says so and suggests `trec activities curate --since <date>`.

## Migration

### US-018: The planner is gone

**As** the operator, **I want** the 18:00 planner removed cleanly, **so that** nothing runs or fails at 18:00.

Acceptance criteria:

- AC-1: Given the planner job is installed, when I run `trec agent install`, `trec agent restart` or `trec agent uninstall`, then the `local.teams-recorder.planner` job (Windows: the planner task) is removed.
- AC-2: Given `trec plan`, then the command no longer exists.
- AC-3: Given old audio past retention, then the daemon purges it once a day; `trec purge` still works.
- AC-4: Given `data/plans/*.md` and `open_actions.json`, then they stay on disk and are no longer read.
- AC-5: Given the old `[planner] retention_days` key, then it is still honoured until moved to `[audio]`.
- AC-6: Given I run the installer scripts, then they no longer offer or announce the 6 pm planner and remove an installed one.
- AC-7: Given the daemon's first tick of a day coincides with a call, then the purge runs in the background and the recording starts as usual.

## Notifications

### US-019: Notify only what concerns me

**As** Felipe, **I want** a notification only when a pass changed something of mine, **so that** notifications keep meaning something.

Acceptance criteria:

- AC-1: Given a pass added an action of mine, a 💬, a changed date of mine, or removed an item other than a ticked one, then I get the notification `Activities updated` whose body is the curator's one-line summary (in Portuguese).
- AC-2: Given a pass that only touched others' items or context, then no notification.
- AC-3: Given a failed pass, then I get `Activity curation failed` naming the meeting.

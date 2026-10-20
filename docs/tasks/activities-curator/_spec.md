# Spec: Activities curator

> Slug `activities-curator` · Date 2026-10-19 · Status: approved (2026-10-19, after five review rounds; reviews-001 to reviews-005 resolved)
> Direction approved by the user in conversation on 2026-10-19 (decisions listed under Assumptions and Defaults); design iterated through two designer/critic rounds.
> Visual flow: https://claude.ai/artifact/V6xTTuxTuGvW7wJS3MLW5m
> Companions: [user stories](_user_stories.md) · [developer experience](_dx.md) · [tests](_tests.md) · [ADR-001](adrs/adr-001.md) · [ADR-002](adrs/adr-002.md) · [ADR-003](adrs/adr-003.md)

---

# Part I — Product

## Overview

- **Motivating Problem**: the user's tasks are scattered across one daily plan per day, per-meeting minutes, story drafts and an invisible `open_actions.json`, and work from previous days disappears from view while still unfinished. Verified causes: the plan has no section for an open action that is neither new nor overdue (an undated action never reappears); an overdue action is shown once and then vanishes (`is_overdue_on` requires `OPEN` while the merge stores `OVERDUE`); others' actions never accumulate; meetings analyzed after 18:00 enter no plan; only the model can close an action. The simplest end-to-end behavior that solves it: minutes after each meeting is analyzed, one Markdown document, `data/activities/atividades.md`, lists everything still open for the user (own actions, what they wait on from others, dates, recent context), each line linked to its meeting, and stays there until the user ticks it.
- **Who it is for**: the single user of teams-recorder, who has many Teams meetings a day in Brazilian Portuguese and opens the document in VS Code.
- **Why it is valuable**: one place to look, current within minutes of each meeting, no daily ritual, nothing disappears without the user's decision. Not every meeting activity is a task or a story, so the document also keeps decisions, questions, risks and ownerless items, and stories become an explicit request.

## Goals

- The user sees every unfinished item from any past day in one document, with where it came from, without running a command.
- The system guarantees that an open item leaves the document only by being archived with a reason, and that only the user ticks or unticks an item.
- The user's edits and own lines are never overwritten; what a meeting says about existing work arrives as a quoted suggestion on that item.
- The 18:00 planner, the daily plan file and automatic story drafting become unnecessary and are removed; a story is drafted only for an item the user tags.

## User Stories

- US-001 to US-004: the document (one current place, provenance, focus, non-task context).
- US-005: progress reported in meetings.
- US-006 to US-007: ownership (only the user closes; the user's edits stand).
- US-008 to US-009: retention (archive, staying short).
- US-010 to US-012: safety (undo, atomic failures and automatic retry, editing during a pass).
- US-013: progress in the minutes.
- US-014: stories on demand.
- US-015 to US-017: operation (coalescing, rerun and bootstrap, `trec activities`).
- US-018: migration (planner removed).
- US-019: notifications.
- [Full user stories](_user_stories.md)

## Core Features

- **Progress extraction (analyzer).** The existing analysis call additionally extracts what the meeting said about pre-existing work (done, in progress, blocked, delayed, date changed, reassigned, cancelled), with who, the literal quote and the time, and who each of the user's actions is for. It never sees the activities document. The verifier checks each statement; the minutes list them.
- **Curator agent.** After each analyzed meeting (or a batch of up to four that finished together), one call receives the current document, the new analyses, transcript excerpts around each progress statement, a 14-day calendar, the user's edits since the last pass and recent archive entries, and returns edits to the document plus a focus, a summary and whether to notify. It decides everything: what is new, what matches what, where it goes, what leaves, what is the focus.
- **The document.** Five blocks: a box rewritten every pass (update time + focus), `## Minhas ações`, `## Aguardando outros`, `## Agenda e prazos`, `## Contexto recente`, then a link block. Three markers: 💬 suggestion, ⚠️ not confirmed, 💤 not mentioned for about three weeks.
- **Plumbing.** Applies the curator's edits to the file as it is when the answer arrives, enforces one rule (only archiving removes a checkbox line; only the user changes a box), writes in a recoverable order (the box carries a pass stamp that tells a reconciling lock whether the document was replaced), keeps versions, appends the archive, logs the pass, notifies, retries failed meetings in later passes and rebuilds the queue after a restart. Serialises passes with an OS file lock.
- **CLI.** `trec activities [--open]`, `trec activities undo`, `trec activities curate <id>… | --since`, `trec stories` (tag-based).
- **Stories on demand.** Items tagged `#história` are sent, as written, with their meetings' analyses, to the existing story writer; the tag is replaced with a link to the draft.
- **Planner removal.** `trec plan`, the 18:00 job, the daily plan and the open-actions list are removed; audio retention moves to the daemon.

Interaction: analysis → curator pass → document; the user edits the document; the next pass reads those edits; `trec stories` reads tagged blocks from the document and writes back the tag replacement.

## Business Rules

- **Completion.** Only the user changes a checkbox state. The curator never ticks, unticks, or archives an open item because a meeting says it is done, cancelled or reassigned; it adds a 💬 sub-line with who, meeting, `hh:mm:ss`, the literal quote and a question.
- **Open-line rule (the one code rule).** In one sentence: the curator can add and change items, but only an `archive` (with a reason) takes a checkbox line away, and only the user changes a box. Code checks it edit by edit, on the document body (box and link block excluded), where `open(x)` counts lines matching `^\s*[-*+] \[ \] ` and `ticked(x)` lines matching `^\s*[-*+] \[[xX]\] `: a `replace` must leave at least as many open lines as its target had and exactly as many ticked ones (so it can neither drop a checkbox line nor tick or untick one); an `insert_after` text holds no ticked line; a `move` relocates lines byte for byte, so it changes no box and no count; `archive` is the only edit that removes a checkbox line. The text after the checkbox may change freely (date, owner, links, 💤). The rule guards checkbox state and count, not line identity: a `replace` that turns one open line into another of the same count passes, and line identity is a prompt rule measured by Q-002 (which is why a reorder is a `move`, never a `replace` that re-emits the lines it passes). A failing edit is reported to the one repair round with the reason. Lines no edit targets are preserved byte for byte by `apply_ops` itself (Safety Invariant 4), so there is no second check over the whole document.
- **User's hand wins.** Lines the user wrote or changed are never reworded, moved, archived, marked 💤 or given links on their main line by the curator (a sub-line may be added: a meeting that mentions a user line becomes a sub-line `citado em <link>`). The curator never rewrites the main text of any existing line; only date, owner or priority fields change, on lines it wrote, with a change note `prazo mudou de <antes> para <depois> (<reunião dd/mm>, hh:mm:ss)`. Information goes in sub-lines.
- **Typed in the box.** A line the user types inside the box is never discarded: the pass moves it to the right section; if neither the pass nor the user did, the app puts it at the top of `## Minhas ações` and the next pass treats it as a normal user line.
- **Ticked items.** A tick the user made gets ` ✔ <ddd dd/mm>` and moves to the bottom of its section at the next pass (the only user change the curator acts on); it is archived (`concluído`) once ticked before the previous working day.
- **Deleted items.** An item the user deleted is archived as `removido por você` and is not re-added unless a new meeting brings a new fact. If most of the last pass's additions vanish at once with no other nearby edit, it is treated as an editor overwrite: the items are re-inserted with 💬 `voltou: parece que o editor sobrescreveu; apague de novo se não vale` and the user is notified.
- **Never delete.** Everything that leaves goes to `arquivo/<AAAA-MM>.md` with date and reason. Open items are never archived for age; an open item the curator wrote gets 💤 and sinks after about three weeks without mention (user lines are exempt: they have no meeting to mention them). Past agenda entries are archived the next day; context entries 7 days after their last mention or when answered/resolved; duplicates after merging links into the older item. When a duplicate involves a user line, the user's line survives.
- **Routing.** User's actions and deadlines → Minhas ações. Others' actions the user depends on → Aguardando outros, as checkboxes. Others' actions that do not affect the user → not in the document. Dated meetings and milestones not owned by the user → Agenda e prazos. Decisions, open questions, risks, ownerless actions affecting the user → Contexto recente (≈10 lines).
- **Progress scope.** A statement by X touches only items owned by X or waiting on X; `who = indefinido` → 💬 only. An intention is not progress. `in_progress` adds a sub-line only with a concrete remainder.
- **Unconfirmed claims.** Items and statements the verifier did not confirm carry ⚠️ with the reason and enter the focus only when overdue; every item from a degraded transcript carries ⚠️.
- **Format.** Item lines carry absolute dates with weekday only; the box may use relative words but always next to an absolute date. At most two sub-lines per item; on lines the curator wrote, the main line carries the origin link plus the two latest mention links; on a user line, mentions are a sub-line. Links are reference-style with the meeting id as label.
- **Repeat safety.** Items whose origin link is the meeting being curated are recognised as already present (rerun).
- **Focus.** 3–5 lines: overdue; due today or next working day; what unblocks someone; stated high priority; today's meetings needing preparation.
- **Notification.** Only when the pass added an action of the user's, a 💬, changed a date of the user's, removed an item other than by tick, or suspected an overwrite; always on failure.
- **Stories.** Drafted only for lines tagged `#história`, only via `trec stories`. A tagged line already in the recent drafts (as a story or as a skipped block) is never sent to the writer again; its tag replacement is retried by every run until it applies.
- **Batching.** Up to 4 meetings per pass, oldest first. When a pass of several meetings fails, the meetings are re-run one at a time before any failure is counted, so a meeting that keeps failing never costs its batch-mates an attempt.
- **Recovery.** A meeting analyzed within the last 2 working days (the meeting's own date, `Meeting.day`, decides the window, with status ANALYZED — the same reading the old planner used; today is day 0, so on a Monday the window starts Thursday 00:00 and on a Saturday or Sunday it starts the Thursday before 00:00; Monday to Friday, holidays ignored) with no successful pass is added to the next pass, and the daemon queues all of them when it starts, so a pass lost to a restart is rebuilt. A meeting is no longer added automatically after 2 failed attempts (attempts are counted only for a meeting curated alone). `trec activities` and `trec doctor` list every meeting analyzed in the last 10 working days (same convention) with no successful pass, whether it failed or was never attempted, with its retry command.
- **Empty analysis.** No actions, statements, deadlines, decisions, questions, risks or next meetings → no call.
- **Defaults.** effort `medium`; versions kept 50; Contexto 7 days; 💤 after ≈3 weeks (model judgment against the calendar); bootstrap window 10 working days.

## User Experience

- Persona: Felipe; operator (same person). See `_user_stories.md`.
- Daily flow: meetings happen → minutes later the document updates → a notification when something concerns him → he opens `atividades.md` in VS Code (or `trec activities --open`), reads the focus, ticks what is done, writes his own lines → next pass respects them.
- First run: `trec activities curate --since <10 working days ago>` builds the document from past meetings, with a confirmation showing meetings, passes and estimated time.
- Discoverability: `trec doctor` and `trec status` show the document and failed meetings; `trec activities` lists retry commands; the box header says when it was last updated.
- Accessibility: plain Markdown; markers are emoji plus words (`a confirmar`, `sem menção desde`) so meaning never depends on the emoji alone.

## High-Level Technical Constraints

- Runs with the existing LLM provider choice (`api` or `claude-code`), through the shared transport; no new external service.
- Everything stays on the Mac under `data/`; the document must not live in iCloud/Documents (TCC, AGENTS.md).
- A pass must never block recording, transcription or analysis; it runs after the analysis is saved.
- Operator manageability: every state is inspectable as files (document, archive, versions, pass log, error file) and every recovery is a CLI verb.
- No extension surfaces exist in this project.

## Non-Goals (Out of Scope)

- A deterministic task store (task ids, ingestion markers, fuzzy matching, code-ranked focus): rejected by the user (ADR-001).
- A scheduled daily pass, morning or evening (ADR-002); the box uses absolute dates instead.
- Phone access, Obsidian-specific features, Microsoft To Do or any other sync target.
- Reading board approvals back into the document.
- A GUI.
- Automatic story drafting or task-card routing.
- Migrating `open_actions.json` or old plans into the document (the bootstrap rebuilds from analyses).

## Open Questions

- None blocking. Evaluation thresholds (Part II › Testing Approach) may be tuned after the first sequence run; the user decides go/no-go after the shadow week.
- Resolved 2026-10-20: the user decided **go** ("pode remover o plano das 18h"), waiving the full shadow week (Q-003) and not running Q-001/Q-002 (they need approval and spend the subscription). Bootstrap evidence: 9 passes over 19 meetings, 0 edits on reruns. Slice 2 (tasks 13 to 15) is unblocked; see `task_12.md` › Completion Notes.

---

# Part II — Technical

## Executive Summary

A new post-analysis step runs a curator agent over a living Markdown file. The agent returns Edit-tool-shaped operations (`replace`, `insert_after`, `move`, `archive`) whose targets are whole lines of the document; code re-reads the file under an OS lock, applies the operations in order in memory, checks the checkbox rule edit by edit, and commits with a recoverable write order: version files, archive entries, the document (its box carries the pass stamp), a `base.md` snapshot (so the next pass sees the user's edits as a diff of the body) and a pass-log line. Judgment lives entirely in `prompts/curate_system.md`; code never parses item lines. The analyzer gains `status_updates` and `for_whom`, verified like other claims. The daily planner, its plan files, the open-actions list and automatic story drafting are removed; `trec stories` drafts from `#história`-tagged blocks.

Primary trade-offs: edit operations instead of a whole-document rewrite (no drift on untouched text, small output) at the cost of target-matching retries (ADR-001); the lock is held through the LLM call (simple serialisation) while undo and stories avoid waiting on it.

## MVP Boundary

Slice 1 delivers the Motivating Problem: analyzer `status_updates` + `for_whom` + minutes section, the curator step with the document, archive, versions, lock, checkbox rule, retry, notification, `trec activities` and `trec activities curate`, running in the daemon after each analysis while the planner still runs (shadow). Slice 2: `trec activities undo`, the recovery rule (working-day window, queue rebuilt at daemon start, not-curated listing), `trec doctor`/`trec status` lines. Slice 3: planner removal and migration (ADR-002), `PublishUserStories` and its helpers moved to `use_cases/stories.py` without plan input, purge in the daemon, config changes. Slice 4: tag-based `trec stories`. Post-MVP: Obsidian specifics. Out of scope: see Non-Goals.

## Developer Experience

- [Developer experience contract](_dx.md) — the document and archive formats, minutes section, CLI (`activities`, `activities curate`, `activities undo`, `stories`, removed `plan`, agent/doctor/status changes), config, notifications, errors.

## System Architecture

```
daemon job thread ── Pipeline.process ──► AnalyzeMeeting (+ status_updates, for_whom, verifier STATUS_UPDATE)
   (Container.pipeline(after_analysis=worker.enqueue))
                                      └─► after_analysis(meeting_id)  ──► CuratorWorker.enqueue (non-blocking)
Daemon (owns the worker): start → _resume_pending → enqueue CurateMeetings.pending()   # rebuilds a queue lost to a restart
CuratorWorker daemon thread: queue.get() → drain ≤3 more → + pending (today and the 2 previous working days, <2 failed attempts) → CurateMeetings.execute(ids)
                        stop: Daemon.shutdown → worker.request_stop(); an in-flight LLM call is not awaited, an abandoned pass is rebuilt by pending() at the next start
trec analyze          : cli.analyze does not use Pipeline; after its analysis loop it calls CurateMeetings.execute on the ids
                        analyzed OK, in batches of 4 oldest first (skipped when [activities] enabled = false)
trec activities curate: CurateMeetings inline (blocking lock; prints `waiting for the curator…` through on_wait)

CurateMeetings: ActivityStore.lock() ─┬─ store reconciles an interrupted commit: a stamp present in the document and equal to `box_stamp(_after)` → roll forward, else roll back, then
                                      ├─ read document F, base B, recent archive, pass log; user_edits = last during_edits + diff(body(B), body(F))
                                      ├─ build CuratorInput (document, analyses + excerpts, calendar, user_edits, archive, last summary)
                                      ├─ ActivityCurator.curate(input) → CuratorOutput                 [LLM]
                                      ├─ re-read F' ; apply_ops(fmt, F', ops) → W1 + failures (target, anchor and checkbox-rule failures)
                                      ├─ on failures: ActivityCurator.repair(...) once → apply to W1 again  [LLM]
                                      ├─ B' = render_links(render_box(W, focus, meetings, now, stamp=version))  → base for the next pass
                                      ├─ written = rescue_box_lines(B', lines the user had typed in the old box)
                                      ├─ during_edits = unified_diff(body(F), body(F'))  (what the user did to the body during the call)
                                      └─ ActivityStore.commit(F', written, archived, B', record)
                                         (version files → archive → document atomic (carries the stamp) → base → pass log = commit point) ; notify
A failed pass of several meetings re-runs them one at a time before any attempt is counted.
```

Components:
- `domain/activities.py` (pure; imports no `messages` or `constants`): `DocFormat`, `apply_ops`, `open_count`, `ticked_count`, `body_span`, `body_text`, `box_stamp`, `render_box`, `rescue_box_lines`, `render_links`, `calendar_strip`, `working_days_ago`, `unified_diff`, `tagged_blocks`, `replace_tag`, `Op`, `OpFailure`, `Applied`, `MeetingContext`, `CuratorInput`, `CuratorOutput`, `PassRecord` and the small types listed under Core Interfaces.
- `domain/excerpts.py` (pure): `excerpt_window`, the transcript windowing shared by the verifier and the curator.
- `application/use_cases/activities.py`: `doc_format()` (builds the `DocFormat` from `messages.ActivityDoc`, `constants.Parse`, `constants.Activities.SKELETON_STAMP`, `constants.Files.RECORDINGS_DIR` and `domain.status.MINUTES`), `CurateMeetings`, `UndoLastPass`, `ActivitiesSummary`.
- `application/use_cases/stories.py`: `DraftStoriesFromTags`, `PublishUserStories` with its report types, `recent_stories`, `stories_waiting`, `untrusted_sources` (moved out of the deleted `planning.py`; none of them reads a plan).
- `application/use_cases/retention.py`: `PurgeOldAudio` (moved out of the deleted `planning.py`).
- `adapters/outbound/curator_claude.py`: `ClaudeCurator` over `StructuredTransport` (schema `CuratorOut`, message builder).
- `adapters/outbound/activities_fs.py`: `FsActivityStore` (flock lock, atomic writes via `retry_io`, versions, archive, base, pass log, commit reconciliation).
- `adapters/inbound/daemon.py`: `CuratorWorker` (one daemon thread, `queue.Queue`, `request_stop()`), owned and started by `Daemon`; the daily purge scheduled from the first tick of each day.
- `container.py`: builds `ClaudeCurator`, `FsActivityStore` and the `CurateMeetings` use case (`curate_meetings()`, like `analyze_meeting()`); `pipeline(after_analysis=None)` takes the hook; removes planner wiring. It never imports `daemon.py`.

## Architectural Boundaries

- `domain/activities.py` imports only the standard library and `domain` types; no I/O. It imports neither `messages` nor `constants`: every marker, heading, weekday name, `(hoje)`, header label, link target and checkbox regex it writes or recognises arrives in a frozen `DocFormat`, its first argument, which `application/use_cases/activities.doc_format()` builds from `messages.ActivityDoc`, `constants.Parse`, `constants.Files.RECORDINGS_DIR` and `domain.status.MINUTES`; the folder name is never a literal in the domain. Tests build the same object from the real constants, so `test_no_hardcoded_strings` stays green with no allowance and AGENTS.md needs no import exception.
- `application/use_cases/activities.py` imports `domain` and `application/ports`; never adapters.
- `curator_claude.py` may import `llm_schema` helpers and `llm_transport` (the allowed LLM-stack exception); nothing else from other adapters. Transcript excerpts are built in the application layer from `domain/excerpts.excerpt_window`, which `verifier_claude.transcript_for` also reuses; there is no adapter-to-adapter import.
- `activities_fs.py` uses `fs_retry.retry_io` and `repository_fs._write_atomic`-equivalent atomic write (moved to `fs_retry` or duplicated as `atomic_write`; see Key Decisions).
- `container.py` remains the only place that instantiates `ClaudeCurator`, `FsActivityStore` and `CurateMeetings`; the inbound adapters consume the container, so `Daemon` builds its own `CuratorWorker` from `container.curate_meetings()` and passes `worker.enqueue` to `Container.pipeline(after_analysis=…)` in `_finish_call` and `_resume_pending`. `container.py` never imports `daemon.py` (the daemon already imports the container).
- Strings: every CLI/notification/log/error text in `messages.py` (`Cli`, `Notify`, `Log`, `Err`); Portuguese document labels in `messages.ActivityDoc`; file names, regexes and defaults in `constants.py` (`Files`, `Parse`, `Activities`, `Audio`, `Legacy`), except meeting-folder file names, which stay in `domain/status.py` (`CURATION_ERROR = "curation_error.txt"  # not part of status`). `tests/unit/test_no_hardcoded_strings.py` must stay green.

## Implementation Design

### Core Interfaces

```python
# domain/activities.py
class OpKind(StrEnum):
    REPLACE = "replace"
    INSERT_AFTER = "insert_after"
    MOVE = "move"
    ARCHIVE = "archive"

@dataclass(frozen=True)
class Op:
    kind: OpKind
    target: str                 # one or more whole lines, exactly as in the document (trailing whitespace ignored)
    text: str | None = None     # replace / insert_after; "" in replace removes the lines
    reason: str | None = None   # archive (Portuguese, shown in the archive)
    anchor: str | None = None   # move: one whole line, exactly as in the document; the target is pasted right after it, byte for byte
    refs: tuple[str, ...] = ()  # analysis refs it accounts for ("1.a1", "1.u2", …)

@dataclass(frozen=True)
class OpFailure:
    index: int                  # position of the op in the list of its round (first answer, or the repair answer)
    op: Op
    error: str                  # "not found" | "found N times" | "targets the box or link block" | "breaks the checkbox rule"
                                # | "anchor not found" | "anchor found N times" | "anchor inside the target" (move)
    detail: str = ""            # for the checkbox rule, the counts: "target: 2 open, 1 ticked; text: 1 open, 1 ticked"

@dataclass(frozen=True)
class Applied:
    text: str                   # the document after the ops that applied
    archived: tuple[str, ...]   # texts removed by archive ops, in order (with their reasons below)
    reasons: tuple[str, ...]
    failures: tuple[OpFailure, ...]

@dataclass(frozen=True)
class DocFormat:                      # all document text the pure functions write or recognise; built by application `doc_format()`
    box_start: str                    # "<!-- curador:início (reescrito a cada passada; escreva fora desta caixa) -->"
    box_end_prefix: str               # "<!-- curador:fim"
    box_end_suffix: str               # " -->": the closing marker is prefix + (" " + stamp when stamped) + suffix, e.g. "<!-- curador:fim 20261019-101200 -->"; render_box writes the stamp, readers (`box_stamp`, `body_span`) accept its absence ("<!-- curador:fim -->", only a user-edited or legacy file)
    skeleton_stamp: str               # "00000000-000000" (`constants.Activities.SKELETON_STAMP`): the fixed stamp of the skeleton's closing marker, never a pass version; so every document the app writes, and every `_after` the app produced for a pass, carries a stamp; an undo's `_after` (the restored `_before_N`) has none only when the user had removed the marker before pass N, and then reconcile rolls back
    links_start: str                  # "<!-- links:início (gerado automaticamente) -->"
    links_end: str
    link_target: str                  # "../recordings/{id}/minutes.md": render_links fills `{id}`; built by doc_format() from Files.RECORDINGS_DIR and status.MINUTES
    heading_actions: str              # "## Minhas ações", then waiting, agenda, context headings
    heading_waiting: str
    heading_agenda: str
    heading_context: str
    updated_label: str                # "Atualizado", "após", "Foco" in the box header
    after_label: str
    focus_label: str
    weekdays: tuple[str, ...]         # seg … dom (calendar_strip, box header)
    today_label: str                  # "(hoje)"
    open_re: str                      # the checkbox patterns of Business Rules
    ticked_re: str

def body_span(fmt: DocFormat, document: str) -> tuple[int, int]: ...          # char range excluding the box and the link block
def body_text(fmt: DocFormat, document: str) -> str: ...                       # the body: what diffs and targets are computed on
def box_stamp(fmt: DocFormat, document: str) -> str | None: ...                # the stamp in the box's closing marker, None when absent (only when the user deleted or rewrote the marker)
def apply_ops(fmt: DocFormat, document: str, ops: Sequence[Op]) -> Applied: ...  # in order; each target (and anchor) unique within the body of the current text
    # per-op checkbox rule, with open(x) / ticked(x) = counts of `- [ ] ` / `- [x] ` lines:
    #   replace      : open(text) >= open(target) and ticked(text) == ticked(target)
    #   insert_after : ticked(text) == 0
    #   move         : cuts the target lines and pastes them right after the anchor line, byte for byte: no count can change;
    #                  fails when the anchor is missing, ambiguous, in the box or link block, or inside the target
    #   archive      : unrestricted (the only op that removes a checkbox line)
    # a violation is an OpFailure and the op does not apply. The rule guards state and count, not line identity (Business Rules)
def open_count(fmt: DocFormat, text: str) -> int: ...
def ticked_count(fmt: DocFormat, text: str) -> int: ...
def render_box(fmt: DocFormat, document: str, focus: Sequence[str], meetings: Sequence[str], now: datetime, stamp: str, base: str | None = None) -> tuple[str, list[str]]:   # `base` = the document as the last pass left it: a numbered box line is generated only while one of base's focus lines is left to match it; any other is the user's
    """Rewrites the box, writing `stamp` (the pass version) into its closing marker; returns the new document and the
    lines the user had typed inside the old box."""
def rescue_box_lines(fmt: DocFormat, document: str, lines: Sequence[str]) -> str:
    """Puts each line (not already a line of the body) at the top of the `## Minhas ações` section, creating the
    heading right after the box when it is missing. No sub-line is added: the next pass treats them as user lines."""
def render_links(fmt: DocFormat, document: str, meeting_exists: Callable[[str], bool]) -> str: ...   # regenerates the link block from labels in use
def calendar_strip(fmt: DocFormat, today: date, days: int = 14) -> str: ...
def working_days_ago(today: date, n: int) -> date: ...         # today is day 0 and is not counted, even on a weekend; each step back lands on the previous Monday-Friday day, holidays ignored; n = 0 -> today
    # Mon 19/10 - 2 = Thu 15/10; Wed - 2 = Monday; Sat 24/10 - 2 = Thu 22/10 and Sun 25/10 - 2 = Thu 22/10 (Fri = 1, Thu = 2)
def unified_diff(base: str, current: str) -> str: ...          # callers pass bodies (`body_text`)
def tagged_blocks(document: str, tag: str) -> list[TaggedBlock]: ...    # line containing the tag + deeper-indented lines
def replace_tag(document: str, line: str, replacement: str) -> str | None: ...  # None when the line is not found exactly once

class PassKind(StrEnum):
    MEETING = "meeting"; UNDO = "undo"; SKIPPED_EMPTY = "skipped_empty"; FAILED = "failed"

@dataclass(frozen=True)
class MeetingContext:                      # built by CurateMeetings; the adapter only formats it
    meeting_id: str
    title: str
    analysis: Analysis
    health: TranscriptHealth | None
    excerpts: str                          # excerpt_window(transcript, times of the status updates, ±60 s, merged, speaker labels)

@dataclass(frozen=True)
class TaggedBlock:
    ref: str                               # "b1"… numbered per call
    lines: tuple[str, ...]                 # the tagged line + deeper-indented lines, verbatim
    labels: tuple[str, ...]                # meeting ids of the reference links in those lines

@dataclass(frozen=True)
class RemovedItem:
    text: str
    note: str

@dataclass(frozen=True)
class IgnoredRef:
    ref: str
    why: str

# domain/excerpts.py
def excerpt_window(transcript: Transcript, times: Sequence[float], window: float, gap: str, head_chars: int = 0) -> str:
    """Segment lines (`timestamped_line`) within ±window seconds of any time, in order, overlaps merged, `gap` where
    lines were left out; the first `head_chars` characters of the transcript are kept too (0 = none)."""

@dataclass(frozen=True)
class CuratorInput:
    document: str
    meetings: list[MeetingContext]        # oldest first
    calendar: str
    user_edits: str                        # the previous meeting/undo record's during_edits + unified diff of the bodies base → document; "" on first pass
    box_lines: list[str]                   # lines the user typed inside the box
    recent_archive: list[str]              # last 60 entries: header + first line
    last_summary: str | None
    today: datetime
    user_name: str

@dataclass(frozen=True)
class CuratorOutput:
    ops: list[Op]
    user_removed: list[RemovedItem]        # text + note; archived by code as "removido por você"
    focus: list[str]                       # 3–5 lines (Portuguese)
    summary: str                           # one line (Portuguese)
    notify: bool
    ignored: list[IgnoredRef]

@dataclass(frozen=True)
class PassRecord:
    ts: datetime
    kind: PassKind
    meetings: tuple[str, ...]
    ops_applied: int
    retried: bool
    retried_by_kind: dict[str, int]
    unaccounted_refs: tuple[str, ...]
    ignored: int
    user_removed: int
    box_rescued: int                       # lines typed in the box that code had to put back
    during_edits: str                      # unified diff of the bodies F → F': what the user changed in the body while the call ran (box lines are rescued, not diffed); "" if nothing; an undo record holds the undone pass's carried_edits
    summary: str
    version: str                           # versions/<version>_{before,after,base,prevbase}.md and <version>_pass.json; a meeting pass writes this string as the stamp in its box's closing marker; an undo record renders no box: its `_after` is the restored text, whose stamp (an earlier pass's, or the skeleton's `skeleton_stamp`) is what reconcile reads with `box_stamp(_after)`, never `version`; when the user had removed the marker before the undone pass, that text has no stamp and reconcile rolls the undo back
    archive_file: str | None
    archive_bytes_before: int | None
    archive_bytes_after: int | None        # archive size right after this pass's append (before + appended bytes, known before `_pass.json` is written); undo truncates only while the file still has this size
    carried_edits: str                     # the during_edits part of the user_edits this pass received; undoing this pass hands it on; "" on an undo record (an undo is never undone: UndoLastPass skips undo records)
    undoes: str | None                     # kind undo: the version of the pass it undid
    doc_chars: int
    error: str | None
```

```python
# domain/errors.py (TeamsRecorderError subclasses)
class CuratorBusy(TeamsRecorderError): ...     # the lock is held and the caller must not wait (undo)
class NothingToUndo(TeamsRecorderError): ...
class UndoStale(TeamsRecorderError): ...       # the last pass is not the one that was previewed
```

```python
# application/ports.py
class ActivityCurator(Protocol):
    def curate(self, data: CuratorInput) -> CuratorOutput: ...
    def repair(self, data: CuratorInput, current: str, failures: list[OpFailure]) -> list[Op]: ...
        # `current` is the in-memory text after the ops that applied; failures include checkbox-rule violations

class VersionFiles(NamedTuple):
    before: str; after: str; base: str | None; prevbase: str | None
        # `prevbase` = base.md as it was when the pass committed (the base the pass read); None when there was no base.md (the first pass).
        # None means the file does not exist: commit writes no `_base` / `_prevbase` file for it

class ActivityStore(Protocol):
    def lock(self, wait: bool = True) -> AbstractContextManager[bool]: ...   # yields False when wait=False and busy; on entry, reconciles an interrupted commit (forward only when `box_stamp(document)` is not None and equals `box_stamp(_after)`; a document with no stamp rolls back)
    def read_document(self) -> str | None: ...
    def read_base(self) -> str | None: ...
    def recent_archive(self, limit: int) -> list[str]: ...
    def commit(self, before: str, after: str, archived: list[tuple[str, str]], base: str | None, record: PassRecord) -> None: ...
        # used by passes and by undo (archived = []): all or nothing for document, base, archive and versions; builds the archive entries and
        # measures their sizes first, writes version files (`_prevbase` = base.md as it is; no file when base.md does not exist), archive, document, base.md, and the pass-log line last
        # = commit point (Safety Invariants 3, 6). `base=None` (undo of the first pass) deletes base.md and writes no `_base` file; reconcile rolling
        # forward a set with no `_base` file likewise deletes base.md, so the next pass sees no base and `user_edits` is "" as on a first pass
    def passes(self) -> list[PassRecord]: ...                                # a torn last JSONL line counts as absent
    def version(self, name: str) -> VersionFiles: ...
    def truncate_archive(self, record: PassRecord) -> bool: ...              # truncates record.archive_file to archive_bytes_before only while its size == archive_bytes_after; False when left in place
    def path(self) -> Path: ...

class MeetingRepository(Protocol):  # gains (the repository owns the meeting folder)
    def mark_curation_failed(self, meeting_id: str, message: str) -> None: ...   # recordings/<id>/curation_error.txt (status.CURATION_ERROR)
    def clear_curation_failed(self, meeting_id: str) -> None: ...
    def curation_error(self, meeting_id: str) -> str | None: ...
    # `curation_error.txt` is written atomically without the meeting `.lock`: no other step touches it and derive_status ignores it

class StoryWriter(Protocol):  # changed
    def draft_from_blocks(self, day: date, blocks: list[TaggedBlock], analyses: list[Analysis],
                          existing: list[UserStory]) -> StoryDrafts: ...

class StoryRenderer(Protocol):  # changed: `actions` is dropped and nothing transient is passed in
    def render(self, drafts: StoryDrafts, existing: list[UserStory],
               degraded: dict[str, TranscriptHealth] | None = None) -> str: ...
        # everything a document prints is persisted in `*.stories.json`: a block story prints `UserStory.source_text`, a skipped block prints
        # `SkippedAction.source_line`, a story drafted by the old planner prints its stored meetings only. `degraded` comes from the stories'
        # `source_meetings` (`untrusted_sources`), so `PublishUserStories` re-renders after each publication with no plan and no block refs
```

```python
# application/use_cases/activities.py
@dataclass(frozen=True)
class NotCurated:
    meeting_id: str
    title: str
    reason: str | None                    # curation_error.txt text; None = never attempted

@dataclass(frozen=True)
class PassResult:
    records: tuple[PassRecord, ...]       # every pass that ran (a failed batch and its single-meeting re-runs each leave one)
    curated: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]   # (meeting_id, reason)
    summary: str | None                   # one-line summary of the last successful pass
    edits: int                            # ops applied over the successful passes

@dataclass
class CurateMeetings:
    repo: MeetingRepository
    store: ActivityStore
    curator: ActivityCurator
    notifier: Notifier
    clock: Clock
    user_name: str = ""
    notify: bool = True
    def execute(self, meeting_ids: list[str], wait: bool = True, on_wait: Callable[[], None] | None = None) -> PassResult: ...
        # takes the lock without blocking first; when busy and wait=True, calls on_wait() once, then blocks.
        # builds MeetingContext.excerpts from repo transcripts. A failed pass of several meetings is re-run one meeting
        # at a time; only a failed single-meeting pass is recorded as that meeting's failure (error file, notification).
    def pending(self, max_attempts: int = 2, working_days: int = 2) -> list[str]: ...
        # analyzed since 00:00 of working_days_ago(today, working_days), no successful pass (kind meeting or
        # skipped_empty lists it), fewer than max_attempts failed single-meeting records; oldest first
    def not_curated(self, working_days: int = 10) -> list[NotCurated]: ...   # same test over 10 working days, attempts ignored

@dataclass
class UndoLastPass:
    store: ActivityStore
    clock: Clock
    def preview(self) -> UndoPreview | None: ...      # UndoPreview(version, record, diff now→before, edited_after, archive_stays)
    def execute(self, expected_version: str) -> UndoResult: ...   # non-blocking lock; raises CuratorBusy, NothingToUndo, UndoStale
        # undo is a commit (ADR-003): `store.commit(current, N.before, [], N.prevbase, undo_record)` restores the document, then base.md to the base
        # pass N started from, then the pass-log line; the undo record has kind undo, undoes = N's version, during_edits = N.carried_edits, carried_edits = "".
        # N.prevbase is None when N was the first pass: base.md is then deleted (`commit(..., base=None, ...)`), not set to "".
        # Then `store.truncate_archive(N)` (last: a stop before it leaves surplus archive entries, never missing ones).
        # UndoResult(version, archive_left_in_place, meetings)

@dataclass(frozen=True)
class TagDraftResult:
    drafts_path: Path | None
    stories: tuple[UserStory, ...]
    skipped: tuple[SkippedAction, ...]    # new skips and stored ones re-reported; `source_line` holds the tagged line
    replaced: int                         # tags replaced now
    deferred: int                         # tags not replaced because the curator held the lock; the next run replaces them
    edited: int                           # tagged lines edited meanwhile: tag stays
    nothing_tagged: bool

@dataclass
class DraftStoriesFromTags:               # application/use_cases/stories.py
    repo: MeetingRepository
    store: ActivityStore
    writer: StoryWriter
    renderer: StoryRenderer
    clock: Clock
    dedup_days: int
    def execute(self) -> TagDraftResult: ...
        # 1. read the tagged blocks from the document. 2. Split them: a block whose tagged line is the first line of a stored
        # `UserStory.source_text`, or equals a stored `SkippedAction.source_line`, in the recent drafts (today included: `recent_story_drafts(
        # before=tomorrow, days=dedup_days + 1)`) is already handled and is never sent to the writer again. 3. Writer call for the rest,
        # without the lock. 4. Save the drafts (merged into today's, numbering kept). 5. `lock(wait=False)`: replace the tag of every handled
        # block (its story → `história: [rascunho dd/mm](../plans/<day>.stories.md)` with the day of the drafts file that holds it; a skip
        # with `duplicate_of` → `história: já existe ("<título>")`; any other skip keeps the tag and is printed again from the stored entry)
        # where its line is found exactly once in the document, and in base.md; busy → report `deferred`, exit normally.
        # Nothing else is persisted: the drafts file is the memory, so a rerun retries step 5 and never repeats step 3.

@dataclass(frozen=True)
class ActivitiesStatus:
    path: Path
    exists: bool
    updated: datetime | None              # ts of the last meeting/undo pass
    titles: tuple[str, ...]               # meeting titles of that pass
    focus: tuple[str, ...]                # read from the box between its markers
    counts: dict[str, int]                # per messages.ActivityDoc heading: open checkboxes (agenda and context: lines)
    last_pass: PassRecord | None
    not_curated: tuple[NotCurated, ...]

@dataclass
class ActivitiesSummary:                  # backs `trec activities`, `trec doctor`, `trec status`
    repo: MeetingRepository
    store: ActivityStore
    curate: CurateMeetings
    def execute(self) -> ActivitiesStatus: ...
```

```python
# application/pipeline.py — Pipeline gains
after_analysis: Callable[[str], None] | None = None   # called once the meeting reaches ANALYZED; failures logged, never error.txt
# container.py: Container.pipeline(after_analysis: Callable[[str], None] | None = None) -> Pipeline
```

```python
# domain/models.py
class StatusChange(StrEnum):
    DONE = "done"; IN_PROGRESS = "in_progress"; BLOCKED = "blocked"; DELAYED = "delayed"
    DUE_CHANGED = "due_changed"; REASSIGNED = "reassigned"; CANCELLED = "cancelled"

@dataclass
class StatusUpdate:
    about: str
    change: StatusChange
    who: str                       # Llm.OWNER_SELF, a name, or Llm.OWNER_UNKNOWN
    evidence: str                  # literal quote, ≤ 20 words, hedges kept
    at: str | None = None
    new_due: date | None = None
    new_owner: str | None = None
    verification: Verification | None = None

# Analysis gains: status_updates: list[StatusUpdate] = field(default_factory=list)
# Action gains:   for_whom: str | None = None
# ClaimKind gains: STATUS_UPDATE = "status_update"
# UserStory gains: source_text: str | None = None   # the tagged block, verbatim (None for stories drafted by the planner); its first line is the tagged line
# SkippedAction gains: source_line: str | None = None   # the tagged line verbatim, persisted (None on planner-era entries, which render by action_id and reason)
# UserStory.is_task_card becomes `self.kind in (ActionKind.TECHNICAL, ActionKind.OPERATION)`; ActionRoute/route_of are deleted
```

### Data Models

| Field | Type | Purpose |
| ----- | ---- | ------- |
| `analysis.status_updates[].about` | str | the work referred to, in the meeting's words, specific enough for the curator to match |
| `analysis.status_updates[].change` | `StatusChange` | done / in_progress / blocked / delayed / due_changed / reassigned / cancelled |
| `analysis.status_updates[].who` | str | whose work: `usuário`, a name, or `indefinido`; scopes which items the curator may touch |
| `analysis.status_updates[].evidence` | str (≤ 20 words) | literal quote shown in the 💬 sub-line and checked by the verifier |
| `analysis.status_updates[].at` | str `hh:mm:ss` \| null | where it was said; anchors the transcript excerpt and the 💬 timestamp |
| `analysis.status_updates[].new_due` | ISO date \| null | the new date for `due_changed`/`delayed` |
| `analysis.status_updates[].new_owner` | str \| null | the new owner for `reassigned` |
| `analysis.status_updates[].verification` | `Verification` \| absent | verifier verdict; unconfirmed → ⚠️ |
| `Claim` of kind `STATUS_UPDATE` (derived, not stored) | text, owner, due, at | `text = "<change>: <about> — \"<evidence>\""` (for `reassigned`: `"reassigned to <new_owner>: <about> — \"<evidence>\""`), `owner = who`, `due = new_due`, `at = at`: the verifier reads what changed, who said it, the new date and the quote, not only the topic |
| `analysis.{my,others}_actions[].for_whom` | str \| null | who receives or waits for the result (`p/ <quem>` on the line) |
| `PassRecord` (one JSONL line) | object | operational record of a pass for undo, recovery and diagnosis (fields in Core Interfaces) |
| `[activities] enabled` | bool, default `true` | run the curator after each analysis |
| `[activities] model` / `cli_model` | str, default analyzer's / `"opus"` | model per provider |
| `[activities] effort` | `Effort`, default `"medium"` | reasoning effort of the curator call |
| `[activities] notify` | bool, default `true` | send `Activities updated` when the curator says so |
| `[activities] keep_versions` | int, default `50` | passes kept for undo |
| `PassRecord.during_edits` | str (unified diff) | what the user changed in the body between the curator's snapshot F and the re-read F' (`unified_diff(body(F), body(F'))`); the next pass prepends it to `user_edits`; on an undo record, the undone pass's `carried_edits` |
| `PassRecord.box_rescued` | int | lines typed in the box that code put back at the top of `## Minhas ações` |
| `PassRecord.archive_bytes_after` | int \| null | archive size right after the pass's append; undo's check is `size(archive_file) == archive_bytes_after` |
| `PassRecord.carried_edits` / `undoes` | str / str \| null | the `during_edits` the pass started from (so an undo can hand it on; "" on an undo record); the version an undo record undid |
| `SkippedAction.source_line` | str \| null | the skipped block's tagged line, persisted so a later render and a later `trec stories` need no per-call refs |
| `UserStory.source_text` | str \| null | the tagged block verbatim; absent on stories drafted by the planner |
| `[audio] retention_days` | int, default `30` | audio purge age (fallback: `[planner] retention_days`) |

- `analysis.json` new keys are written only when non-empty/non-null and are absent on old files (codec defaults), so existing analyses load unchanged.
- `AnalysisOut` (`llm_schema.py`): `StatusUpdateOut` and `ActionOut.for_whom`, strict schema, field descriptions in `messages.Prompt`.
- Verifier: `domain/verification.claims`, `_claim_verification` and `with_verifications` get a `STATUS_UPDATE` branch keyed by position (like the other kinds), producing the claim above; `prompts/verify_system.md` gains two axes for this kind: does the quote support the stated change (an intention or plan is not `done`), and is the new date or new owner what was said. `due = new_due` lets the existing `date_said` axis apply to `due_changed` and `delayed`.
- `CuratorOut` (`curator_claude.py`, strict schema): `ops[{op, target, text|null, reason|null, anchor|null, refs[]}]`, `user_removed[{text, note}]`, `focus[str]`, `summary`, `notify`, `ignored[{ref, why}]`.
- Files (all under `<data_dir>`): `activities/atividades.md` (its box's closing marker carries the pass stamp `<!-- curador:fim 20261019-101200 -->`); `activities/arquivo/<AAAA-MM>.md` (append-only entries `### dd/mm/aaaa — <reason>` + verbatim text + link definitions with `../../recordings/…`); `activities/.curator/lock` (flock target, empty); `activities/.curator/base.md`; `activities/.curator/versions/<YYYYmmdd-HHMMSS>_{before,after,base,prevbase}.md` and `_pass.json` (the `PassRecord`, written before the archive append and the pass-log line; keep `keep_versions` passes); `log/activities.jsonl` (`PassRecord` per line, the commit point; a torn last line counts as absent); `recordings/<id>/curation_error.txt` (`status.CURATION_ERROR`, not part of `derive_status`, written through `MeetingRepository`).
- No side tables or databases: every state is a file (project rule). The pass log is JSONL, opaque operational data.
- Story drafts: `plans/<day>.stories.{md,json}` keep their shape plus `source_text` (stories) and `source_line` (skipped blocks); `DraftStoriesFromTags` loads the day's drafts and appends, keeping existing numbering. For a block story `source_action_ids` is empty, `source_text` is the tagged block verbatim and `source_meetings` are the link labels of the block; a skipped block is a `SkippedAction` whose `action_id` is the per-run block ref (`b1`…, never looked up after the call) and whose `source_line` is persistent. The writer sets `kind` (feature, bug, technical or operation; a block of another nature is skipped with the reason), `priority` and `due` from the block text and its meetings' analyses, or leaves them empty; `verification` stays empty. A story is a task card when its stored `kind` is technical or operation, so `*.stories.json` files written by the planner still load, render and publish. The renderer prints a block story's `source_text`, a skipped block's `source_line`, and for a planner-era story in the same file its stored meetings only (the actions are no longer loadable; its skipped entries print `action_id` and reason). `PublishUserStories` (in `use_cases/stories.py`) loads `*.stories.json` only: it re-renders with `renderer.render(drafts, existing, degraded)` after every publication, `degraded` from `untrusted_sources(repo, source meetings of the stories)`, and reads no plan; `Err.PLAN_MISSING` is deleted and a day without drafts keeps `Err.STORIES_MISSING`. `[stories] publish = true` still publishes right after `trec stories` drafts (default `false`).

### Curator message and prompt

User message, built by `curator_claude.build_user_message`, in this order (tags in English, content in Portuguese): `<document>` (as on disk) · `<meeting n id title when health>` blocks oldest first, refs `n.a1` (user's actions), `n.o1` (others' actions), `n.u1` (status updates), `n.p1` (deadlines), `n.n1` (next meetings), `n.d1` (decisions), `n.q1` (questions), `n.r1` (risks), each with `at` and `⚠️ unconfirmed: <reason>` · `<excerpts>` (±60 s around each status update, merged, with speaker labels) · `<calendar>` (14 days, weekdays, weekends bracketed, today marked) · `<user_edits>` (the previous pass's during-call edits, then the unified diff of the bodies `base.md` → document) · `<box_lines>` (lines the user typed in the box) · `<last_pass>` (previous summary) · `<recent_archive>` (60 entries) · `<task>` (checklist).

`prompts/curate_system.md` (normative content; English, asks for Portuguese output):

1. **Role.** You keep one Markdown document for one user: what they must do, what they wait on, their dates, recent context. You return edits; the app applies them and copies everything else unchanged. Address the user as "você"; never write "usuário".
2. **Edits.** `replace` (target = exact whole lines; text replaces them; `""` removes them), `insert_after` (target = one exact whole line), `move` (target = an exact whole item, main line plus sub-lines, `anchor` = one exact whole line: the app cuts the item and pastes it right after the anchor, byte for byte), `archive` (target = an exact whole item: main line + sub-lines; reason in Portuguese). Each target and anchor occurs exactly once in the document body. Anchor an `insert_after` on a section heading or on a main line: one of yours carrying a meeting id, or the user's line when you add a sub-line to it (`citado na …`, a 💬); never on a 💬 line. A `move` anchors on a section heading (the item goes first in its section) or on the last line of the destination section (it goes last). Use `move` for every reorder (a ticked item to the bottom of its section, a 💤 item sunk) and never a `replace` that re-emits lines it does not change. One op per change; ops apply in order, so list a `move` after any edit of the same item and target the item as that edit left it. The box and the link block are not yours: the app writes the box from `focus` and the link definitions from the labels you use. The app enforces one rule: only `archive` removes a checkbox line and no edit changes a box. Concretely, a `replace` must keep at least as many `- [ ]` lines as its target has and exactly as many `- [x]` lines, an `insert_after` text has no `- [x]` line, and a `move` can break nothing; the text after the checkbox may change (date, links, 💤). Merge duplicates with `archive`, never by `replace`. If a target or anchor is not found or the rule breaks, you get one chance to fix the failed edits, with the reason; otherwise the whole pass is discarded.
3. **Line format.** As in `_dx.md` (own action, `**Nome**: …` waiting line with a checkbox, agenda line without checkbox, `Decisão:`/`Pergunta:`/`Risco:`/`Sem dono:` context lines). Reference links `[<reunião curta> <dd/mm>][<meeting id>]`; on lines you wrote, origin first and at most two latest mentions on the main line; on a user line, a mention is a sub-line `- citado na [<reunião curta> <dd/mm>][<meeting id>]`. At most two sub-lines. Only 💬, ⚠️, 💤. Absolute dates with weekday from `<calendar>` on item lines.
4. **Principle 1 — the document is the truth; the user's hand wins.** Read `<user_edits>` first. Never undo, reword, move or recreate what the user wrote, reworded, moved or deleted. Never rewrite the main text of any existing line; new information goes into sub-lines; only date, owner or priority fields change, on lines you wrote, with a change note. Lines the user wrote may receive a sub-line, nothing else. Deleted items go to `user_removed`; add one back only when a new meeting brings a new fact. If most lines you added last pass vanished together with no other nearby edit, an editor overwrote the file: re-insert them with `💬 voltou: parece que o editor sobrescreveu; apague de novo se não vale`, say so in `summary`, set `notify`. Move each of `<box_lines>` into the right section, copied verbatim (`insert_after` anchored on the section heading); whatever is left in the box, the app puts at the top of `## Minhas ações`. The one user change you act on: a tick → append ` ✔ <ddd dd/mm>` and move the item to the bottom of its section. *(example)*
5. **Principle 2 — completion is the user's.** Never tick, untick or archive an open item because a meeting says it is done, cancelled or reassigned: add `- 💬 Na <reunião dd/mm> (hh:mm:ss) <quem> disse: "<citação>". Marque [x] se concluiu.` Keep hedges. Unconfirmed → also ⚠️. A statement by X touches only items owned by X or waiting on X; `indefinido` → 💬 only. `in_progress` only with a concrete remainder. *(example)*
6. **Principle 3 — same work in other words is one item.** Search the document and `<recent_archive>` under any wording, owner or section before adding. Update instead of adding. Archived and a new fact → add again with `voltou: arquivado em dd/mm (<motivo>)`. Items whose origin link is this meeting → it is a rerun: add nothing again. When a duplicate involves a user line, keep the user's line: `archive` yours (reason `duplicado de: <título>`) after putting its meeting in a `citado na …` sub-line of the user's line, or add `💬 parece duplicado de …`. Example of a mention on a user line: `{"op":"insert_after","target":"- [ ] Ligar para o suporte da VPN","text":"  - citado na [Daily 19/10][2026-10-19_09-30-11]","refs":["1.o2"]}`. *(example)*
7. **Principle 4 — never delete; keep it short.** Archive with reason: ticked before the previous working day (`concluído`); agenda dates passed (`data passou (<data>)`); context 7 days after last mention or when answered/resolved (say where); duplicates (`duplicado de: <título>`). Never archive an open item for age: on an open item you wrote, after about three weeks without mention append ` · 💤 sem menção desde <ddd dd/mm> — ainda vale?` and sink it (a `move` to the last line of its section); drop 💤 when mentioned again. Lines the user wrote are exempt: never 💤, never sunk, never given links on the main line (no meeting can mention a hand-written line, so 💤 would only mean "older than three weeks"). A third sub-line: drop your oldest superseded note or fold its meeting into the links; never drop a user sub-line. Keep Contexto at about ten lines. *(example)*
8. **Principle 5 — put each thing where the user looks.** Routing and ordering per Business Rules. Others' actions that do not affect the user → `ignored`. A status update matching nothing → `ignored`, unless it is a new blocker on the user's work (→ `Risco:`). ⚠️ for unconfirmed and for everything from a degraded transcript. An older meeting never overrides newer information. Every ref appears in some op's `refs` or in `ignored`. *(example)*
9. **Principle 6 — focus says what to do next.** 3–5 lines naming items in bold with why now (order per Business Rules); relative words allowed only next to an absolute date; unconfirmed only when overdue. `summary` one line; `notify` per Business Rules. *(example)*
10. **Worked example**: a full input excerpt (document with a user tick and an own line, one meeting with a1/o1/o2/u1/u2/d1, calendar) and the complete JSON answer (7 ops, focus, summary, notify, ignored), as drafted in the design rounds.
11. **`<task>` checklist** (end of the user message): (1) apply the user's edits and box lines; (2) add/update from each ref; (3) housekeeping: ticked items, past agenda, old context, 💤, sub-line limit; (4) every ref in `refs` or `ignored`; (5) targets copied exactly, body only; (6) no checkbox line removed or changed except by `archive` (reorders are `move` ops); (7) all content in Portuguese.

### API Endpoints

None (CLI only).

## Integration Points

- Claude via the existing `StructuredTransport` (`ApiTransport` with cached system prompt, or `ClaudeCodeTransport` with the 900 s timeout). Errors map to `AnalysisError` as today; a pass converts them to a failed `PassRecord`, `curation_error.txt` and a notification. No retry beyond the one op-repair call and the one-meeting-at-a-time re-run of a failed batch.
- macOS `open` / Windows `os.startfile` for `--open`.
- launchd/schtasks: only removal of the planner job.

## Impact Analysis

| Component | Impact Type | Description and Risk | Required Action |
| --------- | ----------- | -------------------- | --------------- |
| `prompts/analyze_system.md`, `llm_schema.py`, `codec.py`, `domain/models.py` | modified | new `status_updates`, `for_whom`; precision risk of false progress (medium) | cues + rules; fidelity eval gate before rollout B |
| `verifier_claude.py`, `domain/verification.py`, `prompts/verify_system.md` | modified | `ClaimKind.STATUS_UPDATE` with the claim of Data Models (change, quote, new date); `transcript_for` reuses the new `domain/excerpts.excerpt_window` (no adapter-to-adapter import) | add kind, branch in `claims`/`_claim_verification`/`with_verifications`, prompt axes, tests |
| `domain/excerpts.py` | new | pure transcript windowing shared by the verifier and `CurateMeetings` | — |
| `minutes_markdown.py`, `messages.Minutes` | modified | `🔄 Andamento informado` section | render + labels |
| `application/pipeline.py`, `container.py` | modified | `after_analysis` hook; `Container.pipeline(after_analysis=None)`; failures logged only | never writes `error.txt` for curation |
| `adapters/inbound/daemon.py` | modified | `CuratorWorker` thread owned by `Daemon`; `pending()` queued at start; daily purge scheduled through `_background` (the tick never runs it inline) | restart required (user approval) |
| `domain/status.py`, `application/ports.py` (`MeetingRepository`), `repository_fs.py` | modified | `CURATION_ERROR` file name; `mark_curation_failed` / `clear_curation_failed` / `curation_error` on the repository that owns the meeting folder | tests |
| `domain/activities.py`, `use_cases/activities.py`, `curator_claude.py`, `activities_fs.py`, `prompts/curate_system.md` | new | core of the feature | — |
| `cli.py` | modified | `activities` sub-app; `analyze` calls `CurateMeetings` after its loop; tag-based `stories`; `plan` removed; `agent install`/`restart`/`uninstall` remove the legacy planner job; doctor/status lines | — |
| `container.py`, `config.py`, `config.toml` | modified | `[activities]`, `[audio] retention_days`; `[planner]`, `[stories] enabled` removed | old keys tolerated |
| `stories_claude.py`, `prompts/stories_system.md` | modified | blocks mode; the writer sets kind, priority and due for a block story; plan-based drafting removed | — |
| `stories_markdown.py`, `ports.StoryRenderer`, `domain/models.py` (`UserStory`, `SkippedAction`) | modified | `render(drafts, existing, degraded)` with nothing transient; `UserStory.source_text` and `SkippedAction.source_line` persisted; `is_task_card` inlined on stored `kind` | UT for a block story merged into a planner-era drafts file, UT for a block-only publish with no plan |
| `application/use_cases/planning.py` | deleted | planner and plan-based story use cases removed. `PurgeOldAudio` moves to `use_cases/retention.py` with its default from `constants.Audio.RETENTION_DAYS` (moved from `constants.Planner`). `PublishUserStories`, `PublishReport`/`PublishedStory`/`PublishFailure`, `recent_stories`, `stories_waiting` (used by `Container` and `trec status`) and `untrusted_sources` move to the new `use_cases/stories.py` with `untrusted_sources(repo, meeting_ids)` (ids from the stories' `source_meetings`), no plan input and no `Err.PLAN_MISSING` | UT-121 |
| Planner (`planner_claude.py`, `prompts/plan_system.md`, `BuildDailyPlan`, `Planner` port, `DailyPlan`, `merge_open_actions`, `ActionStatus.OVERDUE`, `is_overdue_on`, `ActionRoute`/`route_of`/`task_card`, `save/load_plan`, `latest_plan_before`, `Err.PLAN_MISSING`, `load/save_open_actions`, `Files.PLAN_*`/`OPEN_ACTIONS`, `Llm.MAX_PREVIOUS_PLAN_CHARS`, `ScheduledTask.planner`, `LaunchAgent.planner`, `trec plan`, `_planner_agent`; `Launchd.PLANNER_*` and `Windows.TASK_PLANNER` become the `Legacy` constants below) | deprecated → **deleted** | internal code: hard cut in the same change, no shim, no fallback. Public surface `trec plan`: removed (single-user tool; user decision) | delete + tests |
| `ActionStatus` | modified | `OVERDUE` kept only for decoding old `analysis.json`/plans (read-only) | codec maps legacy value |
| `scripts/fidelity_eval.py`, `scripts/wiki_corpus.py` | modified | they read plans; switch to the document/pass log; add status-update and curator sequence evals | — |
| `docs/prd/pages/06-daily-plan.md`, `08-user-stories.md`, `03-analysis.md`, `docs/prd/README.md`, appendices, `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10, `README.md` | modified | describe the document; remove the plan | — |
| `AGENTS.md` | modified | ports table (add `ActivityCurator`, `ActivityStore`, the `MeetingRepository` additions; change `StoryWriter`/`StoryRenderer`; remove `Planner`); commands (`trec plan` out, `trec activities` in); the intro sentence about the daily plan; the English-only rule gains the Portuguese allowance for `messages.ActivityDoc`, the curator's one-line summaries echoed in notification bodies and CLI lines, and the focus lines `trec activities` prints; the `activities/` lock and file layout; the `CuratorWorker` and the daemon-scheduled purge under the restart rule | edit in the docs wave |
| User state `data/plans/*.md|.json`, `open_actions.json` | kept, unread | no migration (bootstrap rebuilds from analyses) | documented |
| LaunchAgent `local.teams-recorder.planner` / Windows task | deleted | until removed, the installed job runs `trec plan --purge` at 18:00 and exits 2 each weekday; `agent install`, `agent restart` (the usual step after a code change), `agent uninstall` and the installer/uninstall scripts remove it. Its identifiers survive only as `constants.Legacy.PLANNER_LABEL`, `Legacy.PLANNER_TASK` and the arguments needed to build a `LaunchAgent(label=…)` / `ScheduledTask(name=…)` whose only use is `uninstall()` | UT-091, UT-095 |
| `scripts/install.sh`, `scripts/install.ps1`, `scripts/uninstall.sh`, `scripts/uninstall.ps1` | modified | stop offering and announcing the 6 pm planner; remove the legacy job | dry-run test |

Compatibility regime: user state (old plans, open actions) stays on disk untouched; config keys `[planner] retention_days` read as fallback for one release (removal in the release after the planner removal ships), `[stories] enabled` ignored; internal code hard-cuts.

## Agent Manageability Plan

Operated by the daemon and by the operator through the CLI: `trec activities` (state), `trec activities curate` (rerun/bootstrap), `trec activities undo`, `trec doctor`, `trec status`; files `log/activities.jsonl`, `curation_error.txt`, `.curator/versions/`. No structured `--json` output in this delivery.

## Config Lifecycle

Added: `[activities] enabled=true, model, cli_model="opus", effort="medium", notify=true, keep_versions=50`; `[audio] retention_days=30` (falls back to `[planner] retention_days`). Removed: `[planner] hour`, `[stories] enabled` (ignored when present). `[activities] enabled = false` disables only the automatic triggers (the daemon's worker and the curation step of `trec analyze`); the explicit `trec activities …` commands and `trec stories` still run. Validation in `config.Settings` with tests in `tests/unit/test_config.py`; `scripts/config_tool.py` and the Windows installer learn the new section.

## Testing Approach

- Pure domain functions (`apply_ops`, checkbox rule, box, links, diff, tags, calendar) — table-driven unit tests, no fakes.
- Use cases on fakes: `FakeActivityCurator` (scripted outputs, records inputs), `InMemoryActivityStore`, existing repo/notifier/clock fakes.
- `FsActivityStore` on `tmp_path` (lock contention via a second process holding `flock`, atomic write, version rotation, archive truncation, commit rollback when the document replace raises, reconciliation of an interrupted commit rolled back or forward by the box stamp, undo through the same journal).
- `ClaudeCurator` with `fake_claude_cli.py` and the API fake transport (message order, schema mapping, repair call).
- CLI via Typer runner with the container's fakes; daemon `CuratorWorker` with `run_in_background` hooks.
- Quality evaluation (not unit tests): `scripts/fidelity_eval.py` planted status updates (precision/recall ≥ 90%) and a curator sequence run (~10 working days, ~25 synthetic meetings, simulated user edits between and during passes). Targets in `_tests.md`. Spends subscription: ask before running.
- `mypy` clean; `test_no_hardcoded_strings` green.

## Development Sequencing

### Build Order

1. Analyzer contract: `StatusUpdate`, `for_whom`, schema, prompt cues, codec, verifier kind, minutes section (gate: unit tests + fidelity eval on status updates).
2. Domain `activities.py` (gate: unit tables).
3. Ports + `FsActivityStore` + fakes (gate: store tests incl. lock).
4. `ClaudeCurator` + `prompts/curate_system.md` (gate: adapter tests; one sequence eval run).
5. `CurateMeetings` + `Pipeline.after_analysis` + `Container.pipeline(after_analysis)` + `CuratorWorker` (owned by `Daemon`, queue rebuilt at start) + curation step of `trec analyze` + `trec activities` / `curate` (gate: use-case + CLI tests) → **shadow rollout B** with the planner still on, after `trec agent restart` with the user's approval.
6. `UndoLastPass`, recovery rule, doctor/status (gate: tests).
7. Planner removal + migration + daily purge in daemon + config + `PublishUserStories`/`stories_waiting`/`recent_stories`/`untrusted_sources` moved to `use_cases/stories.py` without plan input, `StoryRenderer.render` without actions (gate: full suite, agent install/uninstall tests) — only after the user says go.
8. `DraftStoriesFromTags` + writer blocks mode + `trec stories` (gate: tests).
9. Docs (PRD, REQUIREMENTS §10, AGENTS.md, README).

### Technical Dependencies

- Logged-in Claude Code session for the daemon (already required).
- `trec agent restart` needs the user's approval (a recording may be running).

## Monitoring and Observability

- `log/activities.jsonl`: per pass `kind`, meetings, ops applied, retried and per-kind retries, unaccounted refs, ignored, user_removed, summary, doc size, error.
- `llm_usage.jsonl`: tag `curate:<first meeting id>` and `curate-repair:…`.
- Daemon log (`Log.*`): pass start/end, queue size, lock wait time, failures, batch isolation, commit reconciliation, purge scheduling and failure.
- Thresholds watched in the shadow week: retry rate < 10%, failure rate < 2%, doc ≤ ~8k tokens.

## Technical Considerations

### Key Decisions

- **Edits, not a rewrite; one invariant** — ADR-001.
- **Remove the planner, no scheduled pass, stories on demand** — ADR-002.
- **Lock held through the LLM call.** Passes are serialised without a redo loop; the user is never blocked (editing is outside the lock; `undo` is non-blocking; `stories` tries the lock once without waiting and defers the tag replacement to its next run when the curator holds the lock, since a pass can run for minutes; the drafts file is the memory, so a drafted line is never drafted again). Alternative (optimistic redo) rejected: discards whole calls and loops.
- **flock over a PID file.** Released by the OS on process death; no polling, no timeout. Windows: `msvcrt.locking` in a retry loop (untested on Windows, said so).
- **base.md = the document as the curator produced it, without code's rescue lines, plus `during_edits` in the pass record.** `base = render_links(render_box(W))` where W is the re-read document F' after the ops, so it never depends on whether an op also fits the snapshot F, and the box, focus and link block are in it. User edits are always the body only: `<user_edits>` = `during_edits + unified_diff(body(base), body(document))` and `during_edits = unified_diff(body(F), body(F'))`. A line the user types in the box is therefore never diffed: it reaches the model once through `<box_lines>`, and when code rescues it into `## Minhas ações` the next diff shows it once, as an added line (never twice). Lines rescued from the box are written to the document but not to the base.
- **Commit order is recoverable and the document says whether it was replaced** (ADR-003). `commit` first builds the archive entries and measures each archive file's size before and after the append, then writes, in this order: the version files (`_before`, `_after`, `_base`, `_prevbase` = `base.md` as it is, and `_pass.json` holding both sizes), the archive entries, the document (atomic replace; a pass writes its version as the stamp in the closing marker of its box), `base.md`, and last the pass-log line (the commit point). If a step raises inside the process, `commit` undoes what it did: before the document replace it truncates the archive files to their sizes before and deletes the pass's version files; after the replace it retries the remaining steps and, when the retries run out, raises `CommitIncomplete` (a `RepositoryError`): the pass happened, so `CurateMeetings` logs no `failed` record, writes no error file, sends no failure notification and does not re-run the batch meeting by meeting; the next `lock()` finishes it. A pass or undo never takes the name of a version set that has files (`ActivityStore.version_names()`). Every other file system failure leaves the store as a `RepositoryError` (never a raw `OSError`). After a hard stop, `lock()` reconciles on entry every version triple that has no pass-log line (`passes()` treats a torn last line as absent): the document was replaced iff `box_stamp(document)` is not None and equals `box_stamp(_after)` (for a pass, `_after` carries the pass's stamp; for an undo it is the restored text, whose stamp is an earlier pass's or, when the first pass is undone, the skeleton's fixed `skeleton_stamp`; a document with no stamp, because the user deleted or rewrote the marker, is never counted as replaced); replaced → roll forward (`base.md` from `_base`, deleted when the set has no `_base` file; pass-log line from `_pass.json`), otherwise roll back (archive truncated to its size before, files deleted). The stamp survives whatever the user edited afterwards, so all four cases (stop before or after the replace, document edited or not) are decided correctly; an editor overwrite that restored an old buffer carries an older stamp: a roll back for a pass, whose `_after` has a newer one, and a roll forward for an undo whose restored text carries that same older stamp, which matches the disk in both cases. A deleted or rewritten stamp always reads as "not replaced" and rolls back, even for an undo whose restore did reach the file: the consistent "undo did not happen" state, retried with `trec activities undo`, and the versions keep the text. Rejected: comparing the document with `_before` (a stop before the replace plus a user edit looks like a stop after it plus a user edit); a `_replaced` marker file (a stop between the replace and the marker, then a user edit, is still ambiguous); relaxing the all-or-nothing invariant.
- **Undo is a commit.** `UndoLastPass` goes through the same journal: `commit(current, before_N, [], prevbase_N, undo_record)` restores the document, then `base.md` to the base pass N started from (`_prevbase`; when N was the first pass there was none: `base=None`, `base.md` is deleted and the next pass sees `user_edits` "" as on a first pass), then the pass-log line; the undo record's `during_edits` is N's `carried_edits` and its own `carried_edits` is "". The next pass's `<user_edits>` therefore again shows every edit the user made before and during N, N having been undone: a deletion N archived is seen as the user's deletion again, not lost. The archive is truncated last (`truncate_archive`, only while its size is still `archive_bytes_after`); a stop in between leaves surplus entries, never missing ones, and a stop inside the commit is reconciled like a pass's (the restored text's stamp decides).
- **`move` instead of a spanning `replace`.** A reorder (a ticked item to the bottom, a 💤 item sunk) is a `move`: target = the whole item, anchor = one line, and code pastes the lines byte for byte. Checkbox state, count and every passed line are untouched by construction. The per-op rule for `replace` guards state and count only; keeping a replaced line's identity is a prompt rule measured by Q-002.
- **CuratorWorker stops without waiting.** It is a daemon thread; `request_stop()` sets a flag and enqueues a sentinel, so an idle worker returns and no new pass starts, and `Daemon.shutdown` never joins an in-flight LLM call (up to 900 s). The abandoned pass is rebuilt by `pending()` at the next start; a kill inside a commit's few milliseconds is the reconcile case above.
- **Tag drafting is idempotent through the drafts file.** There is no pending-replacement file: a tagged line whose first line is a stored story's `source_text` or a stored skip's `source_line` is already handled, never sent to the writer again, and only its tag replacement is retried (document and base). Drafted lines are therefore never re-drafted, whether the earlier run was interrupted, deferred by a busy lock or still waiting.
- **A failed batch is isolated before it is counted.** `CurateMeetings` re-runs the meetings of a failed multi-meeting pass one at a time; only a failed single-meeting pass is a failure of that meeting (error file, attempt, notification). Cost: up to N extra calls on a failed batch; benefit: a meeting that always fails never exhausts its batch-mates' attempts. When a single-meeting re-run is left unfinished (its commit replaced the document but could not write `base.md` or its log line), the rest of the round waits for the next lock: the meetings not yet re-run are in `PassResult.deferred`, get no error file and no attempt and stay in `pending()`; the CLI prints one `Deferred …` line for each (exit code unchanged) and the daemon's pass-end log line counts them.
- **Recovery by window, not by event.** `pending()` looks at the last 2 working days and is queued at daemon start; `not_curated()` looks at 10 working days and drives the listing in `trec activities`/`trec doctor` whether or not an attempt happened (the queue is in memory and a restart can lose it). Both count today as day 0: the window starts at 00:00 of `working_days_ago(today, n)`, so on a Monday `pending()` reaches back to Thursday.
- **Meeting id as link label.** No alias table; definitions regenerated by code from labels in use.
- **Analyzer is document-unaware.** Keeps `analysis.json` a function of the transcript; the curator does all matching, with excerpts for context.
- **Atomic write helper.** `repository_fs._write_atomic` is moved to `fs_retry.atomic_write` and used by both repositories (internal hard cut).
- **Story writer contract changes** (`draft` → `draft_from_blocks`, `StoryRenderer.render` drops the actions and takes no per-call input; `PublishUserStories` and the story helpers move to `use_cases/stories.py`); plan-based drafting is deleted, not kept as a second mode. Stored `kind` keeps `is_task_card` working for old drafts.
- **Transcript excerpts are plain domain code.** `domain/excerpts.excerpt_window` is shared by the verifier adapter and `CurateMeetings` (which loads transcripts through the repository), so the curator adapter imports no other adapter.

### Known Risks

- Curator matching quality (duplicates, 💬 on the wrong item): medium; measured by the sequence eval and the shadow week; the user's go/no-go.
- Target-match retries (copy errors on long lines with emoji/quotes): medium; anchoring guidance in the prompt; retry rate logged. A reorder is a `move`, so no `replace` target grows beyond the item it changes.
- A `replace` that keeps checkbox counts but rewrites another line's identity is accepted by code: low-medium; a prompt rule measured by Q-002 (user lines preserved 100%).
- False progress from the analyzer: medium; verifier + 💬-only + eval.
- Lock contention when many meetings end together: low; batching of 4. A failed batch costs extra calls (one per meeting) before attempts are counted.
- A hard stop inside the few-millisecond commit window, or a daemon exit that abandons a pass: low; reconciled at the next lock (the box stamp decides roll back or forward), covered by store tests; an abandoned pass is rebuilt by `pending()`.
- Prompt drift as the document grows: low-medium; retention rules, ≤2 sub-lines, Contexto cap.
- Windows untested.

## Safety Invariants

1. Only the user changes a checkbox state, and only `archive` removes a checkbox line: each `replace` keeps at least its target's open lines and exactly its ticked lines, each `insert_after` text holds no ticked line, a `move` changes no count (an edit that breaks the rule is an `OpFailure` and goes to the one repair round). Lines no edit targets are preserved byte for byte by Safety Invariant 4; there is no whole-document backstop (removed in review round 3, ADR-001).
2. At most one pass writes the document at a time (`ActivityStore.lock`, OS-released).
3. A pass writes everything or nothing: when `commit` raises, `atividades.md`, `base.md`, the archive and the versions are as they were; after a hard stop, the next `lock()` rolls the interrupted commit forward when `box_stamp(document)` is not None and equals `box_stamp(_after)` (an undo's `_after` is the restored text, whose stamp is an earlier pass's or the skeleton's fixed `skeleton_stamp`, or is absent when the user had removed the marker before the undone pass), and back otherwise, a missing stamp included, whatever the user edited meanwhile.
4. Ops apply to the document as re-read under the lock immediately before applying; text no op targets is preserved byte for byte.
5. Op targets are matched only inside the body; the box and the link block are written only by code.
6. Every archived text is appended to the archive after its file's size is recorded and before the document is replaced; the pass-log line is written last.
7. `undo` never waits on the lock, is a commit through the same journal (document, then base to the base the undone pass read, then the pass-log line), truncates the archive last and only while its size is still `archive_bytes_after` (a stop in between leaves surplus archive entries, never missing ones), carries the undone pass's `carried_edits` so the next pass sees the user's edits again, and refuses when the last pass is not the one previewed (`UndoStale`).
8. A curation failure never writes `error.txt` and never changes `derive_status`.
9. A meeting is retried automatically at most twice, counting only failed passes in which it was curated alone.
10. `trec stories` replaces a tag only when the tagged line is found exactly once in a fresh read, applies the same replacement to `base.md`, never waits for the curator lock, and never sends a line already in the recent drafts (as a story or a skip) to the writer again; a replacement it could not apply is retried by the next run from the drafts file.
11. A line typed in the box is never discarded: a line the pass did not move is put back at the top of `## Minhas ações` by code.
12. The next pass sees every user edit once: edits made to the body before the pass as `diff(body(base), body(document))`, edits made to the body during the call as `during_edits`, a line typed in the box through `<box_lines>` and then as the rescued line, and nothing the curator or code wrote.
13. The daemon never waits on a curator LLM call to shut down; the abandoned pass is rebuilt by `pending()` at the next start.

## File References

### Repo Files

- `src/teams_recorder/application/pipeline.py:46-86` — `process`/`resume_pending`; where `after_analysis` hooks in.
- `src/teams_recorder/application/use_cases/processing.py:164-185` — `AnalyzeMeeting` holds the meeting lock, saves analysis and minutes.
- `src/teams_recorder/adapters/outbound/llm_schema.py:37-114` — `ActionOut`/`AnalysisOut`/`to_domain`; new fields go here.
- `prompts/analyze_system.md` — cues section where the progress cues are added.
- `src/teams_recorder/adapters/outbound/verifier_claude.py:77-104` — `transcript_for` windowing; its windowing moves to `domain/excerpts.excerpt_window` (the head-of-transcript part stays a parameter).
- `src/teams_recorder/domain/models.py:176-300,440-470` — `ActionStatus`, `ClaimKind`, `Action`, `merge_open_actions` (deleted).
- `src/teams_recorder/adapters/outbound/llm_transport.py` — `StructuredTransport`, timeouts, usage log.
- `src/teams_recorder/adapters/outbound/repository_fs.py:43-47,150-159,318-330` — atomic write, meeting lock pattern, story drafts persistence.
- `src/teams_recorder/adapters/inbound/daemon.py:218-313` — job threads, `_resume_pending`, `_background`.
- `src/teams_recorder/adapters/inbound/cli.py:553-700` — agent install/planner, `plan`, `stories`, `publish`.
- `src/teams_recorder/application/use_cases/planning.py:45-302` — planner and story use cases being deleted; `PurgeOldAudio` moves to `use_cases/retention.py`; `PublishUserStories`, `stories_waiting`, `recent_stories`, `untrusted_sources` (lines 164-300) move to `use_cases/stories.py` without the `load_plan` call.
- `src/teams_recorder/domain/status.py:11-23` — meeting file names (`CURATION_ERROR` goes here).
- `src/teams_recorder/adapters/inbound/cli.py:453-493` — `analyze` loop (does not use `Pipeline`); curation is called after it.
- `src/teams_recorder/container.py:137-138` — `Container.pipeline()` returns a fresh `Pipeline` on every call.
- `src/teams_recorder/adapters/outbound/stories_markdown.py`, `stories_claude.py:116-128`, `domain/models.py:396-398` — renderer, derived priority/due/kind, `is_task_card`.
- `src/teams_recorder/adapters/outbound/stories_claude.py:99-166` — writer call and message builder to change.
- `src/teams_recorder/constants.py:80-170` — `Files`, `Launchd`, `Llm` entries to add/remove.
- `src/teams_recorder/messages.py` — `Cli`, `Notify`, `Log`, `Err`, `Minutes`, `StoryDoc`; add `ActivityDoc`.
- `config.toml` — `[planner]`, `[stories]` sections to change.
- `tests/fakes/__init__.py` — fakes to add (`FakeActivityCurator`, `InMemoryActivityStore`).
- `tests/unit/test_no_hardcoded_strings.py` — string discipline gate.
- `scripts/fidelity_eval.py`, `scripts/wiki_corpus.py` — evaluation harnesses to extend.

### Design and Analysis Sources

- Design rounds (session scratchpad, not in the repo): `design-v2.md`, `design-final.md`, `critique-v1.md` — rationale; this spec supersedes them.
- Flowchart artifact: https://claude.ai/artifact/V6xTTuxTuGvW7wJS3MLW5m.

## Assumptions and Defaults

- User decisions (2026-10-19): one living document kept by an LLM curator; everything enters; completion is the user's; never delete; stories only via `#história` + `trec stories`; 18:00 planner removed with no scheduled replacement; deterministic task store rejected; VS Code first; bootstrap from the last 10 working days with confirmation.
- Batch size 4; automatic retry window 2 working days (today is day 0; Monday to Friday, holidays ignored), 2 attempts counted on single-meeting passes; listing window of not-curated meetings 10 working days; versions 50; Contexto 7 days and ≈10 lines; 💤 ≈3 weeks; focus 3–5 lines; recent archive sent: 60 entries; bootstrap time estimate 160 s per pass (`Activities.EST_SECONDS_PER_PASS`); excerpts ±60 s merged; effort `medium`; model = the analyzer's.
- Document path `data/activities/atividades.md` relative to `paths.data_dir`.
- Rollout B (shadow) lasts until the user says go.

## Architecture Decision Records

- [ADR-001: The curator edits the document; code applies the edits and enforces one rule](adrs/adr-001.md) — edit operations (`replace`, `insert_after`, `move`, `archive`) over whole-document rewrite and over a deterministic task store.
- [ADR-002: Remove the daily planner; no scheduled pass; stories on demand](adrs/adr-002.md) — the document replaces the plan, absolute dates replace a morning pass.
- [ADR-003: A pass commits in a recoverable order; the pass-log line is the commit point](adrs/adr-003.md) — version files as journal, the stamp in the document's box decides roll back or forward at the next lock; undo uses the same journal.

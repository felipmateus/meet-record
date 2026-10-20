# Test Specification: Activities curator

Canonical test contract for the activities curator. Companion to `_spec.md`.
Derived from `_user_stories.md` (behavior), `_spec.md` Part II (components) and `_dx.md` (CLI journeys).

## Strategy

- Frameworks and harnesses: pytest; pure domain functions tested table-driven without fakes; use cases on fakes from `tests/fakes/__init__.py` (new `FakeActivityCurator` with scripted `CuratorOutput`s that records its inputs, new `InMemoryActivityStore`, existing repository/notifier/clock fakes); `FsActivityStore` on `tmp_path`; `ClaudeCurator` through the existing fake transports and `tests/fixtures/fake_claude_cli.py`; CLI through Typer's `CliRunner` with the container's fakes; daemon via `run_in_background` hooks.
- Execution: `pytest` (fast suite); `mypy`; `tests/unit/test_no_hardcoded_strings.py` stays green. Quality evaluations (Q-*) run through `scripts/fidelity_eval.py` / `scripts/wiki_corpus.py`, spend the Claude subscription, and need the user's go-ahead; they are not part of `pytest`.
- Conventions: one observable behavior per case; Portuguese document fixtures in `tests/fixtures/activities/`; follow existing naming (`test_<unit>_<behavior>`).

## Coverage Matrix

| Source | Behavior | Unit | Integration | E2E / Quality |
| ------ | -------- | ---- | ----------- | ------------- |
| US-001 | one current document after each analysis | UT-030, UT-031 | IT-001, IT-002 | E2E-001, Q-002 |
| US-001.EC-1 | empty analysis → no call | UT-032 | — | — |
| US-001.EC-2/3/4 | same work one item; archived comes back; rerun | — (prompt behavior) | IT-003 | Q-002 |
| US-001.EC-5 | no cap at 150 items | UT-008 | — | — |
| US-002 | provenance links, definitions regenerated | UT-012, UT-013 | — | Q-002 |
| US-002.EC-1 | definition dropped for deleted meeting | UT-014 | — | — |
| US-003 | box written from focus with update time | UT-010 | IT-001 | Q-002 |
| US-003.EC-1 | lines typed in the box are surfaced and never lost | UT-011, UT-027, UT-033, UT-047, UT-048 | IT-016 | — |
| US-004 | context section routing/retention | — (prompt) | — | Q-002 |
| US-005 | progress shows on the item; scope rules | UT-050–UT-053 | — | Q-001, Q-002 |
| US-006 | only the user changes checkbox state | UT-004, UT-005, UT-019–UT-024 | IT-004 | Q-002 |
| US-006.EC-1 | rule rejects silent removal, ticking, drop-and-add; moves are byte-exact; replace identity is a prompt rule | UT-005, UT-020–UT-024, UT-029, UT-034, UT-104, UT-112–UT-115 | — | Q-002 |
| US-007 | user edits stand; diff of the bodies sent; user lines exempt from 💤/links/moves | UT-015, UT-035, UT-049, UT-100, UT-123 | IT-005 | Q-002 |
| US-007.EC-1 | editor overwrite → re-added | — (prompt) | — | Q-002 |
| US-008 | archive entries with reason and relative links | UT-040, UT-041 | — | — |
| US-009 | ≤ 2 sub-lines, size bounded | — (prompt) | — | Q-002 |
| US-010 | undo with diff, confirmation, archive truncation; the next pass sees the user's edits again | UT-060–UT-063, UT-066, UT-118, UT-119, UT-126 | IT-006, IT-015, IT-020, IT-021 | E2E-003 |
| US-010.AC-5/EC-4 | undo refuses when a new pass ran after the preview | UT-065 | — | — |
| US-010.EC-1 | undo non-blocking when busy | UT-064 | IT-007 | — |
| US-011 | failures atomic; one repair; auto retry ≤ 2; a hard stop reconciled by the box stamp | UT-001–UT-003, UT-036–UT-039, UT-104, UT-117, UT-125 | IT-008, IT-012–IT-014, IT-019 | — |
| US-011.AC-3/5/6 | recovery by working-day window, queue rebuilt at start, not-curated listing | UT-101, UT-106, UT-107, UT-087 | — | E2E-005 |
| US-011.AC-7 / US-015.EC-2 | failed batch isolated before counting | UT-102 | — | — |
| US-012 | edits during a pass kept; next pass sees them once (box lines included) | UT-006, UT-046, UT-047, UT-049, UT-100, UT-123 | IT-005, IT-016 | Q-002 |
| US-013 | minutes section | UT-054 | — | — |
| US-013.EC-2 | old analysis without fields | UT-055 | — | — |
| US-014 | tag-based stories; publish needs no plan file | UT-016, UT-017, UT-070–UT-073, UT-121 | IT-009 | E2E-004 |
| US-014.AC-3 | writer skips a block → tag stays, reason printed | UT-075 | — | — |
| US-014.EC-4 | busy curator lock → drafts saved, tag replacement deferred; a drafted line is never re-drafted, however many runs | UT-076, UT-077, UT-122 | IT-017 | — |
| US-014.EC-5 / blocks mode | publish flag; block story merged into planner-era drafts; task-card kind; skipped block rendered from persisted `source_line` | UT-078, UT-079, UT-111, UT-124 | — | — |
| US-015 | batching ≤ 4, one pass at a time | UT-042 | IT-010 | — |
| US-016 | curate id / --since | UT-080, UT-081, UT-088 | — | E2E-002 |
| US-016.EC-2 | `waiting for the curator…` while a pass runs | UT-089, UT-105 | IT-007 | — |
| US-016.AC-4 | `trec analyze` curates after analysis | UT-084–UT-086 | — | E2E-001 |
| US-017 | trec activities output | UT-082, UT-083, UT-087, UT-110 | — | E2E-001 |
| US-018 | planner removed, purge in daemon, config fallback, worker stop contract | UT-090–UT-098, UT-120 | IT-011, IT-018 | — |
| US-019 | notify only what concerns the user | UT-043, UT-044 | — | Q-002 (notification precision) |
| Architecture (domain imports no `messages`/`constants`; `DocFormat`) | pure domain functions get their text from `DocFormat` | UT-116 | — | — |
| Supporting units | trailing-whitespace matching, calendar strip, `excerpt_window`, worker ordering, codec legacy values, verifier claim details, no-tag stories, container/daemon wiring, repository error file | UT-009, UT-018, UT-026, UT-028, UT-045, UT-056–UT-059, UT-074, UT-108, UT-109 | — | Q-003 (shadow week) |
| Safety Invariants 1–13 | see cases | UT-001–UT-008, UT-019–UT-024, UT-034, UT-049, UT-064, UT-065, UT-073, UT-076, UT-102, UT-112–UT-115, UT-118–UT-120, UT-122, UT-126 | IT-007, IT-010, IT-012–IT-017, IT-019–IT-021 | — |

## Unit Tests

### Domain `apply_ops` and the checkbox rule (Spec: Core Interfaces, Safety Invariants)

- **UT-001** (happy): `apply_ops` — `replace` whose target is one whole body line found once → line replaced; text elsewhere byte-identical.
- **UT-002** (error): `apply_ops` — target found 0 times → `OpFailure(error="not found")`, document unchanged by that op, later ops still applied.
- **UT-003** (error): `apply_ops` — target found twice in the body → `OpFailure(error="found 2 times")`.
- **UT-004** (error): `apply_ops` — a `replace` turning `- [ ] X` into `- [x] X` → `OpFailure(error="breaks the checkbox rule")` with the counts in `detail`; document unchanged by that op (the curator may not tick).
- **UT-005** (state): `apply_ops` — an open line removed by `replace` with `""` → rule failure; the same line "moved" as `replace ""` + `insert_after` → the `replace` fails (a move is a `move` op, UT-023); removed via `archive` → applied and listed in `Applied.archived`.
- **UT-006** (concurrency): `apply_ops` on a re-read document where the user added lines elsewhere after the snapshot → user lines preserved, op applied.
- **UT-007** (boundary): `apply_ops` — target matches text inside the box or link block only → `OpFailure(error="targets the box or link block")`; same text also in body once → body line changed, box untouched.
- **UT-008** (boundary): `apply_ops` and `open_count` on a 150-item document → no error, counts exact.
- **UT-009** (happy): trailing whitespace on the target or the document line is ignored when matching; any other difference (curly quote vs straight) is a mismatch.
- **UT-019** (happy): `apply_ops` — `replace` keeping the number of open lines and changing the text after the checkbox (date change, ` · 💤 …` appended, a mention link added) → applied; `ticked` lines gaining a ` ✔ seg 19/10` suffix → applied.
- **UT-020** (error): `apply_ops` — `replace` of two open lines with one (merge) or with `""` → `OpFailure("breaks the checkbox rule")`, `detail` names target and text counts.
- **UT-021** (error): `apply_ops` — one `replace` that ticks A and adds a new open line C in the same text (open count unchanged, ticked count +1) → rule failure; also an untick (`- [x] A` → `- [ ] A`) → rule failure.
- **UT-022** (error): `apply_ops` — `insert_after` whose text contains `- [x] …` → rule failure; `archive` of open A followed by `insert_after` of `- [x] A` → the archive applies, the insert fails.
- **UT-023** (happy): `apply_ops` — a `move` of a ticked item (main line + sub-lines) with the anchor on the last line of its section, and a `move` of an open 💤 item likewise → applied; the moved lines are byte-identical, every line they pass is untouched, open and ticked counts unchanged; the same move attempted as `replace ""` + `insert_after` → the `replace` fails.
- **UT-024** (error): `apply_ops` — ops `replace ""` on open B and `insert_after` adding open C in the same pass (drop B, add C) → B's op fails, C's insert still applies; the count form of the old rule would have passed this pass.
- **UT-025** (withdrawn): was the `check_open_invariant` backstop table. The backstop was removed in review round 3 (user decision, ADR-001 Alternative 5); the ID stays unused and nothing owns it. Untouched lines are proven preserved by UT-001, UT-006, UT-023 and UT-113 (byte-identical outside the edit) and the per-op rule by UT-004, UT-005, UT-019–UT-024.
- **UT-026** (happy): `working_days_ago` — today is day 0 and is not counted: `(date(2026,10,19), 2)` (Monday) → `date(2026,10,15)` (Thursday); `(date(2026,10,21), 2)` (Wednesday) → `date(2026,10,19)` (Monday); `(date(2026,10,24), 2)` (Saturday: Friday is 1, Thursday is 2) → `date(2026,10,22)`; `(date(2026,10,25), 2)` (Sunday) → `date(2026,10,22)`; `(date(2026,10,24), 0)` → `date(2026,10,24)`; a weekend day never counts as Friday.
- **UT-027** (happy): `rescue_box_lines` — lines not in the body → inserted unchanged at the top of `## Minhas ações`, in order, no sub-line; a line already in the body → not duplicated; heading missing → created right after the box.
- **UT-028** (happy): `excerpt_window` — two times 30 s apart → one merged excerpt ±60 s with speaker labels and `gap` between separated windows; `head_chars` keeps the transcript start; no times and no head → empty.
- **UT-029** (state): the per-op rule is evaluated on the text current at that op: an op that targets text an earlier op wrote (an `insert_after` line, a `replace` result) applies, and its counts are taken from that text, not from the original document.
- **UT-112** (boundary): `apply_ops` — a `replace` whose target is `- [ ] A` + `- [ ] B` and whose text is `- [ ] A` + `- [ ] C` (counts equal) → applied. This is the documented limit: code guards checkbox state and count, line identity is a prompt rule measured by Q-002 (a `replace` that drops or rewords a passed line is not detected by code; moves are `move`s so no replace has to pass lines it does not change).
- **UT-113** (happy): `apply_ops` — a `move` whose anchor is a section heading puts the item first in that section; a `move` followed by an `insert_after` on the moved item (targeting the line at its new position) applies in order; an `insert_after` applied first and then a `move` whose target is the item as the insert left it applies; the document outside the moved item is byte-identical.
- **UT-114** (error): `apply_ops` — `move` with an anchor found 0 times → `OpFailure("anchor not found")`; found twice → `"anchor found 2 times"`; anchor inside the target → `"anchor inside the target"`; anchor in the box or link block → `"targets the box or link block"`; target not found → `"not found"`; none of them changes the document, later ops still apply, and all reach `repair` with the reason.
- **UT-115** (state): `apply_ops` — a pass of one `replace` (✔ appended to a ticked item) and one `move` (to the bottom of its section) on the same item commits with the item byte-for-byte as the replace wrote it, and every line the move passes is byte-identical.
- **UT-116** (state): `domain/activities.py` (checked by AST) imports neither `teams_recorder.messages` nor `teams_recorder.constants`; its functions take a `DocFormat`; `doc_format()` builds it from `messages.ActivityDoc`, `constants.Parse`, `constants.Activities.SKELETON_STAMP`, `constants.Files.RECORDINGS_DIR` and `domain.status.MINUTES` so every marker, heading, weekday name, `(hoje)`, header label, link target and checkbox regex round-trips (`render_box` output, with and without a stamp, is recognised by `body_span` and `box_stamp` through `box_end_prefix`/`box_end_suffix`; `open_count` uses `open_re`; `render_links` writes each definition from `link_target`); the AST check also finds no string literal in the module that contains the recordings folder name, so changing `Files.RECORDINGS_DIR` changes every link with no edit to the domain; `test_no_hardcoded_strings` passes with no allowance for the module.

### Domain rendering (Spec: Core Interfaces)

- **UT-010** (happy): `render_box` — focus 3 lines, meetings ["Daily"], now seg 19/10 10:12, stamp `20261019-101200` → box exactly as `_dx.md` (header + numbered focus) between the markers, the closing marker carrying the stamp.
- **UT-011** (state): `render_box` — old box contains a user line `- [ ] Ligar X` → returned in `box_lines`, new box has no such line; a numbered line the user typed (`> 2. Ligar…`) is returned too when `base` is given (only the focus lines of `base` are generated, each matching once), while without `base` every numbered line is generated.
- **UT-117** (state): `box_stamp` — returns the stamp of a document written by `render_box`; the skeleton's box carries `skeleton_stamp` (`00000000-000000`), which no pass version equals; None only for a closing marker the user deleted or rewrote; the stamp is unchanged by lines the user adds or deletes anywhere outside the closing marker, and `body_span`/focus reading accept the marker with and without a stamp.
- **UT-012** (happy): `render_links` — labels used `[…][2026-10-16_09-30-11]` twice and one other → link block lists the two ids sorted, each definition built from `fmt.link_target` (`../recordings/<id>/minutes.md` with the real constants); a `DocFormat` with another `link_target` changes every definition.
- **UT-013** (state): `render_links` — a label no longer used → its definition removed.
- **UT-014** (state): `render_links` with `meeting_exists=False` for one id → that definition omitted.
- **UT-015** (happy): `unified_diff` — base vs current with a reworded line → diff shows `-`/`+` lines; identical → "".
- **UT-016** (happy): `tagged_blocks` — line with `#história` plus two deeper-indented sub-lines followed by a sibling → block has 3 lines.
- **UT-017** (state): `replace_tag` — line found once → tag replaced; line edited (not found) → None.
- **UT-018** (happy): `calendar_strip(date(2026,10,19))` → starts `seg 19/10 (hoje)`, weekend days bracketed, 14 entries.

### `CurateMeetings` (Spec: Use cases)

- **UT-030** (happy): one analyzed meeting, fake curator returns 2 inserts → store `commit` called once with the after text, `base = render_links(render_box(W))` (box, focus and links included, rescue lines excluded), `PassRecord(kind=meeting, ops_applied=2)`.
- **UT-031** (happy): no document → skeleton created from `messages.ActivityDoc` before the curator call, its closing marker carrying `skeleton_stamp` (`box_stamp(skeleton) == skeleton_stamp`); curator receives it.
- **UT-032** (boundary): analysis with no actions, updates, deadlines, decisions, questions, risks, next meetings → curator not called; `PassRecord(kind=skipped_empty)`; document unchanged.
- **UT-033** (state): user typed a line in the box → `CuratorInput.box_lines` contains it.
- **UT-034** (error): curator output breaks the checkbox rule (an op ticks an item), repair returns ops that still break it → nothing committed, `PassRecord(kind=failed)`, `curation_error.txt` written through `repo.mark_curation_failed`, failure notification.
- **UT-035** (happy): `CuratorInput.user_edits` equals the last meeting/undo record's `during_edits` followed by the diff of the bodies from `read_base()` to the current document (`unified_diff(body(base), body(document))`); `""` on the first pass.
- **UT-036** (error): two ops fail to match → `repair` called once with the in-memory text and exactly those two failures; repaired ops apply → committed with `retried=True`.
- **UT-046** (concurrency): between the snapshot and the re-read the user deleted the line an op targets → that op fails with `not found`, `repair` receives it, and after the repair the user's deletion stands (the op is dropped, not re-created); user lines elsewhere preserved (US-012 AC-2).
- **UT-047** (concurrency): a line typed in the box after the snapshot (so absent from `CuratorInput.box_lines`) → still in the committed document, at the top of `## Minhas ações`, `PassRecord.box_rescued == 1`; not in the committed base.
- **UT-048** (state): the curator moves one box line into a section with `insert_after` (verbatim) and leaves another in the box → the first is not duplicated, the second is rescued; next pass `user_edits` shows the rescued line as added.
- **UT-049** (state): the user edits a body line between snapshot and re-read → `PassRecord.during_edits` equals `unified_diff(body(F), body(F'))`, the committed base contains that edit (built from F') and neither the box header nor the link block can appear in any `user_edits` (both diffs are over bodies); the next pass's `user_edits` is `during_edits` then the diff, so the edit is seen exactly once.
- **UT-123** (state): the user types `- [ ] Ligar para o João` inside the box after the snapshot → it is not in `during_edits` (box excluded), code rescues it to the top of `## Minhas ações` (UT-047), and the next pass's `user_edits` contains the line exactly once, as an added body line; the same line typed before the pass reaches the model once through `box_lines` and not at all in `user_edits`.
- **UT-037** (error): transport raises `AnalysisError` → no repair call, nothing committed, error file + notification.
- **UT-038** (state): `pending()` — meetings analyzed in the last 2 working days without a successful pass record (kind `meeting` or `skipped_empty`) → returned oldest first; one with 2 failed single-meeting records → excluded; one older than the window → excluded; a failed record listing several meetings does not count as an attempt for any of them.
- **UT-039** (state): successful pass including a meeting with `curation_error.txt` → cleared through `repo.clear_curation_failed`.
- **UT-100** (state): a repair op that matches only the in-memory text (not the snapshot F) → committed; the next pass's `user_edits` does not show the curator's new line as a user edit (base is derived from the written text, not from replaying ops on F).
- **UT-101** (state): `pending()` on Monday 2026-10-19 (today is day 0, window starts Thursday 15/10 00:00) returns Friday's and Thursday's analyzed meetings with no pass record, and excludes one analyzed Wednesday 14/10; a never-attempted meeting is included; ordering oldest first. `not_curated()` uses the same convention over 10 working days.
- **UT-102** (state): batch of poison P (fails alone) + healthy M1: the batch pass fails, then M1 alone succeeds and P alone fails → M1 committed, no `curation_error.txt` and no failed attempt for M1, P has exactly one counted failure; the failure notification names P only.
- **UT-103** (withdrawn): was the backstop-failure case (internal-check message, no repair). Removed with the backstop in review round 3; the ID stays unused and nothing owns it.
- **UT-104** (error): a checkbox-rule failure is sent to `repair` as an `OpFailure(error="breaks the checkbox rule", detail=…)` for exactly that op; repaired ops (an `archive` instead of a `replace ""`) apply and commit with `retried=True`.
- **UT-105** (concurrency): `execute(ids, wait=True, on_wait=cb)` with the lock busy → `cb` called once, then the pass runs after release; with the lock free → `cb` never called.
- **UT-106** (state): `not_curated()` → a failed meeting (reason = its error text) and a never-attempted one (reason None) within 10 working days, a curated one excluded, one older than 10 working days excluded.
- **UT-040** (happy): archive op with reason `data passou (qui 15/10)` → store receives (text, reason); archive entry rendering `### 16/10/2026 — data passou (qui 15/10)` + text + definitions with `../../recordings/`.
- **UT-041** (state): `user_removed` items → archived with reason `removido por você`.
- **UT-042** (boundary): six ids passed → `execute` handles four, oldest first; caller requeues the rest (worker test UT-045).
- **UT-043** (happy): curator `notify=True` and `[activities] notify=true` → one `Activities updated` notification with the summary.
- **UT-044** (state): curator `notify=False` → no notification; `[activities] notify=false` → none even when the curator says true; failures always notify.
- **UT-045** (ordering): `CuratorWorker` — three enqueued while a pass runs → next pass receives all three in one call plus pending ids; an id enqueued twice is curated once; an id still queued after an earlier round's `pending()` already curated it is dropped when its round starts (`CurateMeetings.uncurated`): six ids enqueued at start reach `execute` exactly once across rounds.
- **UT-107** (state): `Daemon` start with an analyzed meeting that has no pass record (queue lost to a restart) → after `_resume_pending` the worker receives it via `pending()`; with `[activities] enabled = false` no worker is built and nothing is enqueued.
- **UT-120** (concurrency): `CuratorWorker` — `request_stop()` with the worker idle → the thread's `run()` returns within 1 s (the thread is a daemon thread); an id enqueued after the stop is not started; with a pass in flight (fake curator blocked) `Daemon.shutdown` returns without waiting for it and the abandoned meeting is returned by `pending()` after the next start.
- **UT-108** (state): `Container.pipeline(after_analysis=f)` returns a `Pipeline` whose hook is `f`; the daemon's `_finish_call` and `_resume_pending` pass `worker.enqueue`; importing `teams_recorder.container` does not import `adapters.inbound.daemon`.
- **UT-109** (state): `FsMeetingRepository.mark_curation_failed` / `clear_curation_failed` / `curation_error` round-trip `recordings/<id>/curation_error.txt` (name from `domain.status.CURATION_ERROR`) atomically without taking the meeting `.lock`; `derive_status` is unchanged by the file.
- **UT-110** (happy): `ActivitiesSummary` — counts open checkboxes under each `messages.ActivityDoc` heading and lines for agenda/context, reads the focus between the box markers, omits a renamed heading, and takes `updated`/titles from the last pass record.

### Analyzer, verifier, minutes (Spec: Data Models)

- **UT-050** (happy): `to_domain` maps `StatusUpdateOut(change=due_changed, new_due="2026-10-16")` → `StatusUpdate` with `date(2026,10,16)`.
- **UT-051** (happy): `ActionOut.for_whom="Carla"` → `Action.for_whom == "Carla"`.
- **UT-052** (happy): verifier claims include one `ClaimKind.STATUS_UPDATE` per status update with `text = "<change>: <about> — \"<evidence>\""`, `owner = who`, `due = new_due`, `at = at`; the verdict maps back by position to `StatusUpdate.verification`.
- **UT-053** (happy): `verifier_claude.transcript_for` after reusing `domain.excerpts.excerpt_window` → same output as before the move for a long transcript (start plus ±60 s windows, gap markers); `CurateMeetings` builds `MeetingContext.excerpts` from the same function (UT-028).
- **UT-057** (happy): a `reassigned` update → claim text names the new owner (`reassigned to Ana: …`); a `due_changed` update with `new_due` → `Claim.due` set so the `date_said` axis applies; `who = indefinido` → no owner.
- **UT-058** (happy): the verifier user message for a status update contains the change, the quote and the new date (`describe(claim)`), and `prompts/verify_system.md` names the change-support and new-value axes.
- **UT-059** (error): a `done` update whose quote is an intention ("vou subir o timesheet") and a verdict `support != supported` → `StatusUpdate.verification` is unconfirmed with the reason; the minutes line carries ⚠️.
- **UT-054** (happy): minutes render `### 🔄 Andamento informado` with the four lines of `_dx.md`; unconfirmed line ends with ⚠️ and reason.
- **UT-055** (state): codec loads an `analysis.json` without `status_updates`/`for_whom` → empty list / None; saving it writes no new keys.
- **UT-056** (state): codec loads a legacy action with `"status": "overdue"` → loads (read-only legacy value) without error.

### `UndoLastPass` (Spec: Use cases)

- **UT-060** (happy): `preview` → diff now → before of the last pass, count of lines edited after it (current ≠ after), and the `version` of that pass.
- **UT-061** (happy): `execute(preview.version)` → committed through `store.commit(current, N.before, [], N.prevbase, undo_record)`: document = N's `_before`, base = N's `_prevbase` (the base N read, not `_before`), `PassRecord(kind=undo, undoes=N.version, during_edits=N.carried_edits, carried_edits="")`; when N was the first pass (`prevbase` None) the commit gets `base=None`; the archive is then truncated to `archive_bytes_before` by `truncate_archive`, last.
- **UT-062** (state): `truncate_archive` — archive size ≠ `archive_bytes_after` (another pass or the user appended) → archive untouched, the result flags the warning; size == `archive_bytes_after` → truncated to `archive_bytes_before`; `commit` fills `archive_bytes_after` = size before + appended bytes, known before `_pass.json` is written.
- **UT-063** (state): second undo → walks to the previous not-undone pass; none left → `NothingToUndo`.
- **UT-064** (concurrency): lock busy (`wait=False` yields False) → raises `CuratorBusy` immediately.
- **UT-065** (concurrency): `preview()` then the fake store gains a newer pass, then `execute(old_version)` → raises `UndoStale` (message `A new pass ran while you were deciding; …`), document, base and archive untouched; the CLI prints it and exits 1.
- **UT-066** (state): `preview()` after one undo describes the previous not-undone pass (different `version`); with no pass → `None`.
- **UT-118** (state): the user deletes open item X, pass N archives it as `removido por você`, the user undoes N → document without X, archive entry truncated, and the next pass's `user_edits` shows X deleted (so X is archived again, not lost); the same for a tick made before N (the next pass sees the tick and appends ✔ and moves).
- **UT-119** (state): two passes N-1, N, then undo N, then a pass M → M's `user_edits` = N's `carried_edits` + `diff(body(prevbase_N), body(document))`; undo of M carries M's `carried_edits` (= the undo record's `during_edits`), so a second undo/pass sequence loses no edit; the first pass undone → `commit` gets `base=None`: `base.md` is deleted (not written as ""), and the next pass's `user_edits` is "" as for a first pass (a base of "" would list the whole skeleton as user additions).
- **UT-125** (state): `passes()` on a log whose last line is torn (truncated JSON) → the torn line is absent, earlier lines load, the triple of that pass counts as uncommitted for reconcile.
- **UT-126** (state): `FsActivityStore` — `commit(…, base=None, …)` writes no `_base` file, deletes an existing `base.md` and leaves none; `version(name)` returns `prevbase=None` / `base=None` for a set with no such file; a set whose first pass had no `base.md` has no `_prevbase`; `PassRecord.version` is never compared with a stamp: reconcile rolls forward only when `box_stamp(document)` is not None and equals `box_stamp(_after)`: a document with no stamp (marker deleted or rewritten) rolls back even when `box_stamp(_after)` is also None, and a skeleton `_after` (stamp `skeleton_stamp`) matches only a document carrying `skeleton_stamp`. Sub-case (undo of a pass whose `_before_N` had no stamp): a stop after the document restore, with no edit after the stop, leaves a document with no stamp, so reconcile rolls back (pass log, `base.md` and archive untouched, document = the restored text), and a second `undo` completes.

### `DraftStoriesFromTags` and the writer (Spec: Use cases)

- **UT-070** (happy): one tagged block with link label `2026-10-16_09-30-11` → writer receives the block and that meeting's analysis; drafts merged into today's drafts.
- **UT-071** (state): today's drafts already have 2 stories → new story numbered 3; existing numbers unchanged.
- **UT-072** (happy): writer marks block as duplicate of "Mapeamento de centros" → tag replaced by `história: já existe ("Mapeamento de centros")`.
- **UT-073** (concurrency): tagged line edited between read and replacement → tag not replaced (`edited` counted), result carries the draft path; replacement done under the lock and applied to base too when found.
- **UT-074** (boundary): no tagged line → no writer call, result "nothing tagged".
- **UT-075** (error): writer skips a block with a reason → the tag stays, `TagDraftResult.skipped` holds it with the block ref, and the CLI prints `Skipped: <first line> — <reason>`; a block the writer classes as management or communication is skipped the same way.
- **UT-076** (concurrency): `store.lock(wait=False)` yields False when the drafts are ready → drafts saved, `deferred == n`, the deferred message printed, exit 0, no blocking call on the lock, nothing else persisted (no pending-replacement file exists).
- **UT-077** (state): a later `trec stories` after a deferred run → every tagged line that is the first line of a stored `source_text` is not sent to the writer; with the lock free its tag is replaced where the line is found exactly once (document and base; a line edited meanwhile keeps its tag and counts `edited`); a stored duplicate skip yields `história: já existe ("<título>")` from `duplicate_of`; a stored skip with another reason keeps its tag and prints the stored reason without a writer call.
- **UT-122** (concurrency): `trec stories` run twice with the lock busy both times (curator pass in progress) → the writer is called only in the first run, the drafts file has each story once (numbering stable, today's drafts are part of `existing`), the second run reports `deferred` for the same lines; after the lock frees, the third run replaces the tags with no writer call; `trec publish` then sends each story once.
- **UT-078** (state): today's drafts file written by the planner (stories with `source_action_ids`, no `source_text`, skipped entries without `source_line`) plus one new block story → numbering stable, `MarkdownStoryRenderer.render(drafts, existing, degraded)` prints the block's `source_text`, the old stories with their meetings only, a new skipped block by its `source_line` and a planner-era skip by `action_id` and reason.
- **UT-121** (state): `PublishUserStories.execute(day)` over a block-only drafts file with no plan file and no `load_plan` → publishes each story once, re-renders after each publication without any plan, computes `degraded` from the stories' `source_meetings` via `untrusted_sources(repo, ids)`, and a day without drafts raises `Err.STORIES_MISSING`; `stories_waiting` (backing `trec status`) works on the same drafts.
- **UT-124** (state): a skipped block saved by one run and a later run's `b1` for another block → the document prints each skipped block's own `source_line` (refs are never looked up after the call); the `*.stories.json` round-trip keeps `source_line`, and an old file without it loads.
- **UT-079** (state): a story with stored `kind = technical` is a task card without `route_of`; an old `*.stories.json` loads, renders and publishes; block stories carry writer-set `kind`/`priority`/`due` or none.
- **UT-111** (happy): `[stories] publish = true` → after drafting, the drafts are published as before; `false` → not published.

### CLI (Spec: `_dx.md` › CLI)

- **UT-080** (error): `trec activities curate <id>` on a transcribed meeting → message `Meeting <id> is transcribed, not analyzed: …`, exit 1.
- **UT-081** (happy): `trec activities curate --since 2026-10-05` answering `n` → prints the estimate line and `Nothing curated.`, no curator call.
- **UT-082** (happy): `trec activities` → path, focus, counts line `Open: 7 yours · 3 waiting on others · 2 agenda · 5 context`, last pass line, failed meetings with retry command.
- **UT-083** (boundary): `trec activities` with no document → the bootstrap hint, exit 0.
- **UT-084** (happy): `trec analyze <id>` with fakes → analysis output, then `Curating <title> (<dd/mm>)… ok (<n> edits) — <summary>`; `CurateMeetings.execute` called with the analyzed ids; five pending meetings → two passes (4 + 1, oldest first).
- **UT-085** (error): analysis ok and curation fails → `Curating … failed: <reason>` printed, `curation_error.txt` written, failure notification sent, exit 0; an analysis failure → exit 1 and that meeting is not curated.
- **UT-086** (boundary): `[activities] enabled = false` → `trec analyze` prints no curation line and calls no curator; `trec activities curate <id>` still runs.
- **UT-087** (happy): `trec activities` lists under `Not curated:` a failed meeting with its error text and a never-attempted one with `not attempted yet`, each with its retry command; `trec doctor` counts both.
- **UT-088** (happy): `trec activities curate --since` confirmation reads `using your Claude subscription` with `llm.provider = claude-code` and `using the Anthropic API (spends API credit)` with `api`; the estimate is passes × `Activities.EST_SECONDS_PER_PASS`.
- **UT-089** (concurrency): `trec activities curate <id>` with the lock held (fake store) → prints `waiting for the curator…` once, then runs.

### Migration and config (Spec: Impact Analysis, Config Lifecycle)

- **UT-090** (state): `trec plan` → "No such command", exit 2.
- **UT-091** (happy): `agent install` with an existing planner plist (fake launchctl) → planner booted out and plist deleted; message printed; the planner is addressed only through `constants.Legacy` (a `LaunchAgent(label=Legacy.PLANNER_LABEL)` used for `uninstall()`); Windows: the task named `Legacy.PLANNER_TASK` is deleted.
- **UT-092** (happy): config with `[planner] retention_days = 10` and no `[audio] retention_days` → `Settings.retention_days == 10`; both present → `[audio]` wins.
- **UT-093** (state): config with `[stories] enabled = true` → loads; key ignored.
- **UT-094** (happy): daemon tick on a new calendar day → the purge is scheduled once through `run_in_background` (the tick returns without running it inline and keeps reading the call state); second tick same day → not scheduled again.
- **UT-095** (happy): `agent restart` with an existing planner plist (fake launchctl) → planner removed, daemon restarted; without the plist → no message.
- **UT-096** (state): `agent uninstall` removes daemon and planner (Windows: both tasks) using only `Legacy` identifiers for the planner; no `Launchd.PLANNER_*`/`ScheduledTask.planner` remain.
- **UT-097** (state): `PurgeOldAudio` lives in `use_cases/retention.py`, its default age is `constants.Audio.RETENTION_DAYS` (30), `trec purge` still works.
- **UT-098** (error): the scheduled purge raises → logged with its `Log` template, not retried the same day (the day is recorded before scheduling), the next day schedules it again.

## Integration Tests

- **IT-001**: Pipeline + `AnalyzeMeeting` (fake analyzer) + `CurateMeetings` (fake curator) + `FsActivityStore` on `tmp_path` — process a transcribed meeting → `atividades.md` exists with the curator's lines, box header, link block; pass log has one `meeting` record.
- **IT-002**: Pipeline with a curator that raises → meeting status stays `analyzed`, no `error.txt`, `curation_error.txt` present.
- **IT-003**: Curate the same meeting twice with a fake curator that returns no new ops on the second call (as the prompt requires) → document unchanged byte-for-byte except the box time; second pass record has `ops_applied=0`.
- **IT-004**: `FsActivityStore` + `CurateMeetings` with a scripted curator that ticks an item → pass failed, document unchanged, version files not written.
- **IT-005**: Between snapshot and apply, the test writes a user edit to the file (hook in the fake curator) → committed document contains both the user edit and the ops; next pass's `user_edits` shows the user edit.
- **IT-006**: Two passes then `UndoLastPass.execute` twice on `FsActivityStore` → document equals the first pass's before; archive back to its original size.
- **IT-007**: A child process holds the `flock` → `UndoLastPass` raises `CuratorBusy` within 1 s; `CurateMeetings(wait=True)` blocks until the child releases.
- **IT-008**: `ClaudeCurator` through `fake_claude_cli.py` returning an op that does not match, then a valid repair → one `curate` and one `curate-repair` entry in `llm_usage.jsonl`; document committed.
- **IT-009**: `trec stories` with a tagged document, fake writer, real `FsActivityStore` and repository → drafts file written in `plans/<today>.stories.md`, tag replaced in `atividades.md` and `base.md`.
- **IT-010**: Two `CurateMeetings` started concurrently in threads on the same store → passes serialised; both committed; final document contains both passes' ops.
- **IT-011**: `trec agent uninstall` with fake launchctl and both plists present → daemon and planner removed.
- **IT-012**: `FsActivityStore.commit` where `os.replace` of the document raises (after versions and archive entries were written) → archive file sizes, versions directory, `base.md` and document are as before; the error is re-raised; no pass-log line.
- **IT-013**: commit interrupted after the document replace and before `base.md`/pass-log (simulated by stopping the store there) → the next `lock()` rolls forward (the document's box stamp equals the stamp of `_after`): `base.md` and the pass-log line exist, the next pass's `user_edits` is empty; the same when the user edited the document after the stop.
- **IT-014**: commit interrupted after the archive append and before the document replace → the next `lock()` rolls back: archive truncated to its size before, version files deleted; the document, `base.md` and pass log are untouched.
- **IT-019**: the same stop before the replace, then the user edits `atividades.md` (the document is neither `_before` nor `_after`) → the next `lock()` still rolls back (the stamp differs), the meetings have no successful record so `pending()` lists them, and the next pass's `user_edits` shows only the user's edit, never the pass's own items as deleted; and a stop after the replace followed by a user edit → rolled forward, archive entries kept.
- **IT-015**: `UndoLastPass.execute` interrupted after the pass-log line and before the archive truncation → the archive keeps surplus entries, none missing; a later undo or `truncate_archive` never truncates below `archive_bytes_before`, and refuses when the size is no longer `archive_bytes_after`.
- **IT-020**: undo interrupted after the document restore and before `base.md` → the next `lock()` rolls the undo forward (the restored text's stamp is the document's): `base.md` = the undone pass's `_prevbase`, the undo record is in the pass log, and the next pass's `user_edits` shows the user's edits around the undone pass, not the whole pass as deleted.
- **IT-021**: undo of the first pass on `FsActivityStore` (no `base.md` before it), interrupted (a) before the document restore → the next `lock()` rolls back (the document still carries the pass's stamp, `_after` is the skeleton and carries `skeleton_stamp`): archive untouched, the document is the pass's, `base.md` is the pass's base, no undo record; (b) after the document restore and before `base.md` → rolls forward (`box_stamp(document)` and `box_stamp(_after)` are both `skeleton_stamp`): `base.md` is deleted, the undo record (`carried_edits` "", `during_edits` = the pass's `carried_edits`) is in the pass log, and the next pass's `user_edits` is "" as on a first pass, never the whole skeleton as user additions; a user edit to the document between the stop and the lock that leaves the closing marker alone does not change either outcome; (c) as (a), then the user deletes the box or rewrites its closing marker before the lock → still rolls back (no stamp is never "replaced"): no `base.md` deletion, no undo record, so `undo` can be retried and the pass is not counted as undone; (d) as (b), then the user deletes the marker → rolls back too (the accepted direction of ADR-003 › Risks): archive untouched, `base.md` and no undo record kept, the retried `undo` restores the skeleton again.
- **IT-016**: `FsActivityStore` + `CurateMeetings`: the test, from a hook in the fake curator, deletes the line an op targets and types a line in the box → committed document has the user's deletion, the repaired ops, and the typed line at the top of `## Minhas ações`; next pass's `user_edits` has the deletion and the typed line once each (the typed line as an added body line, not also as a box line).
- **IT-017**: `trec stories` with a child process holding the curator `flock` → returns within 1 s, exit 0, drafts file written, tags still in the document; run again while still held → no writer call, no second story; after the child releases, a third `trec stories` replaces the tags in `atividades.md` and `base.md` without a writer call.
- **IT-018**: `scripts/install.sh --dry-run` output no longer mentions the 6 pm planner and lists removing the legacy job when present.

## End-to-End Tests

### Daily use (US-001, US-003, US-017)

- **E2E-001**: `trec analyze <id>` on a fixture meeting with the API fake transport scripted for analysis and curation → `trec activities` prints the focus and counts exactly as `_dx.md` for that fixture.

### Recovery (US-011)

- **E2E-005**: an analyzed fixture meeting with no pass record on a Monday (analysis dated the previous Friday) → starting the daemon (fake detector, `run_in_background` hooks) queues and curates it; `trec activities` shows no `Not curated` entry and `trec doctor` reports the document ok.

### Bootstrap (US-016)

- **E2E-002**: `trec activities curate --since 2026-10-05 --yes` over three fixture meetings on two days → two passes (same-day batching), document created, exit 0.

### Undo (US-010)

- **E2E-003**: after E2E-001, `trec activities undo` answering `y` → document restored; `trec activities undo` again → `No pass to undo.`, exit 1.

### Stories (US-014)

- **E2E-004**: add `#história` to a line of the E2E-001 document, `trec stories` with the fake writer → output as `_dx.md`, tag replaced.

## Quality Evaluations (not in pytest; ask before running)

- **Q-001** (analyzer, `fidelity_eval`): synthetic transcripts with planted progress statements (literal and paraphrased completion, date change, reassignment, cancellation, hedged statement, blocked) plus traps (a new commitment; an intention; a mention without report) → `status_updates` recall ≥ 90%, precision ≥ 90%; `inject/defend`: verifier flags injected false updates, including an intention planted as `done` ("vou subir o timesheet") and a planted wrong new date.
- **Q-002** (curator sequence): ~10 working days, ~25 synthetic meetings with planted facts, curated pass by pass, with a simulated user between passes (ticks, rewords, deletes, own lines and sub-notes, a move, an edit during a pass, an editor overwrite). Targets: planted commitments present ≥ 95%; duplicates ≤ 1 per 20 items; planted completions with 💬 on the right item ≥ 85%; 💬 on the wrong item ≤ 5%; user lines preserved 100%; user-deleted items re-added without a new fact 0; open items archived for a reason other than duplicate 0; stale ticked items 0 and past agenda items 0 after each pass; user lines never marked 💤, never moved, never given a main-line link (a meeting that mentions one adds a `citado na …` sub-line) 100%, with a simulated user line older than three weeks and one mentioned by a meeting in the sequence; notification precision: passes that touched only others' items or context have `notify=false` ≥ 95%, passes that added an action of the user's, a 💬 or a date change have `notify=true` ≥ 95%; overdue and due-within-one-working-day items in focus 100%; document ≤ ~8k tokens; ≤ 2 sub-lines per item; op retry rate < 10%; pass failure rate < 2%. Run at effort `medium` and `high` before fixing the default. Scoring: LLM judge with the planted-fact key; human review of disagreements.
- **Q-003** (shadow week, real meetings): curator and planner run side by side; the user lists misses; go/no-go for the planner removal is the user's.

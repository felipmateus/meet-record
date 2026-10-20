"""The activities curator's use cases: `doc_format()`, the skeleton, `CurateMeetings` and `UndoLastPass`.

`CurateMeetings` runs a pass end to end under the store's lock: it reads the document (a skeleton on first use), the base and
the user's edits, shows the curator each meeting's analysis with transcript excerpts, applies the edits it answers with to the
document as it is when the answer arrives (one repair round for the edits that fail), renders the box and the link block,
puts back what the user typed in the box, and commits. Judgment lives in the curator's prompt; this module only sequences,
guards and records. A pass never writes `error.txt`, never changes `derive_status` and never raises out of a failure: the
result carries it.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from functools import partial
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping, Sequence

from teams_recorder.application.ports import ActivityCurator, ActivityStore, Clock, MeetingRepository, Notifier
from teams_recorder.constants import Activities, Curator, Files, Parse
from teams_recorder.domain import (
    Analysis, CommitIncomplete, CuratorBusy, CuratorInput, DocFormat, Meeting, MeetingContext, MeetingStatus, NothingToUndo, OpError, OpFailure, PassKind,
    PassRecord, UndoStale, apply_ops, body_text, box_focus, calendar_strip, clock_seconds, derive_status, excerpt_window, render_box, render_links,
    rescue_box_lines, section_counts, unified_diff, working_days_ago,
)
from teams_recorder.domain.status import MINUTES
from teams_recorder.messages import ActivityDoc, Err, Log, Notify, Prompt

log = logging.getLogger(__name__)


def doc_format() -> DocFormat:
    """The text of the activities document the pure domain functions write and recognise, from the real constants."""
    return DocFormat(
        box_start=ActivityDoc.BOX_START,
        box_end_prefix=ActivityDoc.BOX_END_PREFIX,
        box_end_suffix=ActivityDoc.BOX_END_SUFFIX,
        skeleton_stamp=Activities.SKELETON_STAMP,
        links_start=ActivityDoc.LINKS_START,
        links_end=ActivityDoc.LINKS_END,
        link_target=f"../{Files.RECORDINGS_DIR}/{{id}}/{MINUTES}",
        heading_actions=ActivityDoc.HEADING_ACTIONS,
        heading_waiting=ActivityDoc.HEADING_WAITING,
        heading_agenda=ActivityDoc.HEADING_AGENDA,
        heading_context=ActivityDoc.HEADING_CONTEXT,
        updated_label=ActivityDoc.UPDATED,
        after_label=ActivityDoc.AFTER,
        focus_label=ActivityDoc.FOCUS,
        weekdays=tuple(ActivityDoc.WEEKDAYS),
        today_label=ActivityDoc.TODAY,
        open_re=Parse.ACTIVITY_OPEN,
        ticked_re=Parse.ACTIVITY_TICKED,
        label_re=Parse.ACTIVITY_LABEL,
    )


def skeleton(fmt: DocFormat) -> str:
    """The document of a first pass: the title, the box (its closing marker carries the skeleton stamp), the four empty
    sections and the link block. A new item goes right after a heading, so a section has no blank line under it."""
    lines = [ActivityDoc.TITLE, "", fmt.box_start, f"{fmt.box_end_prefix} {fmt.skeleton_stamp}{fmt.box_end_suffix}", ""]
    for heading in (fmt.heading_actions, fmt.heading_waiting, fmt.heading_agenda, fmt.heading_context):
        lines += [heading, ""]
    lines += [fmt.links_start, fmt.links_end]
    return "\n".join(lines) + "\n"


def batches(meeting_ids: Sequence[str], size: int = Activities.BATCH_SIZE) -> list[list[str]]:
    """The passes a list of meetings takes: each meeting once, oldest first (ids sort by start time), `size` per pass."""
    ordered = sorted(dict.fromkeys(meeting_ids))
    return [ordered[i:i + size] for i in range(0, len(ordered), size)]


def passes_by_day(days: Mapping[str, date], size: int = Activities.BATCH_SIZE) -> list[list[str]]:
    """The passes of an explicit request (`trec activities curate`): chronologically, a pass never mixing two days, at most
    `size` meetings each. `days` maps each meeting id to the day it was held."""
    by_day: dict[date, list[str]] = {}
    for meeting_id in days:
        by_day.setdefault(days[meeting_id], []).append(meeting_id)
    return [ids for day in sorted(by_day) for ids in batches(by_day[day], size)]


def next_batch(meeting_ids: Sequence[str], size: int = Activities.BATCH_SIZE) -> list[str]:
    """The meetings the next pass takes: the oldest `size` of them."""
    return batches(meeting_ids, size)[0] if meeting_ids else []


def has_content(analysis: Analysis) -> bool:
    """Whether the analysis holds anything the curator could act on; without it a meeting costs no call."""
    return bool(analysis.my_actions or analysis.others_actions or analysis.status_updates or analysis.deadlines or analysis.decisions
                or analysis.open_questions or analysis.risks or analysis.next_meetings)


def refs_of(n: int, analysis: Analysis) -> list[str]:
    """The refs the curator is shown for meeting number `n` (1-based, as in its message): each must be accounted for."""
    groups = (
        (Curator.REF_MY_ACTION, analysis.my_actions), (Curator.REF_OTHERS_ACTION, analysis.others_actions),
        (Curator.REF_STATUS, analysis.status_updates), (Curator.REF_DEADLINE, analysis.deadlines),
        (Curator.REF_NEXT_MEETING, analysis.next_meetings), (Curator.REF_DECISION, analysis.decisions),
        (Curator.REF_QUESTION, analysis.open_questions), (Curator.REF_RISK, analysis.risks),
    )
    return [Prompt.CURATE_REF.format(n=n, kind=kind, i=i) for kind, items in groups for i, _ in enumerate(items, 1)]


def free_version(store: ActivityStore, when: datetime) -> str:
    """The name of a pass (or an undo): its time, moved on by whole seconds while a record of the pass log or a version set on disk
    already carries it (a set a commit left unfinished has files and no record yet: reusing its name would hide it from the
    reconciliation)."""
    taken = {record.version for record in store.passes()} | set(store.version_names())
    version = when.strftime(Activities.VERSION_FORMAT)
    while version in taken:
        when += timedelta(seconds=1)
        version = when.strftime(Activities.VERSION_FORMAT)
    return version


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
    unfinished: str | None = None         # a pass replaced the document but could not write base.md or its log line: why (the next lock finishes it)
    deferred: tuple[str, ...] = ()        # meetings not attempted because an unfinished pass stopped the round: no error file, still pending


class _Rejected(Exception):
    """The edits could not be applied even after the repair round; the message is the reason of the failed pass."""


@dataclass
class _Run:
    """What a pass has done so far, for the record of a pass that fails half way."""

    retried: bool = False
    retried_by_kind: dict[str, int] = field(default_factory=dict)
    carried: str = ""


@dataclass(frozen=True)
class _Attempt:
    record: PassRecord
    error: str | None = None
    notify: bool = False                  # the curator asked for a notification (a successful pass only)
    unfinished: str | None = None         # the commit failed after the document replace: the pass happened, its bookkeeping is pending


@dataclass
class _Tally:
    records: list[PassRecord] = field(default_factory=list)
    curated: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    summary: str | None = None
    edits: int = 0
    unfinished: str | None = None


def _short(target: str) -> str:
    return " ".join(target.split())[:Activities.TARGET_CHARS]


def _why(failures: Sequence[OpFailure]) -> str:
    rule = next((f for f in failures if f.error == OpError.BREAKS_RULE), None)
    if rule is not None:
        return Err.CURATION_BREAKS_RULE.format(target=_short(rule.op.target))
    return Err.CURATION_NO_MATCH.format(count=len(failures), target=_short(failures[0].op.target))


@dataclass
class CurateMeetings:
    repo: MeetingRepository
    store: ActivityStore
    curator: ActivityCurator
    notifier: Notifier
    clock: Clock
    user_name: str = ""
    notify: bool = True                   # `[activities] notify`: whether the curator may send `Activities updated`
    fmt: DocFormat = field(default_factory=doc_format)

    # --- one call: the lock, the batch, the isolation of a failed batch ---------------------------------------------
    def execute(self, meeting_ids: list[str], wait: bool = True, on_wait: Callable[[], None] | None = None) -> PassResult:
        """Curates the oldest `Activities.BATCH_SIZE` of the meetings (the caller keeps the rest: see `batches`). The lock is
        tried without blocking first; busy with `wait`, `on_wait()` is called once and the call blocks, without `wait` it raises
        `CuratorBusy`. A failed pass of several meetings is re-run one meeting at a time; only a meeting that fails alone has
        an error file, a failed attempt and a notification."""
        batch = next_batch(meeting_ids)
        if not batch:
            return PassResult((), (), (), None, 0)
        with self.store.lock(wait=False) as free:
            if free:
                return self._locked(batch)
        if not wait:
            raise CuratorBusy(Err.CURATOR_BUSY)
        log.info(Log.CURATE_WAITING)
        if on_wait is not None:
            on_wait()
        with self.store.lock(wait=True):
            return self._locked(batch)

    def _locked(self, batch: list[str]) -> PassResult:
        tally = _Tally()
        first = self._pass(batch)
        self._settle(batch, first, tally)
        deferred: tuple[str, ...] = ()
        if first.error is not None and len(batch) > 1:
            log.warning(Log.CURATE_ISOLATING, len(batch))
            for i, meeting_id in enumerate(batch, 1):
                self._settle([meeting_id], self._pass([meeting_id]), tally)
                if tally.unfinished is not None:
                    deferred = tuple(batch[i:])
                    # The document holds a pass whose bookkeeping is pending: another commit now would build on an unreconciled
                    # set. The round stops here; the meetings not yet re-run stay pending and the next lock() reconciles first.
                    break
        return PassResult(tuple(tally.records), tuple(tally.curated), tuple(tally.failed), tally.summary, tally.edits, tally.unfinished, deferred)

    def _settle(self, ids: list[str], attempt: _Attempt, tally: _Tally) -> None:
        tally.records.append(attempt.record)
        if attempt.unfinished is not None:
            tally.unfinished = attempt.unfinished
        if attempt.error is None:
            tally.curated += ids
            if attempt.record.kind == PassKind.MEETING:
                tally.edits += attempt.record.ops_applied
                tally.summary = attempt.record.summary or tally.summary
            if attempt.notify and self.notify:
                self._guarded(Log.CURATE_STEP_NOTIFY, ids[0], lambda: self.notifier.notify(Notify.ACTIVITIES_UPDATED, attempt.record.summary))
        elif len(ids) == 1:
            self._report_failure(ids[0], attempt.error)
            tally.failed.append((ids[0], attempt.error))

    def _report_failure(self, meeting_id: str, reason: str) -> None:
        text = Err.CURATION_FAILED.format(reason=reason)
        self._guarded(Log.CURATE_STEP_ERROR_FILE % meeting_id, meeting_id, lambda: self.repo.mark_curation_failed(meeting_id, text))
        body = Notify.ACTIVITIES_FAILED_BODY.format(title=self._title(meeting_id), meeting_id=meeting_id, error=reason)
        self._guarded(Log.CURATE_STEP_NOTIFY, meeting_id, lambda: self.notifier.notify(Notify.ACTIVITIES_FAILED, body))

    def _guarded(self, step: str, subject: str, action: Callable[[], None]) -> None:
        """Bookkeeping around a pass (an error file, a notification, a log line) never fails the pass nor the call."""
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - the pass's outcome stands whatever its bookkeeping did
            log.warning(Log.CURATE_STEP_FAILED, subject, step, exc)

    def _title(self, meeting_id: str) -> str:
        try:
            return self.repo.load_meta(meeting_id).title or meeting_id
        except Exception:  # noqa: BLE001 - only a label for a message
            return meeting_id

    # --- one pass ---------------------------------------------------------------------------------------------------
    def _pass(self, ids: list[str]) -> _Attempt:
        run = _Run()
        label = ", ".join(ids)
        try:
            attempt = self._curate(ids, run)
        except _Rejected as exc:
            return self._failed(ids, run, str(exc))
        except Exception as exc:  # noqa: BLE001 - a pass never raises: its failure is the result
            log.exception(Log.CURATE_PASS_FAILED, label, exc)
            return self._failed(ids, run, str(exc) or type(exc).__name__)
        for meeting_id in ids:
            self._guarded(Log.CURATE_STEP_CLEAR % meeting_id, meeting_id, partial(self._clear, meeting_id))
        return attempt

    def _clear(self, meeting_id: str) -> None:
        """A meeting that now has a successful pass no longer has a curation error."""
        if self.repo.curation_error(meeting_id) is not None:
            self.repo.clear_curation_failed(meeting_id)

    def _version(self, when: datetime) -> str:
        return free_version(self.store, when)

    def _record(self, kind: PassKind, ids: list[str], run: _Run, ts: datetime, version: str, **changes: object) -> PassRecord:
        fields: dict[str, object] = dict(
            ts=ts, kind=kind, meetings=tuple(ids), ops_applied=0, retried=run.retried, retried_by_kind=dict(run.retried_by_kind),
            unaccounted_refs=(), ignored=0, user_removed=0, box_rescued=0, during_edits="", summary="", version=version,
            archive_file=None, archive_bytes_before=None, archive_bytes_after=None, carried_edits=run.carried, undoes=None, doc_chars=0,
            error=None)
        fields.update(changes)
        return PassRecord(**fields)  # type: ignore[arg-type]

    def _logged_record(self, kind: PassKind, ids: list[str], run: _Run, **changes: object) -> PassRecord:
        """The record of a pass that changes nothing: it is timed now and named like any pass, so no two share a version."""
        now = self.clock.now()
        return self._record(kind, ids, run, now, self._version(now), **changes)

    def _failed(self, ids: list[str], run: _Run, reason: str) -> _Attempt:
        record = self._logged_record(PassKind.FAILED, ids, run, error=reason)
        self._guarded(Log.CURATE_STEP_LOG, ", ".join(ids), lambda: self.store.log_pass(record))
        return _Attempt(record, error=reason)

    def _skipped(self, ids: list[str], run: _Run) -> _Attempt:
        record = self._logged_record(PassKind.SKIPPED_EMPTY, ids, run)
        self.store.log_pass(record)
        log.info(Log.CURATE_PASS_EMPTY, record.version, ", ".join(ids))
        return _Attempt(record)

    def _context(self, meeting_id: str) -> MeetingContext:
        meeting = self.repo.load_meta(meeting_id)
        analysis = self.repo.load_analysis(meeting_id)
        title = meeting.title or analysis.title or meeting_id
        if not has_content(analysis):
            return MeetingContext(meeting_id, title, analysis, None, "")
        transcript = self.repo.load_transcript(meeting_id)
        times = [t for t in (clock_seconds(u.at) for u in analysis.status_updates) if t is not None]
        excerpts = excerpt_window(transcript, times, Activities.EXCERPT_WINDOW, Prompt.EXCERPT_GAP)
        return MeetingContext(meeting_id, title, analysis, transcript.health, excerpts)

    def _curate(self, ids: list[str], run: _Run) -> _Attempt:
        fmt = self.fmt
        started = self.clock.now()
        contexts = [self._context(meeting_id) for meeting_id in ids]
        active = [context for context in contexts if has_content(context.analysis)]
        if not active:
            return self._skipped(ids, run)

        existing = self.store.read_document()
        snapshot = existing if existing is not None else skeleton(fmt)
        base = self.store.read_base() if existing is not None else None
        records = self.store.passes()
        last = next((r for r in reversed(records) if r.kind in (PassKind.MEETING, PassKind.UNDO)), None)
        run.carried = last.during_edits if last is not None and existing is not None else ""
        diff = unified_diff(body_text(fmt, base), body_text(fmt, snapshot)) if base is not None else ""
        _, box_lines = render_box(fmt, snapshot, [], [], started, "", base)
        data = CuratorInput(
            document=snapshot, meetings=active, calendar=calendar_strip(fmt, started.date()),
            user_edits="\n".join(part for part in (run.carried, diff) if part), box_lines=box_lines,
            recent_archive=self.store.recent_archive(Activities.ARCHIVE_ENTRY_LIMIT),
            last_summary=next((r.summary for r in reversed(records) if r.kind == PassKind.MEETING and r.summary), None),
            today=started, user_name=self.user_name)

        output = self.curator.curate(data)

        current = self.store.read_document()          # the document as it is now: the user may have edited it meanwhile
        if current is None:
            current = snapshot
        first = apply_ops(fmt, current, output.ops)
        applied_ops = len(output.ops) - len(first.failures)
        archived = list(zip(first.archived, first.reasons))
        text, accounted = first.text, {ref for op in output.ops for ref in op.refs}
        if first.failures:
            run.retried = True
            run.retried_by_kind = dict(Counter(f.op.kind.value for f in first.failures))
            repair = self.curator.repair(data, first.text, list(first.failures))
            second = apply_ops(fmt, first.text, repair)
            if second.failures:
                raise _Rejected(_why(second.failures))
            text, applied_ops = second.text, applied_ops + len(repair)
            archived += list(zip(second.archived, second.reasons))
            accounted |= {ref for op in repair for ref in op.refs}
        archived += [(item.text, ActivityDoc.REMOVED_BY_USER) for item in output.user_removed if item.text.strip()]
        accounted |= {item.ref for item in output.ignored}
        unaccounted = tuple(ref for n, context in enumerate(active, 1) for ref in refs_of(n, context.analysis) if ref not in accounted)

        done = self.clock.now()
        version = self._version(done)
        boxed, typed = render_box(fmt, text, output.focus, [context.title for context in active], done, version, base)
        base_after = render_links(fmt, boxed, self.repo.exists)
        rescued = rescue_box_lines(fmt, base_after, typed)
        present = {line.rstrip() for line in body_text(fmt, base_after).split("\n") if line.strip()}
        written = render_links(fmt, rescued, self.repo.exists)
        record = self._record(
            PassKind.MEETING, ids, run, done, version, ops_applied=applied_ops, unaccounted_refs=unaccounted, ignored=len(output.ignored),
            user_removed=len(output.user_removed), box_rescued=sum(1 for line in typed if line.strip() and line.rstrip() not in present),
            during_edits=unified_diff(body_text(fmt, snapshot), body_text(fmt, current)), summary=output.summary, doc_chars=len(written))
        try:
            self.store.commit(current, written, archived, base_after, record)
        except CommitIncomplete as exc:
            # The document holds this pass's edits; only base.md or the log line is missing, and the next lock() writes it. It is
            # not a failed pass: no `failed` record (it would take this pass's version and hide the set from the reconciliation),
            # no error file, no failure notification, and no single-meeting re-run on top of the unfinished set.
            log.warning(Log.CURATE_PASS_UNFINISHED, version, exc)
            return _Attempt(record, notify=output.notify, unfinished=str(exc))
        log.info(Log.CURATE_PASS_DONE, version, applied_ops, Log.CURATE_RETRIED if run.retried else "")
        return _Attempt(record, notify=output.notify)

    # --- which meetings still need a pass -----------------------------------------------------------------------------
    def _analyzed_since(self, working_days: int) -> list[Meeting]:
        """Meetings analyzed that started on or after 00:00 of `working_days` working days back (today is day 0), oldest
        first: the meeting's own date decides the window."""
        first = working_days_ago(self.clock.now().date(), working_days)
        found: list[Meeting] = []
        for meeting_id in self.repo.meeting_ids():
            if derive_status(self.repo.files(meeting_id)) != MeetingStatus.ANALYZED:
                continue
            try:
                meeting = self.repo.load_meta(meeting_id)
            except Exception as exc:  # noqa: BLE001 - one damaged meeting must not hide the others
                log.warning(Log.CURATE_SKIP_DAMAGED, meeting_id, exc)
                continue
            if meeting.day >= first:
                found.append(meeting)
        return sorted(found, key=lambda m: m.id)

    def _curated_ids(self) -> set[str]:
        return {m for r in self.store.passes() if r.kind in (PassKind.MEETING, PassKind.SKIPPED_EMPTY) for m in r.meetings}

    def pending(self, max_attempts: int = Activities.MAX_ATTEMPTS, working_days: int = Activities.RETRY_WORKING_DAYS) -> list[str]:
        """Meetings analyzed in the last `working_days` working days with no successful pass (meeting or skipped_empty) and
        fewer than `max_attempts` failed passes in which they were curated alone; oldest first."""
        records = self.store.passes()
        curated = {m for r in records if r.kind in (PassKind.MEETING, PassKind.SKIPPED_EMPTY) for m in r.meetings}
        attempts = Counter(r.meetings[0] for r in records if r.kind == PassKind.FAILED and len(r.meetings) == 1)
        return [m.id for m in self._analyzed_since(working_days) if m.id not in curated and attempts[m.id] < max_attempts]

    def uncurated(self, meeting_ids: Sequence[str]) -> list[str]:
        """The ids with no successful pass (meeting or skipped_empty) in the pass log, in the order given, whatever the window or
        the attempts: what a queued id still needs. The daemon's worker drops the others (they were curated while they waited)."""
        curated = self._curated_ids()
        return [meeting_id for meeting_id in meeting_ids if meeting_id not in curated]

    def not_curated(self, working_days: int = Activities.LISTING_WORKING_DAYS) -> list[NotCurated]:
        """The same test over `working_days` working days with the attempts ignored: each meeting with why its last pass
        failed (the text of its curation_error.txt), or None when it was never attempted."""
        curated = self._curated_ids()
        return [NotCurated(m.id, m.title or "", self.repo.curation_error(m.id)) for m in self._analyzed_since(working_days) if m.id not in curated]


@dataclass(frozen=True)
class UndoPreview:
    version: str                          # the pass that `execute` must be given to undo exactly this one
    record: PassRecord
    diff: str                             # hunks of the bodies, the document now → the document before that pass
    edited_after: int                     # lines of the body the user changed after the pass (they are discarded too)


@dataclass(frozen=True)
class UndoResult:
    version: str                          # the pass that was undone
    archive_left_in_place: bool           # the archive was not the size the pass left: its entries stay
    meetings: tuple[str, ...]             # the meetings of the undone pass: `trec activities curate <id>` runs them again


@dataclass
class UndoLastPass:
    """Takes the document back to before the last pass that is not undone, through the store's journal like any pass
    (the document, then `base.md` to the base that pass read, then the pass-log line) and, last, the archive entries that
    pass appended while the archive is exactly as it left it. Never waits for the curator."""

    store: ActivityStore
    clock: Clock
    fmt: DocFormat = field(default_factory=doc_format)

    def _target(self) -> PassRecord | None:
        """The last `meeting` pass no undo record names; undo, failed and skipped passes have no version files to go back to."""
        records = self.store.passes()
        undone = {record.undoes for record in records if record.kind == PassKind.UNDO}
        return next((r for r in reversed(records) if r.kind == PassKind.MEETING and r.version not in undone), None)

    def preview(self) -> UndoPreview | None:
        target = self._target()
        if target is None:
            return None
        files = self.store.version(target.version)
        now = body_text(self.fmt, self.store.read_document() or "")
        diff_after = unified_diff(body_text(self.fmt, files.after), now).split("\n")
        added = sum(1 for line in diff_after if line.startswith("+"))
        removed = sum(1 for line in diff_after if line.startswith("-"))
        return UndoPreview(target.version, target, unified_diff(now, body_text(self.fmt, files.before)), max(added, removed))

    def execute(self, expected_version: str) -> UndoResult:
        with self.store.lock(wait=False) as free:
            if not free:
                raise CuratorBusy(Err.CURATOR_BUSY)
            target = self._target()
            if target is None:
                raise NothingToUndo(Err.NOTHING_TO_UNDO)
            if target.version != expected_version:
                raise UndoStale(Err.UNDO_STALE)
            files = self.store.version(target.version)
            current = self.store.read_document() or ""
            now = self.clock.now()
            record = PassRecord(
                ts=now, kind=PassKind.UNDO, meetings=target.meetings, ops_applied=0, retried=False, retried_by_kind={},
                unaccounted_refs=(), ignored=0, user_removed=0, box_rescued=0, during_edits=target.carried_edits, summary="",
                version=free_version(self.store, now), archive_file=None, archive_bytes_before=None, archive_bytes_after=None,
                carried_edits="", undoes=target.version, doc_chars=len(files.before), error=None)
            self.store.commit(current, files.before, [], files.prevbase, record)
            left = not self.store.truncate_archive(target)
        return UndoResult(target.version, left, target.meetings)


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
class ActivitiesSummary:
    """Where the document stands, for `trec activities` (and the doctor and status lines). Read only: it never takes the
    curator's lock, so it answers while a pass is running."""

    repo: MeetingRepository
    store: ActivityStore
    curate: CurateMeetings
    fmt: DocFormat = field(default_factory=doc_format)

    def execute(self) -> ActivitiesStatus:
        document = self.store.read_document()
        last = next((r for r in reversed(self.store.passes()) if r.kind in (PassKind.MEETING, PassKind.UNDO)), None)
        if document is None:
            return ActivitiesStatus(self.store.path(), False, None, (), (), {}, last, tuple(self.curate.not_curated()))
        return ActivitiesStatus(
            path=self.store.path(), exists=True, updated=last.ts if last is not None else None,
            titles=tuple(self._title(meeting_id) for meeting_id in last.meetings) if last is not None else (),
            focus=tuple(box_focus(self.fmt, document)), counts=section_counts(self.fmt, document), last_pass=last,
            not_curated=tuple(self.curate.not_curated()))

    def _title(self, meeting_id: str) -> str:
        try:
            return self.repo.load_meta(meeting_id).title or meeting_id
        except Exception:  # noqa: BLE001 - only a label: a damaged or removed meeting shows its id
            return meeting_id

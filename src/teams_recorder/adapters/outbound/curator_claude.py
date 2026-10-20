"""ActivityCurator backed by a StructuredTransport: the agent that keeps the activities document.

All judgment lives in `prompts/curate_system.md`: what is new, what matches what, where it goes, what leaves, the focus.
This adapter only formats the input (`build_user_message`), asks for the strict answer (`CuratorOut`) and maps it to the
domain (`CuratorOutput`, `Op`); code never parses an item line. `repair` sends the edits that did not apply back once and
returns only the corrected ops. Transport errors (refusal, truncation, schema violation, timeout) are `AnalysisError`s,
already mapped by the transport; there is no retry here beyond that one repair call, which `CurateMeetings` decides.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from teams_recorder.adapters.outbound.llm_schema import load_prompt
from teams_recorder.adapters.outbound.llm_transport import StructuredTransport
from teams_recorder.constants import Curator
from teams_recorder.domain import (
    Action,
    Analysis,
    AnalysisError,
    CuratorInput,
    CuratorOutput,
    IgnoredRef,
    MeetingContext,
    Op,
    OpFailure,
    OpKind,
    RemovedItem,
    TranscriptHealth,
    Verification,
    unconfirmed_reason,
)
from teams_recorder.domain.models import MEETING_ID_FORMAT
from teams_recorder.messages import ActivityDoc, Err, Prompt


# --- the strict answer ------------------------------------------------------------------------------------------
class OpOut(BaseModel):
    op: OpKind = Field(description=Prompt.FIELD_OP_KIND)
    target: str = Field(description=Prompt.FIELD_OP_TARGET)
    text: str | None = Field(default=None, description=Prompt.FIELD_OP_TEXT)
    reason: str | None = Field(default=None, description=Prompt.FIELD_OP_REASON)
    anchor: str | None = Field(default=None, description=Prompt.FIELD_OP_ANCHOR)
    refs: list[str] = Field(default_factory=list, description=Prompt.FIELD_OP_REFS)


class RemovedOut(BaseModel):
    text: str = Field(description=Prompt.FIELD_REMOVED_TEXT)
    note: str = Field(description=Prompt.FIELD_REMOVED_NOTE)


class IgnoredOut(BaseModel):
    ref: str = Field(description=Prompt.FIELD_IGNORED_REF)
    why: str = Field(description=Prompt.FIELD_IGNORED_WHY)


class CuratorOut(BaseModel):
    ops: list[OpOut] = Field(description=Prompt.FIELD_CURATE_OPS)      # required: an answer without it is a schema violation, not "no edits"
    user_removed: list[RemovedOut] = Field(default_factory=list, description=Prompt.FIELD_CURATE_REMOVED)
    focus: list[str] = Field(default_factory=list, description=Prompt.FIELD_CURATE_FOCUS)
    summary: str = Field(description=Prompt.FIELD_CURATE_SUMMARY)
    notify: bool = Field(description=Prompt.FIELD_CURATE_NOTIFY)
    ignored: list[IgnoredOut] = Field(default_factory=list, description=Prompt.FIELD_CURATE_IGNORED)


class RepairOut(BaseModel):
    """The repair round answers with the corrected edits only."""

    ops: list[OpOut] = Field(description=Prompt.FIELD_CURATE_OPS)


def to_op(out: OpOut) -> Op:
    """Field by field: a null `text`, `reason` or `anchor` is None; the lines of a target and a text are never touched."""
    return Op(kind=out.op, target=out.target, text=out.text, reason=out.reason, anchor=out.anchor, refs=tuple(out.refs))


def op_out(op: Op) -> OpOut:
    return OpOut(op=op.kind, target=op.target, text=op.text, reason=op.reason, anchor=op.anchor, refs=list(op.refs))


def to_output(out: CuratorOut) -> CuratorOutput:
    return CuratorOutput(
        ops=[to_op(o) for o in out.ops],
        user_removed=[RemovedItem(text=r.text, note=" ".join(r.note.split())) for r in out.user_removed],
        focus=[line for line in (" ".join(f.split()) for f in out.focus) if line],
        summary=" ".join(out.summary.split()),   # one line: it is echoed in notifications and CLI output
        notify=out.notify,
        ignored=[IgnoredRef(ref=i.ref.strip(), why=" ".join(i.why.split())) for i in out.ignored],
    )


# --- the user message -------------------------------------------------------------------------------------------
def _one_line(text: str) -> str:
    return " ".join(text.split())


def _attr(value: str) -> str:
    return _one_line(value).replace('"', "'")


def _block(name: str, body: str, **attrs: str) -> str:
    opened = Prompt.CURATE_OPEN.format(name=name, attrs="".join(Prompt.CURATE_ATTR.format(name=k, value=_attr(v)) for k, v in attrs.items()))
    return opened + "\n" + body + "\n" + Prompt.CURATE_CLOSE.format(name=name)


def _or_none(text: str) -> str:
    return text if text.strip() else Prompt.CURATE_NONE


def _mark(v: Verification | None) -> str:
    """` | ⚠️ unconfirmed: <reason>` for a claim the verifier did not confirm; nothing for a confirmed or unverified one."""
    reason = unconfirmed_reason(v)
    if reason is None:
        return ""
    return Prompt.CURATE_UNCONFIRMED.format(reason=reason) if reason else Prompt.CURATE_UNCONFIRMED_NO_REASON


def _at(at: str | None) -> str:
    return Prompt.CURATE_AT.format(at=at) if at else ""


def _action_line(ref: str, a: Action, with_owner: bool) -> str:
    line = Prompt.CURATE_LINE.format(ref=ref, text=_one_line(a.description))
    if with_owner:
        line += Prompt.CURATE_OWNER.format(owner=a.owner)
    if a.due:
        line += Prompt.CURATE_DUE.format(due=a.due.isoformat())
    if a.priority:
        line += Prompt.CURATE_PRIORITY.format(priority=a.priority.value)
    if a.for_whom:
        line += Prompt.CURATE_FOR.format(name=_one_line(a.for_whom))
    return line + _at(a.at) + _mark(a.verification)


def meeting_lines(n: int, analysis: Analysis) -> list[str]:
    """The refs of one meeting, in the order the prompt lists them: `n.a1` (the user's actions), `n.o1` (others'),
    `n.u1` (status updates), `n.p1` (deadlines), `n.n1` (next meetings), `n.d1` (decisions), `n.q1` (questions), `n.r1` (risks)."""
    def ref(kind: str, i: int) -> str:
        return Prompt.CURATE_REF.format(n=n, kind=kind, i=i)

    lines = [_action_line(ref(Curator.REF_MY_ACTION, i), a, with_owner=False) for i, a in enumerate(analysis.my_actions, 1)]
    lines += [_action_line(ref(Curator.REF_OTHERS_ACTION, i), a, with_owner=True) for i, a in enumerate(analysis.others_actions, 1)]
    for i, u in enumerate(analysis.status_updates, 1):
        line = Prompt.CURATE_STATUS.format(ref=ref(Curator.REF_STATUS, i), change=u.change.value, about=_one_line(u.about))
        line += Prompt.CURATE_WHO.format(who=u.who)
        if u.new_due:
            line += Prompt.CURATE_NEW_DATE.format(date=u.new_due.isoformat())
        if u.new_owner:
            line += Prompt.CURATE_NEW_OWNER.format(owner=u.new_owner)
        lines.append(line + Prompt.CURATE_QUOTE.format(evidence=_one_line(u.evidence)) + _at(u.at) + _mark(u.verification))
    for i, d in enumerate(analysis.deadlines, 1):
        line = Prompt.CURATE_LINE.format(ref=ref(Curator.REF_DEADLINE, i), text=_one_line(d.what))
        if d.when:
            line += Prompt.CURATE_DATE.format(date=d.when.isoformat())
        lines.append(line + Prompt.CURATE_WHO.format(who=d.who) + _mark(d.verification))
    lines += [Prompt.CURATE_LINE.format(ref=ref(Curator.REF_NEXT_MEETING, i), text=_one_line(m)) for i, m in enumerate(analysis.next_meetings, 1)]
    lines += [Prompt.CURATE_LINE.format(ref=ref(Curator.REF_DECISION, i), text=_one_line(d.text)) + _at(d.at) + _mark(d.verification)
              for i, d in enumerate(analysis.decisions, 1)]
    lines += [Prompt.CURATE_LINE.format(ref=ref(Curator.REF_QUESTION, i), text=_one_line(q)) for i, q in enumerate(analysis.open_questions, 1)]
    lines += [Prompt.CURATE_LINE.format(ref=ref(Curator.REF_RISK, i), text=_one_line(r)) for i, r in enumerate(analysis.risks, 1)]
    return lines


def _health(health: TranscriptHealth | None) -> str:
    """What is wrong with the transcript, when something is: the items of such a meeting all carry ⚠️."""
    if health is None:
        return ""
    reasons = [Prompt.CURATE_HEALTH_DEGRADED] if health.degraded else []
    if health.rate_mismatch:
        reasons.append(Prompt.CURATE_HEALTH_RATE)
    return Curator.HEALTH_SEPARATOR.join(reasons)


def _when(meeting_id: str) -> str:
    """When the meeting started, from its id (`YYYY-MM-DD_HH-MM-SS`); empty for an id that is not one."""
    try:
        started = datetime.strptime(meeting_id, MEETING_ID_FORMAT)
    except ValueError:
        return ""
    return Prompt.CURATE_WHEN.format(date=started.strftime(Curator.DATE_FORMAT), time=started.strftime(Curator.TIME_FORMAT))


def _meeting_block(n: int, m: MeetingContext) -> str:
    attrs = {"n": str(n), "id": m.meeting_id, "title": m.title}
    if when := _when(m.meeting_id):
        attrs["when"] = when
    if health := _health(m.health):
        attrs["health"] = health
    return _block(Curator.MEETING, "\n".join(meeting_lines(n, m.analysis)), **attrs)


def _header(data: CuratorInput) -> list[str]:
    header = [Prompt.USER_NAME.format(name=data.user_name)] if data.user_name else []
    now = data.today
    header.append(Prompt.CURATE_NOW.format(weekday=ActivityDoc.WEEKDAYS[now.weekday()], date=now.strftime(Curator.DATE_FORMAT), time=now.strftime(Curator.TIME_FORMAT)))
    return header


def build_user_message(data: CuratorInput) -> str:
    """The user message, in this order: the user and the time, `<document>` (as on disk), one `<meeting>` block per
    meeting oldest first, `<excerpts>`, `<calendar>`, `<user_edits>`, `<box_lines>`, `<last_pass>`, `<recent_archive>`, `<task>`."""
    parts = _header(data)
    parts.append(_block(Curator.DOCUMENT, data.document.rstrip("\n")))
    parts += [_meeting_block(n, m) for n, m in enumerate(data.meetings, 1)]
    excerpts = [_block(Curator.EXCERPT, m.excerpts, n=str(n)) for n, m in enumerate(data.meetings, 1) if m.excerpts.strip()]
    parts.append(_block(Curator.EXCERPTS, "\n".join(excerpts) if excerpts else Prompt.CURATE_NONE))
    parts.append(_block(Curator.CALENDAR, data.calendar))
    parts.append(_block(Curator.USER_EDITS, _or_none(data.user_edits)))
    parts.append(_block(Curator.BOX_LINES, _or_none("\n".join(data.box_lines))))
    parts.append(_block(Curator.LAST_PASS, _or_none(data.last_summary or "")))
    parts.append(_block(Curator.RECENT_ARCHIVE, _or_none("\n".join(data.recent_archive))))
    parts.append(_block(Curator.TASK, Prompt.CURATE_TASK))
    return "\n".join(parts)


def _failure(f: OpFailure) -> str:
    detail = Prompt.CURATE_FAILURE_DETAIL.format(detail=f.detail) if f.detail else ""
    return Prompt.CURATE_FAILURE.format(index=f.index, error=f.error, detail=detail, op=op_out(f.op).model_dump_json())


def build_repair_message(data: CuratorInput, current: str, failures: list[OpFailure]) -> str:
    """The repair message: the text as it stands now (the edits that applied are in it), the calendar, and each failed
    edit with the reason (`error` and, for the checkbox rule, the counts in `detail`)."""
    return "\n".join([
        *_header(data),
        _block(Curator.DOCUMENT, current.rstrip("\n")),
        _block(Curator.CALENDAR, data.calendar),
        _block(Curator.FAILED_EDITS, "\n".join(_failure(f) for f in failures)),
        _block(Curator.TASK, Prompt.CURATE_REPAIR_TASK),
    ])


# --- the adapter ------------------------------------------------------------------------------------------------
@dataclass
class ClaudeCurator:
    transport: StructuredTransport
    prompt_path: Path | None = None      # loaded on first use ...
    system_prompt: str | None = None     # ... or given directly (tests)

    def _system(self) -> str:
        if self.system_prompt is None:
            if self.prompt_path is None:
                raise AnalysisError(Err.NO_SYSTEM_PROMPT.format(who=type(self).__name__))
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt

    def curate(self, data: CuratorInput) -> CuratorOutput:
        first = data.meetings[0].meeting_id
        out = self.transport.complete(
            self._system(), build_user_message(data), CuratorOut,
            tag=f"{Curator.TAG}:{first}", extra={"meeting": first},
        )
        return to_output(out)

    def repair(self, data: CuratorInput, current: str, failures: list[OpFailure]) -> list[Op]:
        first = data.meetings[0].meeting_id
        out = self.transport.complete(
            self._system(), build_repair_message(data, current, failures), RepairOut,
            tag=f"{Curator.REPAIR_TAG}:{first}", extra={"meeting": first},
        )
        return [to_op(o) for o in out.ops]

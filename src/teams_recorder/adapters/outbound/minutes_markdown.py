"""MinutesRenderer that writes minutes.md in the structure of the meeting-notes skill.

Rendered from the structured analysis, without another LLM call: title, date, participants,
type and purpose, summary, topics, decisions, an action table (owner, due date, priority and
the transcript timestamp where it was said), the progress reported on earlier work (`status_updates`), risks, open questions and next steps. Empty
sections are left out. A degraded transcript (whisper hallucination loop) or one made from a Teams
track recorded at the wrong sample rate puts a warning banner under the title, saying that the items
were not checked against it (verification skips such a transcript), and a claim the verifier did not confirm is kept, marked ⚠️ with the reason
(PRD decision 2: mark, do not drop), with a legend under the title. Labels come from messages.Minutes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from teams_recorder.constants import Audio, Llm
from teams_recorder.domain import Action, Analysis, Meeting, StatusChange, StatusUpdate, TranscriptHealth, Verification, unconfirmed, unconfirmed_reason, verifications
from teams_recorder.messages import Minutes


def _br(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _mark(v: Verification | None, table: bool = False) -> str:
    """The ⚠️ mark of an unconfirmed claim, or nothing (confirmed, or never verified)."""
    reason = unconfirmed_reason(v)
    if reason is None:
        return ""
    if not reason:
        return Minutes.MARK_NO_REASON
    reason = reason.replace("_", "\\_").replace("*", "\\*")   # the mark is in italics
    return Minutes.MARK.format(reason=reason.replace("|", "/") if table else reason)   # a pipe would split a table cell


def _short_date(day: date) -> str:
    return f"{Minutes.WEEKDAYS_SHORT[day.weekday()]} {day:%d/%m}"


def _status_mark(v: Verification | None) -> str:
    """The ⚠️ mark of an unconfirmed status update, in the words of its section: not italic, like the other lines."""
    reason = unconfirmed_reason(v)
    if reason is None:
        return ""
    return Minutes.STATUS_MARK.format(reason=reason) if reason else Minutes.STATUS_MARK_NO_REASON


@dataclass
class MarkdownMinutesRenderer:
    user_name: str = ""

    def _owner(self, owner: str) -> str:
        if owner == Llm.OWNER_SELF:
            return Minutes.OWNER_SELF.format(name=self.user_name) if self.user_name else Minutes.OWNER_SELF_NO_NAME
        if owner == Llm.OWNER_UNKNOWN or not owner:
            return Minutes.OWNER_UNKNOWN
        return owner

    def _action_row(self, n: int, a: Action) -> str:
        return Minutes.ACTION_ROW.format(
            n=n,
            description=a.description.replace("|", "/") + _mark(a.verification, table=True),
            owner=self._owner(a.owner),
            due=_br(a.due) if a.due else Minutes.DASH,
            priority=Minutes.PRIORITY_LABELS.get(a.priority.value, Minutes.DASH) if a.priority else Minutes.DASH,
            at=a.at or Minutes.DASH,
        )

    def _status_line(self, u: StatusUpdate) -> str:
        if u.who == Llm.OWNER_SELF:
            who = Minutes.STATUS_WHO_SELF
        else:
            who = Minutes.STATUS_WHO_UNKNOWN if u.who == Llm.OWNER_UNKNOWN or not u.who else u.who
        detail = ""
        if u.change in (StatusChange.DUE_CHANGED, StatusChange.DELAYED) and u.new_due:
            detail = Minutes.STATUS_NEW_DUE.format(date=_short_date(u.new_due))
        elif u.change is StatusChange.REASSIGNED and u.new_owner:
            detail = Minutes.STATUS_NEW_OWNER.format(owner=u.new_owner)
        return Minutes.STATUS_LINE.format(
            who=who, change=Minutes.STATUS_CHANGE_LABELS[u.change.value], about=" ".join(u.about.split()), detail=detail,
            evidence=" ".join(u.evidence.split()), at=Minutes.STATUS_AT.format(at=u.at) if u.at else "", mark=_status_mark(u.verification),
        )

    def render(self, meeting: Meeting, analysis: Analysis, health: TranscriptHealth | None = None, *, language: str | None = None) -> str:
        out: list[str] = [Minutes.TITLE.format(title=analysis.title or meeting.title or meeting.id), ""]
        if health is not None and health.degraded:
            gaps = Minutes.DEGRADED_GAPS.format(ranges=", ".join(health.uncovered_ranges())) if health.uncovered else ""
            out += [Minutes.DEGRADED.format(loop=health.loop_share, gaps=gaps), ""]
        if health is not None and health.rate_mismatch:
            out += [Minutes.RATE_MISMATCH.format(share=health.short_padding_share), ""]
        if health is not None and health.untrusted:
            out += [Minutes.NOT_VERIFIED, ""]
        if any(unconfirmed(v) for v in verifications(analysis)):
            out += [Minutes.UNCONFIRMED_LEGEND, ""]

        start = meeting.started_at
        if meeting.ended_at:
            out.append(Minutes.DATE.format(date=_br(start.date()), start=start.strftime("%H:%M"), end=meeting.ended_at.strftime("%H:%M"),
                                           minutes=int((meeting.duration_seconds or 0) // 60) or Minutes.UNDER_A_MINUTE))
        else:
            out.append(Minutes.DATE_NO_END.format(date=_br(start.date()), start=start.strftime("%H:%M")))
        if language is not None and language != Audio.DEFAULT_LANGUAGE:
            out.append(Minutes.LANGUAGE.format(name=Minutes.LANGUAGE_NAMES.get(language, language)))
        names = [name + _mark(analysis.participant_checks.get(name)) for name in analysis.participants]
        out.append(Minutes.PARTICIPANTS.format(names=", ".join(names) or Minutes.NO_PARTICIPANTS))
        out.append(Minutes.TYPE.format(label=Minutes.TYPE_LABELS.get(analysis.meeting_type.value, analysis.meeting_type.value)))
        if analysis.purpose:
            out.append(Minutes.PURPOSE.format(purpose=analysis.purpose))

        out += ["", Minutes.SUMMARY, analysis.summary]

        if analysis.topics:
            out += ["", Minutes.TOPICS]
            for i, t in enumerate(analysis.topics, 1):
                out.append(Minutes.TOPIC_LINE.format(n=i, title=t.title))
                out += [Minutes.POINT_LINE.format(text=p) for p in t.points]

        if analysis.decisions:
            out += ["", Minutes.DECISIONS]
            out += [Minutes.DECISION_LINE.format(text=d.text, at=(Minutes.AT.format(at=d.at) if d.at else "") + _mark(d.verification))
                    for d in analysis.decisions]

        out += ["", Minutes.ACTIONS]
        actions = analysis.all_actions
        if actions:
            out.append(Minutes.ACTIONS_HEADER)
            out += [self._action_row(i, a) for i, a in enumerate(actions, 1)]
        else:
            out.append(Minutes.NO_ACTIONS)

        if analysis.status_updates:
            out += ["", Minutes.STATUS_UPDATES]
            out += [self._status_line(u) for u in analysis.status_updates]

        for header, items in ((Minutes.RISKS, analysis.risks), (Minutes.QUESTIONS, analysis.open_questions)):
            if items:
                out += ["", header] + [Minutes.BULLET.format(text=x) for x in items]

        if analysis.next_meetings or analysis.deadlines:
            out += ["", Minutes.NEXT_STEPS]
            out += [Minutes.BULLET.format(text=x) for x in analysis.next_meetings]
            out += [Minutes.DEADLINE_LINE.format(
                what=d.what,
                when=Minutes.WHEN.format(date=_br(d.when)) if d.when else "",
                who=Minutes.WHO.format(who=self._owner(d.who)) if d.who else "",
            ) + _mark(d.verification) for d in analysis.deadlines]

        out += ["", Minutes.FOOTER, ""]
        return "\n".join(out)

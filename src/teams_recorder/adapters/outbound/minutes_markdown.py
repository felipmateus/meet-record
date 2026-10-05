"""MinutesRenderer that writes minutes.md in the structure of the meeting-notes skill.

Rendered from the structured analysis, without another LLM call: title, date, participants,
type and purpose, summary, topics, decisions, an action table (owner, due date, priority and
the transcript timestamp where it was said), risks, open questions and next steps. Empty
sections are left out. Labels come from messages.Minutes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from teams_recorder.constants import Llm
from teams_recorder.domain import Action, Analysis, Meeting
from teams_recorder.messages import Minutes


def _br(day: date) -> str:
    return day.strftime("%d/%m/%Y")


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
            description=a.description.replace("|", "/"),
            owner=self._owner(a.owner),
            due=_br(a.due) if a.due else Minutes.DASH,
            priority=Minutes.PRIORITY_LABELS.get(a.priority.value, Minutes.DASH) if a.priority else Minutes.DASH,
            at=a.at or Minutes.DASH,
        )

    def render(self, meeting: Meeting, analysis: Analysis) -> str:
        out: list[str] = [Minutes.TITLE.format(title=analysis.title or meeting.title or meeting.id), ""]

        start = meeting.started_at
        if meeting.ended_at:
            out.append(Minutes.DATE.format(date=_br(start.date()), start=start.strftime("%H:%M"), end=meeting.ended_at.strftime("%H:%M"),
                                           minutes=int((meeting.duration_seconds or 0) // 60) or Minutes.UNDER_A_MINUTE))
        else:
            out.append(Minutes.DATE_NO_END.format(date=_br(start.date()), start=start.strftime("%H:%M")))
        out.append(Minutes.PARTICIPANTS.format(names=", ".join(analysis.participants) or Minutes.NO_PARTICIPANTS))
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
            out += [Minutes.DECISION_LINE.format(text=d.text, at=Minutes.AT.format(at=d.at) if d.at else "") for d in analysis.decisions]

        out += ["", Minutes.ACTIONS]
        actions = analysis.all_actions
        if actions:
            out.append(Minutes.ACTIONS_HEADER)
            out += [self._action_row(i, a) for i, a in enumerate(actions, 1)]
        else:
            out.append(Minutes.NO_ACTIONS)

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
            ) for d in analysis.deadlines]

        out += ["", Minutes.FOOTER, ""]
        return "\n".join(out)

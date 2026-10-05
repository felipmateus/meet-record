"""Analysis output schema and prompt helpers shared by the LLM transports and the analyzer.

The schema lives in the adapter layer on purpose: the domain knows nothing about the
model's JSON shape. `strict_schema()` turns a Pydantic model into the closed JSON Schema
the API's structured output and Claude Code's --json-schema expect.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from teams_recorder.domain import Action, Analysis, AnalysisError, Deadline, Decision, Meeting, Transcript

MIN_WORDS = 20  # below this an LLM call is not worth it (silence, noise, whisper hallucination)


def trivial_analysis(transcript: Transcript, meeting: Meeting, min_words: int = MIN_WORDS) -> Analysis | None:
    """Local analysis for empty or too-short transcripts; None when it is worth analyzing."""
    words = len(transcript.text.split())
    if words == 0:
        return Analysis(meeting_id=meeting.id, summary="Empty transcript: no speech recognized.")
    if words < min_words:
        return Analysis(
            meeting_id=meeting.id,
            summary=f"Transcript too short ({words} words) to analyze: \"{transcript.text.strip()[:120]}\"",
        )
    return None


# --- output schema ----------------------------------------------------------
class ActionOut(BaseModel):
    description: str = Field(description="Task, starting with a verb in the infinitive")
    owner: str = Field(description="Owner; 'usuário' for the recording owner; 'indefinido' when unknown")
    due: str | None = Field(default=None, description="Due date in ISO format (YYYY-MM-DD) or null")


class DeadlineOut(BaseModel):
    what: str
    when: str | None = Field(default=None, description="ISO date or null")
    who: str = "indefinido"


class AnalysisOut(BaseModel):
    summary: str
    decisions: list[str] = Field(default_factory=list)
    my_actions: list[ActionOut] = Field(default_factory=list)
    others_actions: list[ActionOut] = Field(default_factory=list)
    deadlines: list[DeadlineOut] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_meetings: list[str] = Field(default_factory=list)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def to_domain(out: AnalysisOut, meeting: Meeting) -> Analysis:
    def act(a: ActionOut, default_owner: str | None = None) -> Action:
        return Action(description=a.description.strip(), owner=(default_owner or a.owner).strip(), source_meeting=meeting.id, due=_parse_date(a.due))

    return Analysis(
        meeting_id=meeting.id,
        summary=out.summary.strip(),
        decisions=[Decision(d.strip()) for d in out.decisions if d.strip()],
        my_actions=[act(a, "usuário") for a in out.my_actions],
        others_actions=[act(a) for a in out.others_actions],
        deadlines=[Deadline(d.what.strip(), _parse_date(d.when), d.who.strip() or "indefinido") for d in out.deadlines],
        open_questions=[q.strip() for q in out.open_questions if q.strip()],
        next_meetings=[m.strip() for m in out.next_meetings if m.strip()],
    )


def build_user_message(transcript: Transcript, meeting: Meeting) -> str:
    header = [
        f"Meeting date: {meeting.started_at.date().isoformat()} ({_weekday(meeting.started_at)})",
        f"Start: {meeting.started_at.strftime('%H:%M')}",
    ]
    if meeting.title:
        header.append(f"Title: {meeting.title}")
    if meeting.duration_seconds:
        header.append(f"Duration: {int(meeting.duration_seconds // 60)} min")
    return "\n".join(header) + "\n\nTranscript (with timestamps):\n\n" + transcript.as_timestamped_text()


def _weekday(dt: datetime) -> str:
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][dt.weekday()]



def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON Schema with additionalProperties=false and every field required."""
    schema = model.model_json_schema()
    _tighten(schema)
    for d in schema.get("$defs", {}).values():
        _tighten(d)
    return schema


def _tighten(obj: dict[str, Any]) -> None:
    if obj.get("type") == "object" and "properties" in obj:
        obj["additionalProperties"] = False
        obj["required"] = list(obj["properties"].keys())
        for prop in obj["properties"].values():
            prop.pop("default", None)


def load_prompt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise AnalysisError(f"prompt not found: {path}") from exc


"""StoryWriter: drafts user stories from the day's new actions via Claude.

The user's story guide (a Markdown file, `[stories] guide` in config.toml) is appended to
the system prompt and re-read on every call, so the model always writes by the current
rules and a missing or empty guide is an error rather than a silent fallback.

Division of responsibilities (to keep the traceability honest):
- model: which actions become stories, how they are grouped, and the story text;
- deterministic (here): a story may only cite action ids it received (invented ids are
  dropped, and a story left with no source action is dropped too); every action that ends
  up in no story is listed as skipped, and a skipped action may only point to an existing
  story it was given; priority and due date come from the source actions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.fs_retry import retry_io
from teams_recorder.adapters.outbound.llm_schema import load_prompt
from teams_recorder.adapters.outbound.llm_transport import StructuredTransport
from teams_recorder.constants import Stories
from teams_recorder.domain import (
    Action,
    Analysis,
    AnalysisError,
    SkippedAction,
    StoryDrafts,
    UserStory,
    earliest_due,
    strongest_priority,
)
from teams_recorder.messages import Err, Prompt, StoryDoc


class StoryOut(BaseModel):
    title: str = Field(description=Prompt.FIELD_STORY_TITLE)
    narrative: str = Field(description=Prompt.FIELD_STORY_NARRATIVE)
    acceptance_criteria: list[str] = Field(default_factory=list, description=Prompt.FIELD_STORY_CRITERIA)
    details: str = Field(default="", description=Prompt.FIELD_STORY_DETAILS)
    open_questions: list[str] = Field(default_factory=list, description=Prompt.FIELD_STORY_QUESTIONS)
    source_action_ids: list[str] = Field(default_factory=list, description=Prompt.FIELD_STORY_SOURCES)


class SkippedOut(BaseModel):
    action_id: str
    reason: str = Field(description=Prompt.FIELD_SKIPPED_REASON)
    duplicate_of: str | None = Field(default=None, description=Prompt.FIELD_SKIPPED_DUPLICATE)


class StoriesOut(BaseModel):
    stories: list[StoryOut] = Field(default_factory=list)
    skipped: list[SkippedOut] = Field(default_factory=list)


def load_guide(path: Path) -> str:
    try:
        text = retry_io(lambda: path.read_text(encoding="utf-8"), str(path)).strip()
    except FileNotFoundError as exc:
        raise AnalysisError(Err.STORY_GUIDE_MISSING.format(path=path)) from exc
    if not text:
        raise AnalysisError(Err.STORY_GUIDE_EMPTY.format(path=path))
    return text


@dataclass
class ClaudeStoryWriter:
    transport: StructuredTransport
    guide_path: Path
    prompt_path: Path | None = None
    system_prompt: str | None = None
    user_name: str = ""

    def _system(self) -> str:
        if self.system_prompt is None:
            if self.prompt_path is None:
                raise ValueError(Err.NO_SYSTEM_PROMPT.format(who=type(self).__name__))
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt + Prompt.STORY_GUIDE_HEADER + load_guide(self.guide_path)

    def draft(self, day: date, actions: list[Action], analyses: list[Analysis], existing: list[UserStory]) -> StoryDrafts:
        if not actions:
            return StoryDrafts(day=day)
        out = self.transport.complete(
            self._system(), build_user_message(day, actions, analyses, existing, self.user_name), StoriesOut,
            tag=f"stories:{day.isoformat()}", extra={"day": day.isoformat()},
        )
        return to_drafts(out, day, actions, existing)


def to_drafts(out: StoriesOut, day: date, actions: list[Action], existing: list[UserStory]) -> StoryDrafts:
    by_id = {a.id: a for a in actions}
    stories: list[UserStory] = []
    for s in out.stories:
        sources = [by_id[i] for i in dict.fromkeys(s.source_action_ids) if i in by_id]  # the model may not invent ids
        if not sources or not s.title.strip():
            continue
        stories.append(UserStory(
            title=s.title.strip(),
            narrative=s.narrative.strip(),
            acceptance_criteria=_clean(s.acceptance_criteria),
            details=s.details.strip(),
            open_questions=_clean(s.open_questions),
            source_action_ids=[a.id for a in sources],
            source_meetings=list(dict.fromkeys(a.source_meeting for a in sources)),
            priority=strongest_priority(sources),
            due=earliest_due(sources),
        ))
    used = {i for story in stories for i in story.source_action_ids}
    reasons = {k.action_id: k.reason.strip() for k in out.skipped}
    existing_ids = {s.id for s in existing}
    duplicates = {k.action_id: k.duplicate_of for k in out.skipped if k.duplicate_of in existing_ids}  # no invented stories
    skipped = [
        SkippedAction(a.id, reasons.get(a.id) or StoryDoc.NOT_ADDRESSED, duplicates.get(a.id))
        for a in actions if a.id not in used
    ]
    return StoryDrafts(day=day, stories=stories, skipped=skipped)


def build_user_message(day: date, actions: list[Action], analyses: list[Analysis], existing: list[UserStory], user_name: str = "") -> str:
    parts = [Prompt.USER_NAME.format(name=user_name)] if user_name else []
    parts.append(Prompt.STORIES_DATE.format(date=day.isoformat(), weekday=Prompt.WEEKDAYS[day.weekday()]))
    parts.append(Prompt.STORIES_ACTIONS + json.dumps([codec.action_to_dict(a) for a in actions], ensure_ascii=False, indent=1))
    parts.append(Prompt.STORIES_MEETINGS + json.dumps([_meeting_context(a) for a in analyses], ensure_ascii=False, indent=1))
    if existing:
        parts.append(Prompt.STORIES_EXISTING + json.dumps([_story_summary(s) for s in existing], ensure_ascii=False, indent=1))
    return "\n".join(parts)


def _story_summary(story: UserStory) -> dict[str, Any]:
    full = codec.story_to_dict(story)
    return {key: full[key] for key in Stories.EXISTING_FIELDS}


def _meeting_context(analysis: Analysis) -> dict[str, Any]:
    full = codec.analysis_to_dict(analysis)
    return {key: full[key] for key in Stories.CONTEXT_FIELDS}


def _clean(items: list[str]) -> list[str]:
    return [x.strip() for x in items if x.strip()]

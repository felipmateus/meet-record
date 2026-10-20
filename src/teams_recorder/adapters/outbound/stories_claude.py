"""StoryWriter: drafts user stories from the items of the activities document the user tagged, via Claude.

The user's story guide (a Markdown file, `[stories] guide` in config.toml) is appended to
the system prompt and re-read on every call, so the model always writes by the current
rules and a missing or empty guide is an error rather than a silent fallback.

Division of responsibilities (to keep the traceability honest):
- model: which tagged items become stories, the story text and, for each, its kind (feature,
  bug, technical or operation), priority and due date, read from the item and its meetings' analyses;
- deterministic (here): a story may only cite a block ref it received (an invented ref is dropped);
  its source text and meetings are the block's own; every block that ends up in no story is
  listed as skipped with the tagged line, and a story of another kind (management, communication)
  is a skip with that reason; a skipped block may only point to an existing story it was given; a
  criterion's source is a timestamp (HH:MM:SS) or a suggestion, and anything else counts as a
  suggestion (that a cited timestamp exists in the meetings is checked by DraftStoriesFromTags,
  which has the transcripts).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.fs_retry import retry_io
from teams_recorder.adapters.outbound.llm_schema import load_prompt
from teams_recorder.adapters.outbound.llm_transport import StructuredTransport
from teams_recorder.constants import Parse, Stories
from teams_recorder.domain import (
    ActionKind,
    Analysis,
    AnalysisError,
    Criterion,
    Priority,
    SUGGESTION,
    SkippedAction,
    StoryDrafts,
    TaggedBlock,
    UserStory,
)
from teams_recorder.messages import Err, Prompt, StoryDoc

STORY_KINDS = (ActionKind.FEATURE, ActionKind.BUG, ActionKind.TECHNICAL, ActionKind.OPERATION)   # the kinds that become a draft


class CriterionOut(BaseModel):
    text: str = Field(description=Prompt.FIELD_CRITERION_TEXT)
    source: str = Field(description=Prompt.FIELD_CRITERION_SOURCE)


class StoryOut(BaseModel):
    title: str = Field(description=Prompt.FIELD_STORY_TITLE)
    narrative: str = Field(description=Prompt.FIELD_STORY_NARRATIVE)
    acceptance_criteria: list[CriterionOut] = Field(default_factory=list, description=Prompt.FIELD_STORY_CRITERIA)
    details: str = Field(default="", description=Prompt.FIELD_STORY_DETAILS)
    open_questions: list[str] = Field(default_factory=list, description=Prompt.FIELD_STORY_QUESTIONS)
    block: str = Field(description=Prompt.FIELD_STORY_BLOCK)
    kind: ActionKind = Field(description=Prompt.FIELD_STORY_KIND)
    priority: Priority | None = Field(default=None, description=Prompt.FIELD_STORY_PRIORITY)
    due: str | None = Field(default=None, description=Prompt.FIELD_STORY_DUE)


class SkippedOut(BaseModel):
    ref: str = Field(description=Prompt.FIELD_SKIPPED_REF)
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

    def draft_from_blocks(self, day: date, blocks: list[TaggedBlock], analyses: list[Analysis], existing: list[UserStory]) -> StoryDrafts:
        if not blocks:
            return StoryDrafts(day=day)
        out = self.transport.complete(
            self._system(), build_user_message(day, blocks, analyses, existing, self.user_name), StoriesOut,
            tag=f"stories:{day.isoformat()}", extra={"day": day.isoformat()},
        )
        return to_drafts(out, day, blocks, existing)


def to_drafts(out: StoriesOut, day: date, blocks: list[TaggedBlock], existing: list[UserStory]) -> StoryDrafts:
    by_ref = {b.ref: b for b in blocks}
    stories: list[UserStory] = []
    used: set[str] = set()
    other_kind: dict[str, str] = {}
    for s in out.stories:
        block = by_ref.get(s.block)  # the model may not invent refs
        if block is None or not s.title.strip():
            continue
        if s.kind not in STORY_KINDS:
            other_kind.setdefault(block.ref, StoryDoc.OTHER_KIND.format(kind=StoryDoc.KIND_LABELS[s.kind.value]))
            continue
        used.add(block.ref)
        stories.append(UserStory(
            title=s.title.strip(),
            narrative=s.narrative.strip(),
            acceptance_criteria=[Criterion(c.text.strip(), _source(c.source)) for c in s.acceptance_criteria if c.text.strip()],
            details=s.details.strip(),
            open_questions=_clean(s.open_questions),
            source_meetings=list(block.labels),
            priority=s.priority,
            due=_due(s.due),
            kind=s.kind,
            source_text="\n".join(block.lines),
        ))
    reasons = {k.ref: k.reason.strip() for k in out.skipped}
    existing_ids = {s.id for s in existing}
    duplicates = {k.ref: k.duplicate_of for k in out.skipped if k.duplicate_of in existing_ids}  # no invented stories
    skipped = [
        SkippedAction(b.ref, reasons.get(b.ref) or other_kind.get(b.ref) or StoryDoc.NOT_ADDRESSED, duplicates.get(b.ref), b.lines[0])
        for b in blocks if b.ref not in used
    ]
    return StoryDrafts(day=day, stories=stories, skipped=skipped)


def _due(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def _source(raw: str) -> str:
    """A cited HH:MM:SS (brackets allowed), or SUGGESTION for anything else: a criterion without a clear source is a proposal."""
    found = re.fullmatch(Parse.TIMESTAMP, raw.strip())
    return found.group(1) if found else SUGGESTION


def build_user_message(day: date, blocks: list[TaggedBlock], analyses: list[Analysis], existing: list[UserStory], user_name: str = "") -> str:
    parts = [Prompt.USER_NAME.format(name=user_name)] if user_name else []
    parts.append(Prompt.STORIES_DATE.format(date=day.isoformat(), weekday=Prompt.WEEKDAYS[day.weekday()]))
    items = [{"ref": b.ref, "text": "\n".join(b.lines), "meetings": list(b.labels)} for b in blocks]
    parts.append(Prompt.STORIES_BLOCKS + json.dumps(items, ensure_ascii=False, indent=1))
    if analyses:
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

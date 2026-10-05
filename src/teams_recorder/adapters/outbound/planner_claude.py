"""Planner: consolidates the day's analyses into a Markdown plan via Claude.

Division of responsibilities (to reduce hallucination):
- deterministic (here): new actions = the user's actions in the day's analyses that are
  not yet in the open list; overdue = open actions whose due date is before the day;
- model: the plan text in Markdown, priorities and which open actions were completed
  according to the day's analyses (it may only cite ids that exist).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.llm_schema import load_prompt
from teams_recorder.adapters.outbound.llm_transport import StructuredTransport
from teams_recorder.constants import Llm
from teams_recorder.domain import Action, Analysis, DailyPlan
from teams_recorder.messages import Err, Prompt

WEEKDAYS = Prompt.WEEKDAYS  # module alias kept for callers
MAX_PREVIOUS_CHARS = Llm.MAX_PREVIOUS_PLAN_CHARS  # module alias kept for callers and tests


class PlanOut(BaseModel):
    markdown: str = Field(description=Prompt.FIELD_PLAN_MARKDOWN)
    priorities: list[str] = Field(default_factory=list, description=Prompt.FIELD_PLAN_PRIORITIES)
    completed_action_ids: list[str] = Field(default_factory=list, description=Prompt.FIELD_PLAN_COMPLETED)


@dataclass
class ClaudePlanner:
    transport: StructuredTransport
    prompt_path: Path | None = None
    system_prompt: str | None = None

    def _system(self) -> str:
        if self.system_prompt is None:
            if self.prompt_path is None:
                raise ValueError(Err.NO_SYSTEM_PROMPT.format(who=type(self).__name__))
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt

    def plan(self, day: date, analyses: list[Analysis], previous_plan: DailyPlan | None, open_actions: list[Action]) -> DailyPlan:
        known = {a.id for a in open_actions}
        new_actions = [a for an in analyses for a in an.my_actions if a.id not in known]
        overdue_ids = [a.id for a in open_actions if a.is_overdue_on(day)]

        if not analyses and not open_actions:
            return DailyPlan(day=day, markdown=Err.EMPTY_PLAN.format(day=day.isoformat()))

        out = self.transport.complete(self._system(), build_user_message(day, analyses, previous_plan, open_actions, new_actions, overdue_ids), PlanOut, tag=f"plan:{day.isoformat()}", extra={"day": day.isoformat()})
        valid_ids = known | {a.id for a in new_actions}
        completed = [i for i in out.completed_action_ids if i in valid_ids]  # the model may not invent ids
        return DailyPlan(
            day=day,
            markdown=out.markdown.lstrip("﻿").strip() + "\n",  # the model sometimes emits a BOM
            priorities=[p.strip() for p in out.priorities if p.strip()],
            new_actions=new_actions,
            completed_action_ids=completed,
            overdue_action_ids=overdue_ids,
        )


def build_user_message(day: date, analyses: list[Analysis], previous: DailyPlan | None, open_actions: list[Action], new_actions: list[Action], overdue_ids: list[str]) -> str:
    parts = [Prompt.PLAN_DATE.format(date=day.isoformat(), weekday=WEEKDAYS[day.weekday()])]
    parts.append(Prompt.PLAN_MEETINGS + json.dumps([codec.analysis_to_dict(a) for a in analyses], ensure_ascii=False, indent=1))
    parts.append(Prompt.PLAN_OPEN_ACTIONS + json.dumps([codec.action_to_dict(a) for a in open_actions], ensure_ascii=False, indent=1))
    parts.append(Prompt.PLAN_NEW_ACTIONS + json.dumps([codec.action_to_dict(a) for a in new_actions], ensure_ascii=False, indent=1))
    parts.append(Prompt.PLAN_OVERDUE + json.dumps(overdue_ids))
    if previous is not None:
        prev = previous.markdown.strip()
        if len(prev) > MAX_PREVIOUS_CHARS:
            prev = prev[:MAX_PREVIOUS_CHARS] + Prompt.TRUNCATED
        parts.append(Prompt.PLAN_PREVIOUS.format(date=previous.day.isoformat(), markdown=prev))
    return "\n".join(parts)

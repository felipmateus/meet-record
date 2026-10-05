from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.planner_claude import ClaudePlanner, PlanOut, build_user_message
from teams_recorder.domain import Action, Analysis, DailyPlan, Decision


class FakeTransport:
    name = "fake"

    def __init__(self, out: PlanOut):
        self.out = out
        self.calls: list[tuple[str, str, type, str]] = []

    def complete(self, system, user, schema, *, tag, extra=None):
        self.calls.append((system, user, schema, tag))
        return self.out


def _analysis(mid: str, *actions: Action) -> Analysis:
    return Analysis(meeting_id=mid, summary=f"resumo {mid}", decisions=[Decision("d")], my_actions=list(actions))


def test_plan_combines_deterministic_and_model_parts(tmp_path: Path):
    day = date(2026, 10, 6)
    open_old = Action("antiga", "usuário", "m0", id="old1", due=day - timedelta(days=2))
    open_fresh = Action("em dia", "usuário", "m0", id="ok1", due=day + timedelta(days=3))
    new = Action("Enviar relatório", "usuário", "m1", id="new1", due=day + timedelta(days=1))
    dup = Action("já aberta", "usuário", "m1", id="ok1")  # same id as an open one: not new
    out = PlanOut(markdown="# Plano\n\n## Prioridades\n- x", priorities=[" Enviar relatório ", ""], completed_action_ids=["ok1", "inventado"])
    transport = FakeTransport(out)
    planner = ClaudePlanner(transport, system_prompt="SYS")

    plan = planner.plan(day, [_analysis("m1", new, dup)], DailyPlan(day - timedelta(days=1), "# ontem"), [open_old, open_fresh])

    assert plan.day == day and plan.markdown.endswith("\n")
    assert plan.priorities == ["Enviar relatório"]
    assert [a.id for a in plan.new_actions] == ["new1"]
    assert plan.overdue_action_ids == ["old1"]
    assert plan.completed_action_ids == ["ok1"]  # invented id discarded
    system, user, schema, tag = transport.calls[0]
    assert system == "SYS" and schema is PlanOut and tag == "plan:2026-10-06"
    assert "Tuesday" in user and "# ontem" in user and '"new1"' in user and '"old1"' in user


def test_empty_day_without_open_actions_skips_model():
    transport = FakeTransport(PlanOut(markdown="x"))
    plan = ClaudePlanner(transport, system_prompt="SYS").plan(date(2026, 10, 6), [], None, [])
    assert "No analyzed meetings" in plan.markdown and not transport.calls


def test_open_actions_only_still_calls_model():
    transport = FakeTransport(PlanOut(markdown="# só pendências"))
    plan = ClaudePlanner(transport, system_prompt="SYS").plan(date(2026, 10, 6), [], None, [Action("a", "usuário", "m0", id="a1")])
    assert transport.calls and plan.new_actions == []


def test_prompt_loaded_from_file(tmp_path: Path):
    prompt = tmp_path / "plan_system.md"; prompt.write_text("PROMPT\n")
    transport = FakeTransport(PlanOut(markdown="x"))
    ClaudePlanner(transport, prompt_path=prompt).plan(date(2026, 10, 6), [], None, [Action("a", "usuário", "m0")])
    assert transport.calls[0][0] == "PROMPT"


def test_user_name_in_plan_message():
    msg = build_user_message(date(2026, 10, 6), [], None, [], [], [], user_name="Felipe")
    assert msg.startswith("User (recording owner): Felipe\n")
    assert not build_user_message(date(2026, 10, 6), [], None, [], [], []).startswith("User")


def test_previous_plan_is_truncated():
    prev = DailyPlan(date(2026, 10, 5), "x" * 10000)
    msg = build_user_message(date(2026, 10, 6), [], prev, [], [], [])
    assert "(truncated)" in msg and len(msg) < 8000

"""Story flow end to end on the real model and a real Backlog.md board.

Opt-in: TREC_REAL_CLAUDE_CLI=1 and TREC_REAL_BACKLOG=1 (uses the Claude Code subscription and the
`backlog` CLI). Day 1 drafts and publishes a story; day 2 raises the same topic again, which must be
left out as a duplicate of the day-1 story, so the board still holds one task for it.
"""
import os
import shutil
from datetime import date
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.clock import SystemClock
from teams_recorder.adapters.outbound.llm_transport import ClaudeCodeTransport
from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher, GitIgnore
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.stories_claude import ClaudeStoryWriter
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.application.use_cases import DraftUserStories, PublishUserStories
from teams_recorder.config import load_settings
from teams_recorder.constants import Files, Stories
from teams_recorder.domain import Action, DailyPlan
from tests.fakes import FakeNotifier
from tests.integration.conftest import board_tasks

PROJECT = Path(__file__).resolve().parents[2]
ready = (
    os.environ.get("TREC_REAL_CLAUDE_CLI") == "1" and os.environ.get("TREC_REAL_BACKLOG") == "1"
    and shutil.which("claude") and shutil.which("backlog")
)

pytestmark = [pytest.mark.slow, pytest.mark.skipif(
    not ready, reason="set TREC_REAL_CLAUDE_CLI=1 and TREC_REAL_BACKLOG=1 (requires a logged-in Claude Code and the backlog CLI)",
)]

DAY_1, DAY_2 = date(2026, 10, 6), date(2026, 10, 8)


def test_real_topic_raised_again_does_not_become_a_second_story(tmp_path: Path, throwaway_board: Path):
    settings = load_settings(PROJECT)
    repo = FsMeetingRepository(tmp_path / "data")
    transport = ClaudeCodeTransport(model=settings.llm_cli_model, effort=settings.llm_effort)
    writer = ClaudeStoryWriter(transport, settings.story_guide_path, prompt_path=settings.prompts_dir / Files.STORIES_PROMPT,
                               user_name=settings.user_name)
    renderer = MarkdownStoryRenderer()
    draft = DraftUserStories(repo, writer, renderer, FakeNotifier())
    publisher = BacklogMdPublisher(throwaway_board, ignore_state=lambda p: GitIgnore.OUTSIDE_GIT)
    publish = PublishUserStories(repo, [publisher], renderer, FakeNotifier(), SystemClock())

    export = Action("Criar a exportação em CSV do relatório de horas por projeto, para o fechamento mensal do financeiro",
                    "usuário", "m1", id="a1")
    repo.save_plan(DailyPlan(DAY_1, "# plano\n", new_actions=[export]))
    day_1 = draft.execute(DAY_1)
    report = publish.execute(DAY_1)

    assert len(day_1.stories) == 1 and len(report.published) == 1 and not report.failures
    assert [t["status"] for t in board_tasks(throwaway_board)] == [Stories.BACKLOG_STATUS]

    again = Action("Entregar a exportação CSV das horas por projeto que o financeiro pediu para fechar o mês", "usuário", "m2", id="a2")
    email = Action("Mandar e-mail para o cliente confirmando a reunião de sexta-feira", "usuário", "m2", id="a3")
    repo.save_plan(DailyPlan(DAY_2, "# plano\n", new_actions=[again, email]))
    day_2 = draft.execute(DAY_2)
    publish.execute(DAY_2)

    assert not any("a2" in story.source_action_ids for story in day_2.stories)      # no second story for the topic
    assert {k.action_id: k.duplicate_of for k in day_2.skipped}["a2"] == day_1.stories[0].id
    assert len(board_tasks(throwaway_board)) == 1 + len(day_2.stories)               # the board holds one task for it

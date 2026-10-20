"""Story flow end to end on the real model and a real Backlog.md board, from tagged lines.

Opt-in: TREC_REAL_CLAUDE_CLI=1 and TREC_REAL_BACKLOG=1 (uses the Claude Code subscription and the
`backlog` CLI). Day 1 drafts and publishes a story for a tagged line; day 2 tags the same topic again, which must be
left out as a duplicate of the day-1 story, so the board still holds one task for it.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.activities_fs import FsActivityStore
from teams_recorder.adapters.outbound.llm_transport import ClaudeCodeTransport
from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher, GitIgnore
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.stories_claude import ClaudeStoryWriter
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.application.use_cases import DraftStoriesFromTags, PublishUserStories
from teams_recorder.application.use_cases.activities import doc_format, skeleton
from teams_recorder.config import load_settings
from teams_recorder.constants import Files, Stories
from teams_recorder.messages import ActivityDoc
from tests.fakes import FakeClock, FakeNotifier
from tests.integration.conftest import board_tasks

PROJECT = Path(__file__).resolve().parents[2]
ready = (
    os.environ.get("TREC_REAL_CLAUDE_CLI") == "1" and os.environ.get("TREC_REAL_BACKLOG") == "1"
    and shutil.which("claude") and shutil.which("backlog")
)

pytestmark = [pytest.mark.slow, pytest.mark.skipif(
    not ready, reason="set TREC_REAL_CLAUDE_CLI=1 and TREC_REAL_BACKLOG=1 (requires a logged-in Claude Code and the backlog CLI)",
)]

DAY_1, DAY_2 = datetime(2026, 10, 6, 10, 0), datetime(2026, 10, 8, 10, 0)


def test_real_topic_tagged_again_does_not_become_a_second_story(tmp_path: Path, throwaway_board: Path):
    settings = load_settings(PROJECT)
    repo = FsMeetingRepository(tmp_path / "data")
    store = FsActivityStore(tmp_path / "data", doc_format())
    transport = ClaudeCodeTransport(model=settings.llm_cli_model, effort=settings.llm_effort)
    writer = ClaudeStoryWriter(transport, settings.story_guide_path, prompt_path=settings.prompts_dir / Files.STORIES_PROMPT,
                               user_name=settings.user_name)
    renderer = MarkdownStoryRenderer()
    clock = FakeClock(DAY_1)
    draft = DraftStoriesFromTags(repo, store, writer, renderer, clock)
    publisher = BacklogMdPublisher(throwaway_board, ignore_state=lambda p: GitIgnore.OUTSIDE_GIT)
    publish = PublishUserStories(repo, [publisher], renderer, FakeNotifier(), clock)

    def tag(text: str) -> None:
        store.path().parent.mkdir(parents=True, exist_ok=True)
        store.path().write_text(skeleton(doc_format()).replace(doc_format().heading_actions + "\n", f"{doc_format().heading_actions}\n\n- [ ] {text} {ActivityDoc.STORY_TAG}\n", 1))

    tag("Criar a exportação em CSV do relatório de horas por projeto, para o fechamento mensal do financeiro")
    day_1 = draft.execute()
    report = publish.execute(DAY_1.date())

    assert len(day_1.stories) == 1 and len(report.published) == 1 and not report.failures
    assert [t["status"] for t in board_tasks(throwaway_board)] == [Stories.BACKLOG_STATUS]

    clock.current = DAY_2
    tag("Entregar a exportação CSV das horas por projeto que o financeiro pediu para fechar o mês")
    day_2 = draft.execute()
    publish.execute(DAY_2.date())

    assert not day_2.stories and [k.duplicate_of for k in day_2.skipped] == [day_1.stories[0].id]      # no second story for the topic
    assert len(board_tasks(throwaway_board)) == 1                                                       # the board holds one task for it

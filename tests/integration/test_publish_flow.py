"""Publishing with the real file repository and renderer: an interrupted run keeps what was published."""
from datetime import date, datetime
from pathlib import Path

from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.application.use_cases import PublishUserStories
from teams_recorder.domain import Action, DailyPlan, StoryDrafts, UserStory
from teams_recorder.messages import StoryDoc
from tests.fakes import FakeClock, FakeNotifier, FakeStoryPublisher

DAY = date(2026, 10, 9)


def test_failure_on_the_second_story_keeps_the_first_on_disk_and_a_rerun_sends_only_the_rest(tmp_path: Path):
    fs = FsMeetingRepository(tmp_path / "data")
    actions = [Action("Exportar horas", "usuário", "m1", id="a1"), Action("Validar filtros", "usuário", "m1", id="a2")]
    fs.save_plan(DailyPlan(DAY, "# plano\n", new_actions=actions))
    fs.save_story_drafts(StoryDrafts(DAY, [UserStory("Um", "n", source_action_ids=["a1"]), UserStory("Dois", "n", source_action_ids=["a2"])]), "#\n")
    clock = FakeClock(datetime(2026, 10, 9, 18, 5))

    first = PublishUserStories(fs, [FakeStoryPublisher("board", fail_on={"Dois"})], MarkdownStoryRenderer(), FakeNotifier(), clock).execute(DAY)

    reloaded = fs.load_story_drafts(DAY)
    assert [len(s.publications) for s in reloaded.stories] == [1, 0] and len(first.failures) == 1
    markdown = (fs.plans / "2026-10-09.stories.md").read_text()
    assert StoryDoc.PUBLISHED.format(destination="board", ref="board-1") in markdown

    board = FakeStoryPublisher("board")
    second = PublishUserStories(fs, [board], MarkdownStoryRenderer(), FakeNotifier(), clock).execute(DAY)

    assert [o.story.title for o in second.published] == ["Dois"] and second.already_published == 1
    assert [s.title for s, _ in board.calls] == ["Dois"]
    assert all(s.publications for s in fs.load_story_drafts(DAY).stories)

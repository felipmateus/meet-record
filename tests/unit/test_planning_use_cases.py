from datetime import date, datetime, timedelta

import re

import pytest

from teams_recorder.application.use_cases import BuildDailyPlan, DraftUserStories, PurgeOldAudio
from teams_recorder.domain import (
    Action,
    ActionStatus,
    AnalysisError,
    DailyPlan,
    Meeting,
    Publication,
    RepositoryError,
    StoryDrafts,
    UserStory,
)
from teams_recorder.domain.status import ANALYSIS, AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Err
from tests.fakes import FakeAnalyzer, FakePlanner, FakeStoryRenderer, FakeStoryWriter, FakeTranscriber


def _analyzed(repo, clock, title):
    m = Meeting.start(clock.now(), title=title)
    analysis = FakeAnalyzer().analyze(FakeTranscriber().transcript, m)
    analysis.meeting_id = m.id
    repo.seed(m, {AUDIO, TRANSCRIPT_JSON, ANALYSIS}, analysis=analysis)
    return m, analysis


def test_build_daily_plan_uses_only_analyzed_meetings_of_the_day(repo, notifier, clock):
    day = clock.now().date()
    _analyzed(repo, clock, "A")
    clock.advance(hours=1)
    _analyzed(repo, clock, "B")
    clock.advance(hours=1)
    repo.seed(Meeting.start(clock.now(), title="recorded only"), {AUDIO})
    clock.advance(days=1)
    _analyzed(repo, clock, "tomorrow")
    late = Action("old", "me", "m0", id="late", due=day - timedelta(days=3))
    repo.save_open_actions([late])

    plan = BuildDailyPlan(repo, FakePlanner(), notifier).execute(day)

    assert plan.day == day
    assert len(plan.new_actions) == 2
    assert repo.load_plan(day) is plan
    open_ids = [a.id for a in repo.load_open_actions()]
    assert open_ids[0] == "late" and len(open_ids) == 3
    assert repo.load_open_actions()[0].status == ActionStatus.OVERDUE
    assert notifier.messages[-1] == ("Daily plan ready", "2 meeting(s), 2 new action(s)")


def test_build_daily_plan_passes_previous_plan(repo, notifier, clock):
    day = clock.now().date()
    captured = {}

    class SpyPlanner(FakePlanner):
        def plan(self, day, analyses, previous_plan, open_actions):
            captured["previous"] = previous_plan
            return super().plan(day, analyses, previous_plan, open_actions)

    uc = BuildDailyPlan(repo, SpyPlanner(), notifier)
    first = uc.execute(day - timedelta(days=1))
    uc.execute(day)

    assert captured["previous"] is first


def test_purge_old_audio_respects_retention_and_transcript(repo, clock):
    now = clock.now()
    old_done = Meeting.start(now - timedelta(days=31)); repo.seed(old_done, {AUDIO, TRANSCRIPT_JSON})
    old_untranscribed = Meeting.start(now - timedelta(days=40)); repo.seed(old_untranscribed, {AUDIO})
    recent = Meeting.start(now - timedelta(days=5)); repo.seed(recent, {AUDIO, TRANSCRIPT_JSON})
    purged_already = Meeting.start(now - timedelta(days=60)); repo.seed(purged_already, {TRANSCRIPT_JSON})

    purged = PurgeOldAudio(repo, clock, retention_days=30).execute()

    assert purged == [old_done.id]
    assert AUDIO not in repo.files(old_done.id)
    assert AUDIO in repo.files(old_untranscribed.id)
    assert AUDIO in repo.files(recent.id)


def test_draft_user_stories_from_the_plan(repo, notifier, clock):
    day = clock.now().date()
    m, analysis = _analyzed(repo, clock, "A")
    feature = Action("Export hours", "me", m.id, id="f1")
    email = Action("Email the client", "me", m.id, id="e1")
    orphan = Action("From a deleted meeting", "me", "gone", id="o1")
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[feature, email, orphan]))
    writer = FakeStoryWriter()

    drafts = DraftUserStories(repo, writer, FakeStoryRenderer(), notifier).execute(day)

    assert [s.source_action_ids for s in drafts.stories] == [["f1"], ["o1"]]
    assert [k.action_id for k in drafts.skipped] == ["e1"]
    _, actions, analyses, existing = writer.calls[0]
    assert actions == [feature, email, orphan] and existing == []
    assert analyses == [analysis]                             # context of existing meetings only
    saved, markdown = repo.story_drafts[day]
    assert saved is drafts and markdown.startswith(f"# Stories {day}")
    assert notifier.messages[-1] == ("User story drafts ready", "2 draft(s) to review, 1 action(s) left out")


def test_draft_user_stories_without_new_actions_skips_the_writer(repo, notifier, clock):
    day = clock.now().date()
    repo.save_plan(DailyPlan(day, "# plan"))
    writer = FakeStoryWriter()

    drafts = DraftUserStories(repo, writer, FakeStoryRenderer(), notifier).execute(day)

    assert drafts.stories == [] and not writer.calls
    assert day in repo.story_drafts and not notifier.messages


def test_draft_user_stories_needs_a_plan(repo, notifier, clock):
    with pytest.raises(RepositoryError, match="no plan for 2026-10-06"):
        DraftUserStories(repo, FakeStoryWriter(), FakeStoryRenderer(), notifier).execute(clock.now().date())


def test_draft_user_stories_failure_saves_nothing(repo, notifier, clock):
    day = clock.now().date()
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[Action("Export hours", "me", "m0")]))
    with pytest.raises(AnalysisError):
        DraftUserStories(repo, FakeStoryWriter(fail=True), FakeStoryRenderer(), notifier).execute(day)
    assert not repo.story_drafts


def test_draft_user_stories_shows_recent_stories_to_the_writer(repo, notifier, clock):
    day = clock.now().date()
    old = UserStory("Too old", "n", id="old")
    recent = UserStory("Export hours", "n", id="s1")
    repo.save_story_drafts(StoryDrafts(day - timedelta(days=31), [old]), "#")
    repo.save_story_drafts(StoryDrafts(day - timedelta(days=2), [recent]), "#")
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[Action("Export hours again", "me", "m0", id="f1")]))
    writer, renderer = FakeStoryWriter(), FakeStoryRenderer()

    DraftUserStories(repo, writer, renderer, notifier, dedup_days=30).execute(day)

    assert writer.calls[0][3] == [recent]
    assert renderer.calls[0][2] == [recent]          # the document can name the covering story


def test_published_day_is_never_drafted_again(repo, notifier, clock):
    day = clock.now().date()
    published = UserStory("Export hours", "n", publications=[Publication("backlog-md", "TASK-1", clock.now())])
    repo.save_story_drafts(StoryDrafts(day, [published]), "# published")
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[Action("Export hours", "me", "m0")]))
    writer = FakeStoryWriter()

    with pytest.raises(RepositoryError, match=re.escape(Err.STORIES_ALREADY_PUBLISHED.format(day=day.isoformat()))):
        DraftUserStories(repo, writer, FakeStoryRenderer(), notifier).execute(day)

    assert not writer.calls and repo.story_drafts[day][1] == "# published"


def test_unpublished_drafts_can_be_drafted_again(repo, notifier, clock):
    day = clock.now().date()
    repo.save_story_drafts(StoryDrafts(day, [UserStory("Old draft", "n")]), "# old")
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[Action("Export hours", "me", "m0", id="f1")]))

    writer = FakeStoryWriter()

    drafts = DraftUserStories(repo, writer, FakeStoryRenderer(), notifier).execute(day)

    assert [s.title for s in drafts.stories] == ["Story for Export hours"]
    assert writer.calls[0][3] == []      # the day's own earlier drafts are not "existing" stories

from datetime import date, datetime, timedelta

import re

import pytest

from teams_recorder.application.use_cases import BuildDailyPlan, DraftUserStories, PublishUserStories, PurgeOldAudio
from teams_recorder.domain import (
    Action,
    ActionKind,
    ActionStatus,
    AnalysisError,
    DailyPlan,
    Meeting,
    Publication,
    PublishError,
    RepositoryError,
    StoryDrafts,
    UserStory,
)
from teams_recorder.domain.status import ANALYSIS, AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Err, Notify, StoryDoc
from tests.fakes import FakeAnalyzer, FakePlanner, FakeStoryPublisher, FakeStoryRenderer, FakeStoryWriter, FakeTranscriber


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
    assert notifier.messages[-1] == (Notify.STORIES_READY, Notify.STORIES_READY_BODY.format(stories=2, tasks=0, skipped=1))


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


def _publish_setup(repo, clock, titles=("One", "Two", "Three")):
    day = clock.now().date()
    stories = [UserStory(t, "n", id=f"s{i}") for i, t in enumerate(titles, 1)]
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[Action("Export hours", "me", "m0", id="f1")]))
    repo.save_story_drafts(StoryDrafts(day, stories), "# drafts")
    return day, stories


def test_publish_sends_every_story_to_every_destination_once(repo, notifier, clock):
    day, stories = _publish_setup(repo, clock)
    board, other = FakeStoryPublisher("board"), FakeStoryPublisher("other")
    uc = PublishUserStories(repo, [board, other], FakeStoryRenderer(), notifier, clock)

    report = uc.execute(day)

    assert len(report.published) == 6 and report.already_published == 0 and not report.failures
    saved = repo.load_story_drafts(day)
    assert [p.destination for p in saved.stories[0].publications] == ["board", "other"]
    assert saved.stories[0].publication("board").published_at == clock.now()
    assert notifier.messages[-1] == (Notify.STORIES_PUBLISHED, Notify.STORIES_PUBLISHED_BODY.format(count=6))

    again = uc.execute(day)

    assert again.published == [] and again.already_published == 6 and len(board.calls) == 3   # nothing sent twice
    assert len(notifier.messages) == 1                                                # nothing new: no notification


def test_publish_failure_does_not_stop_other_destinations(repo, notifier, clock):
    day, _ = _publish_setup(repo, clock)
    board, broken = FakeStoryPublisher("board"), FakeStoryPublisher("broken", fail_all=True)

    report = PublishUserStories(repo, [broken, board], FakeStoryRenderer(), notifier, clock).execute(day)

    assert len(report.published) == 3 and len(report.failures) == 3
    assert report.failures[0].destination == "broken" and "refused One" in report.failures[0].error
    assert report.published[0].publication.ref == "board-1"
    assert notifier.messages[-1] == (Notify.PUBLISH_FAILED, Notify.PUBLISH_FAILED_BODY.format(failed=3, published=3))


def test_publish_saves_each_success_before_the_next_story(repo, notifier, clock):
    day, _ = _publish_setup(repo, clock)
    renderer = FakeStoryRenderer()

    report = PublishUserStories(repo, [FakeStoryPublisher("board", fail_on={"Two"})], renderer, notifier, clock).execute(day)

    saved = repo.load_story_drafts(day)
    assert [bool(s.publications) for s in saved.stories] == [True, False, True]
    assert len(renderer.calls) == 2                                   # one save per success
    _, actions, _ = renderer.calls[0]
    assert [a.id for a in actions] == ["f1"]                          # re-rendered with the plan's actions
    assert [o.story.title for o in report.failures] == ["Two"]


def test_publish_only_selected_numbers_and_validates_them_first(repo, notifier, clock):
    day, _ = _publish_setup(repo, clock)
    board = FakeStoryPublisher("board")
    uc = PublishUserStories(repo, [board], FakeStoryRenderer(), notifier, clock)

    with pytest.raises(PublishError, match=re.escape(Err.INVALID_STORY_NUMBER.format(number=9, day=day.isoformat(), count=3))):
        uc.execute(day, only=[2, 9])
    assert not board.calls                                             # nothing published before the error

    report = uc.execute(day, only=[2, 2])

    assert [o.story.title for o in report.published] == ["Two"]
    assert uc.execute(day, only=[]).published == []                     # an empty selection publishes nothing


def test_publish_needs_drafts(repo, notifier, clock):
    day = clock.now().date()
    with pytest.raises(RepositoryError, match=re.escape(Err.STORIES_MISSING.format(day=day.isoformat()))):
        PublishUserStories(repo, [FakeStoryPublisher()], FakeStoryRenderer(), notifier, clock).execute(day)


def test_publish_rerenders_with_recent_stories(repo, notifier, clock):
    day, _ = _publish_setup(repo, clock, titles=("One",))
    earlier = UserStory("Earlier", "n", id="e1")
    repo.save_story_drafts(StoryDrafts(day - timedelta(days=3), [earlier]), "#")
    renderer = FakeStoryRenderer()

    PublishUserStories(repo, [FakeStoryPublisher()], renderer, notifier, clock, dedup_days=30).execute(day)

    assert renderer.calls[0][2] == [earlier]


def test_publish_needs_the_plan_to_rerender_the_document(repo, notifier, clock):
    day = clock.now().date()
    repo.save_story_drafts(StoryDrafts(day, [UserStory("One", "n")]), "# drafts")
    board = FakeStoryPublisher()
    with pytest.raises(RepositoryError, match=re.escape(Err.PLAN_MISSING.format(day=day.isoformat()))):
        PublishUserStories(repo, [board], FakeStoryRenderer(), notifier, clock).execute(day)
    assert not board.calls and repo.story_drafts[day][1] == "# drafts"


def test_drafting_routes_actions_by_kind(repo, notifier, clock):
    day = clock.now().date()
    kinds = {"f1": ActionKind.FEATURE, "b1": ActionKind.BUG, "t1": ActionKind.TECHNICAL, "o1": ActionKind.OPERATION,
             "g1": ActionKind.MANAGEMENT, "c1": ActionKind.COMMUNICATION, "u1": None}
    actions = [Action(f"Action {i}", "me", "m0", id=i, kind=k) for i, k in kinds.items()]
    repo.save_plan(DailyPlan(day, "# plan", new_actions=actions))
    writer = FakeStoryWriter()

    drafts = DraftUserStories(repo, writer, FakeStoryRenderer(), notifier).execute(day)

    assert [a.id for a in writer.calls[0][1]] == ["f1", "b1", "u1"]                  # product work and unclassified
    cards = [s for s in drafts.stories if s.is_task_card]
    assert [(c.source_action_ids, c.kind, c.narrative) for c in cards] == [(["t1"], ActionKind.TECHNICAL, ""), (["o1"], ActionKind.OPERATION, "")]
    plan_only = {k.action_id: k.reason for k in drafts.skipped}
    assert plan_only == {"g1": StoryDoc.PLAN_ONLY.format(kind=StoryDoc.KIND_LABELS["management"]),
                         "c1": StoryDoc.PLAN_ONLY.format(kind=StoryDoc.KIND_LABELS["communication"])}


def test_a_day_without_product_work_does_not_call_the_writer(repo, notifier, clock):
    day = clock.now().date()
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[Action("Deploy", "me", "m0", kind=ActionKind.OPERATION),
                                                          Action("E-mail", "me", "m0", kind=ActionKind.COMMUNICATION)]))
    writer = FakeStoryWriter()
    drafts = DraftUserStories(repo, writer, FakeStoryRenderer(), notifier).execute(day)
    assert not writer.calls and [s.title for s in drafts.stories] == ["Deploy"] and len(drafts.skipped) == 1



def test_the_writer_sees_only_stories_and_task_cards_are_not_repeated(repo, notifier, clock):
    day = clock.now().date()
    earlier_story = UserStory("Implementar exportação", "n", id="s0", kind=ActionKind.FEATURE)
    earlier_card = UserStory("Estimar horas da nova tela", "", id="t0", kind=ActionKind.TECHNICAL)
    repo.save_story_drafts(StoryDrafts(day - timedelta(days=1), [earlier_story, earlier_card]), "#")
    actions = [Action("Implementar exportação de novo", "me", "m0", id="f1", kind=ActionKind.FEATURE),
               Action("  estimar horas  da NOVA TELA", "me", "m0", id="t1", kind=ActionKind.TECHNICAL),
               Action("Publicar em PROD", "me", "m0", id="o1", kind=ActionKind.OPERATION),
               Action("Publicar em prod", "me", "m1", id="o2", kind=ActionKind.OPERATION)]
    repo.save_plan(DailyPlan(day, "# plan", new_actions=actions))
    writer = FakeStoryWriter()

    drafts = DraftUserStories(repo, writer, FakeStoryRenderer(), notifier).execute(day)

    assert writer.calls[0][3] == [earlier_story]                                  # task cards never count as stories
    assert [s.title for s in drafts.stories if s.is_task_card] == ["Publicar em PROD"]
    duplicates = {k.action_id: k.duplicate_of for k in drafts.skipped}
    assert duplicates["t1"] == "t0" and duplicates["o2"] == drafts.stories[-1].id
    assert notifier.messages[-1] == (Notify.STORIES_READY, Notify.STORIES_READY_BODY.format(stories=1, tasks=1, skipped=2))

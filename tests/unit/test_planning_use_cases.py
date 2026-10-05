from datetime import date, datetime, timedelta

from teams_recorder.application.use_cases import BuildDailyPlan, PurgeOldAudio
from teams_recorder.domain import Action, ActionStatus, Meeting
from teams_recorder.domain.status import ANALYSIS, AUDIO, TRANSCRIPT_JSON
from tests.fakes import FakeAnalyzer, FakePlanner, FakeTranscriber


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

"""Planning and maintenance use cases."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from teams_recorder.application.ports import Clock, MeetingRepository, Notifier, Planner, StoryRenderer, StoryWriter
from teams_recorder.constants import Planner as PlannerDefaults
from teams_recorder.constants import Stories as StoryDefaults
from teams_recorder.domain import (
    Action,
    Analysis,
    DailyPlan,
    MeetingStatus,
    RepositoryError,
    StoryDrafts,
    UserStory,
    derive_status,
    merge_open_actions,
)
from teams_recorder.domain.status import ANALYSIS, AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Err, Notify


@dataclass
class BuildDailyPlan:
    repo: MeetingRepository
    planner: Planner
    notifier: Notifier

    def execute(self, day: date) -> DailyPlan:
        analyses = [
            self.repo.load_analysis(m.id)
            for m in self.repo.list_meetings()
            if m.day == day and derive_status(self.repo.files(m.id)) == MeetingStatus.ANALYZED
        ]
        previous = self.repo.latest_plan_before(day)
        open_actions = self.repo.load_open_actions()
        plan = self.planner.plan(day, analyses, previous, open_actions)
        plan.day = day
        self.repo.save_plan(plan)
        self.repo.save_open_actions(merge_open_actions(open_actions, plan))
        self.notifier.notify(
            Notify.PLAN_READY,
            Notify.PLAN_READY_BODY.format(meetings=len(analyses), new_actions=len(plan.new_actions)),
        )
        return plan


@dataclass
class DraftUserStories:
    """Drafts user stories from a saved daily plan's new actions.

    The drafts are files for the user to review (`plans/<day>.stories.*`). A day without new
    actions gets an empty set without calling the writer. The stories of the previous
    `dedup_days` days go to the writer so a topic raised again does not become a second story,
    and a day whose stories were already published is never drafted again (that would put
    the same work on the board twice).
    """

    repo: MeetingRepository
    writer: StoryWriter
    renderer: StoryRenderer
    notifier: Notifier
    dedup_days: int = StoryDefaults.DEDUP_DAYS

    def execute(self, day: date) -> StoryDrafts:
        plan = self.repo.load_plan(day)
        if plan is None:
            raise RepositoryError(Err.PLAN_MISSING.format(day=day.isoformat()))
        already_drafted = self.repo.load_story_drafts(day)
        if already_drafted is not None and already_drafted.has_publications:
            raise RepositoryError(Err.STORIES_ALREADY_PUBLISHED.format(day=day.isoformat()))
        actions = plan.new_actions
        existing = recent_stories(self.repo, day, self.dedup_days)
        drafts = self.writer.draft(day, actions, self._source_analyses(actions), existing) if actions else StoryDrafts(day=day)
        drafts.day = day
        self.repo.save_story_drafts(drafts, self.renderer.render(drafts, actions, existing))
        if drafts.stories:
            self.notifier.notify(
                Notify.STORIES_READY,
                Notify.STORIES_READY_BODY.format(stories=len(drafts.stories), skipped=len(drafts.skipped)),
            )
        return drafts

    def _source_analyses(self, actions: list[Action]) -> list[Analysis]:
        meeting_ids = dict.fromkeys(a.source_meeting for a in actions)  # unique, in order
        return [
            self.repo.load_analysis(mid)
            for mid in meeting_ids
            if self.repo.exists(mid) and ANALYSIS in self.repo.files(mid)
        ]


def recent_stories(repo: MeetingRepository, day: date, days: int) -> list[UserStory]:
    """The stories drafted in the `days` days before `day`, oldest first."""
    return [story for drafts in repo.recent_story_drafts(day, days) for story in drafts.stories]


@dataclass
class PurgeOldAudio:
    repo: MeetingRepository
    clock: Clock
    retention_days: int = PlannerDefaults.RETENTION_DAYS

    def execute(self) -> list[str]:
        cutoff = self.clock.now() - timedelta(days=self.retention_days)
        purged: list[str] = []
        for meeting in self.repo.list_meetings():
            files = self.repo.files(meeting.id)
            if AUDIO in files and TRANSCRIPT_JSON in files and meeting.started_at < cutoff:
                self.repo.delete_file(meeting.id, AUDIO)
                purged.append(meeting.id)
        return purged

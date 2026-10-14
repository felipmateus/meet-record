"""Planning and maintenance use cases."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from teams_recorder.application.ports import (
    Clock,
    MeetingRepository,
    Notifier,
    Planner,
    StoryPublisher,
    StoryRenderer,
    StoryWriter,
)
from teams_recorder.constants import Planner as PlannerDefaults
from teams_recorder.constants import Stories as StoryDefaults
from teams_recorder.domain import (
    Action,
    ActionRoute,
    Analysis,
    DailyPlan,
    MeetingStatus,
    Publication,
    PublishError,
    RepositoryError,
    SkippedAction,
    StoryDrafts,
    TeamsRecorderError,
    TranscriptHealth,
    UserStory,
    checked_criteria,
    derive_status,
    merge_open_actions,
    said_at,
    task_card,
    unconfirmed,
    unconfirmed_reason,
)
from teams_recorder.domain.status import ANALYSIS, AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Err, Notify, StoryDoc


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

    The drafts are files for the user to review (`plans/<day>.stories.*`). Actions are routed by
    the kind the analysis gave them (`ActionRoute`): features, bugs and unclassified actions go to
    the writer; technical and operation actions become task cards as they are; management and
    communication actions stay in the plan. An action the claim verifier did not confirm never becomes a
    story's source (FR5): it is listed as left out with the verifier's reason, while a technical or
    operation one still becomes a task card that carries the mark (PRD decision 10). The writer sees the stories (not the task cards) of
    the previous `dedup_days` days, so a topic raised again does not become a second story; a
    task card whose text and kind match a recent card is left out as its duplicate. A day whose
    stories were already published is never drafted again (that would put the same work on the
    board twice).
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
        by_route = {route: [a for a in actions if a.route is route] for route in ActionRoute}
        existing = recent_stories(self.repo, day, self.dedup_days)
        unconfirmed_story_actions = [a for a in by_route[ActionRoute.STORY] if unconfirmed(a.verification)]
        candidates = [a for a in by_route[ActionRoute.STORY] if not unconfirmed(a.verification)]
        stories_only = [s for s in existing if not s.is_task_card]
        drafts = self.writer.draft(day, candidates, self._source_analyses(candidates), stories_only) if candidates else StoryDrafts(day=day)
        drafts.day = day
        self._check_provenance(drafts)
        self._add_task_cards(drafts, by_route[ActionRoute.TASK], [s for s in existing if s.is_task_card])
        drafts.skipped += [
            SkippedAction(a.id, StoryDoc.NOT_CONFIRMED.format(reason=reason) if (reason := unconfirmed_reason(a.verification))
                          else StoryDoc.NOT_CONFIRMED_NO_REASON)
            for a in unconfirmed_story_actions
        ]
        drafts.skipped += [
            SkippedAction(a.id, StoryDoc.PLAN_ONLY.format(kind=StoryDoc.KIND_LABELS[a.kind.value]) + _unconfirmed_suffix(a))
            for a in by_route[ActionRoute.PLAN] if a.kind is not None
        ]
        self.repo.save_story_drafts(drafts, self.renderer.render(drafts, actions, existing, degraded_sources(self.repo, actions)))
        if drafts.stories:
            tasks = sum(1 for s in drafts.stories if s.is_task_card)
            self.notifier.notify(
                Notify.STORIES_READY,
                Notify.STORIES_READY_BODY.format(stories=len(drafts.stories) - tasks, tasks=tasks, skipped=len(drafts.skipped)),
            )
        return drafts

    @staticmethod
    def _add_task_cards(drafts: StoryDrafts, actions: list[Action], recent_cards: list[UserStory]) -> None:
        """Task cards as the actions are; one repeating a recent card (same kind and text) is left out as its duplicate."""
        seen = {(c.kind, " ".join(c.title.lower().split())): c for c in [*recent_cards, *drafts.stories]}
        for action in actions:
            card = task_card(action)
            twin = seen.get((card.kind, " ".join(card.title.lower().split())))
            if twin is not None:
                drafts.skipped.append(SkippedAction(action.id, StoryDoc.SAME_TASK, duplicate_of=twin.id))
                continue
            drafts.stories.append(card)
            seen[(card.kind, " ".join(card.title.lower().split()))] = card

    def _check_provenance(self, drafts: StoryDrafts) -> None:
        """A criterion citing a time that is not a line of its story's source meetings becomes a suggestion (FR6).
        A meeting whose transcript cannot be read confirms nothing."""
        lines: dict[str, set[str]] = {}
        for story in drafts.stories:
            said: set[str] = set()
            for meeting_id in story.source_meetings:
                if meeting_id not in lines:
                    try:
                        lines[meeting_id] = said_at(self.repo.load_transcript(meeting_id)) if self.repo.exists(meeting_id) else set()
                    except TeamsRecorderError:
                        lines[meeting_id] = set()
                said |= lines[meeting_id]
            story.acceptance_criteria = checked_criteria(story.acceptance_criteria, said)

    def _source_analyses(self, actions: list[Action]) -> list[Analysis]:
        meeting_ids = dict.fromkeys(a.source_meeting for a in actions)  # unique, in order
        return [
            self.repo.load_analysis(mid)
            for mid in meeting_ids
            if self.repo.exists(mid) and ANALYSIS in self.repo.files(mid)
        ]


@dataclass(frozen=True)
class PublishedStory:
    story: UserStory
    publication: Publication


@dataclass(frozen=True)
class PublishFailure:
    story: UserStory
    destination: str
    error: str


@dataclass
class PublishReport:
    published: list[PublishedStory] = field(default_factory=list)
    already_published: int = 0  # (story, destination) pairs skipped because they were published before
    failures: list[PublishFailure] = field(default_factory=list)


@dataclass
class PublishUserStories:
    """Sends a day's story drafts to every configured destination (a board).

    Idempotent per destination: a story already published there is skipped. Each
    publication is saved (JSON and re-rendered document) as soon as it succeeds, so an
    interrupted run resumes without duplicates; a failure on one story or destination is
    reported and the others go on.
    """

    repo: MeetingRepository
    publishers: list[StoryPublisher]
    renderer: StoryRenderer
    notifier: Notifier
    clock: Clock
    dedup_days: int = StoryDefaults.DEDUP_DAYS

    def execute(self, day: date, only: list[int] | None = None) -> PublishReport:
        drafts = self.repo.load_story_drafts(day)
        if drafts is None:
            raise RepositoryError(Err.STORIES_MISSING.format(day=day.isoformat()))
        plan = self.repo.load_plan(day)  # its actions are needed to re-render the document faithfully
        if plan is None:
            raise RepositoryError(Err.PLAN_MISSING.format(day=day.isoformat()))
        selected = self._select(drafts, only)
        existing = recent_stories(self.repo, day, self.dedup_days)
        degraded = degraded_sources(self.repo, plan.new_actions)
        report = PublishReport()
        for story in selected:
            for publisher in self.publishers:
                if story.publication(publisher.destination) is not None:
                    report.already_published += 1
                    continue
                try:
                    ref = publisher.publish(story, day)
                except TeamsRecorderError as exc:
                    report.failures.append(PublishFailure(story, publisher.destination, str(exc)))
                    continue
                publication = Publication(publisher.destination, ref, self.clock.now())
                story.publications.append(publication)
                self.repo.save_story_drafts(drafts, self.renderer.render(drafts, plan.new_actions, existing, degraded))
                report.published.append(PublishedStory(story, publication))
        self._notify(report)
        return report

    @staticmethod
    def _select(drafts: StoryDrafts, only: list[int] | None) -> list[UserStory]:
        """All stories (None), or the 1-based numbers of the drafts document; any bad number fails before publishing."""
        if only is None:
            return drafts.stories
        for number in only:
            if not 1 <= number <= len(drafts.stories):
                raise PublishError(Err.INVALID_STORY_NUMBER.format(number=number, day=drafts.day.isoformat(), count=len(drafts.stories)))
        return [drafts.stories[number - 1] for number in dict.fromkeys(only)]

    def _notify(self, report: PublishReport) -> None:
        if report.failures:
            self.notifier.notify(
                Notify.PUBLISH_FAILED,
                Notify.PUBLISH_FAILED_BODY.format(failed=len(report.failures), published=len(report.published)),
            )
        elif report.published:
            self.notifier.notify(Notify.STORIES_PUBLISHED, Notify.STORIES_PUBLISHED_BODY.format(count=len(report.published)))


def _unconfirmed_suffix(action: Action) -> str:
    """The mark a plan-only action carries in the drafts when the verifier did not confirm it (FR4: kept, visibly marked)."""
    reason = unconfirmed_reason(action.verification)
    if reason is None:
        return ""
    return StoryDoc.UNCONFIRMED_SUFFIX.format(reason=reason) if reason else StoryDoc.UNCONFIRMED_SUFFIX_NO_REASON


def degraded_sources(repo: MeetingRepository, actions: list[Action]) -> dict[str, TranscriptHealth]:
    """The actions' source meetings whose transcript is degraded (a whisper loop survived the retry), by meeting id,
    so the drafts document warns that what came from them may be incomplete (PRD decision 9). A meeting whose
    transcript is gone or unreadable is left out: the warning is advice, never a reason to fail."""
    found: dict[str, TranscriptHealth] = {}
    for meeting_id in dict.fromkeys(a.source_meeting for a in actions):
        try:
            if not repo.exists(meeting_id) or TRANSCRIPT_JSON not in repo.files(meeting_id):
                continue
            health = repo.load_transcript(meeting_id).health
        except TeamsRecorderError:
            continue
        if health is not None and health.degraded:
            found[meeting_id] = health
    return found


def recent_stories(repo: MeetingRepository, day: date, days: int) -> list[UserStory]:
    """The stories drafted in the `days` days before `day`, oldest first."""
    return [story for drafts in repo.recent_story_drafts(day, days) for story in drafts.stories]


def stories_waiting(repo: MeetingRepository, today: date, days: int, destinations: list[str]) -> list[UserStory]:
    """Stories of the last `days` days (today and the `days - 1` before it) still missing from a destination."""
    tomorrow = today + timedelta(days=1)  # the window is [before - days, before): ending tomorrow includes today
    return [
        story for story in recent_stories(repo, tomorrow, days)
        if any(story.publication(destination) is None for destination in destinations)
    ]


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

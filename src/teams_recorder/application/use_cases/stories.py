"""Story use cases: drafting from the items the user tagged in the activities document, and publishing the drafts.

`DraftStoriesFromTags` reads the tagged blocks of `atividades.md`, sends the ones not drafted before to the story writer (with
their meetings' analyses, without the activities lock: the call can take minutes), merges the drafts into today's file and
replaces each tag with a link to its draft, under `lock(wait=False)` so it never waits for a curator pass. The drafts file is
the only memory: a block whose tagged line is already in the recent drafts (as a story or as a skip) is never sent to the
writer again, and a replacement that could not be applied (the curator held the lock, the line was edited) is retried by
the next run from the same files.

`PublishUserStories` reads only `plans/<day>.stories.json`; no plan file is involved, so it publishes the drafts of the
planner era and of the tags alike.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

from teams_recorder.application.ports import (
    ActivityStore,
    Clock,
    MeetingRepository,
    Notifier,
    StoryPublisher,
    StoryRenderer,
    StoryWriter,
)
from teams_recorder.application.use_cases.activities import doc_format
from teams_recorder.constants import Files, Stories
from teams_recorder.domain import (
    Analysis,
    Publication,
    PublishError,
    RepositoryError,
    SkippedAction,
    StoryDrafts,
    TaggedBlock,
    TeamsRecorderError,
    TranscriptHealth,
    UserStory,
    checked_criteria,
    replace_tag,
    said_at,
    tagged_blocks,
)
from teams_recorder.domain.status import ANALYSIS, TRANSCRIPT_JSON
from teams_recorder.messages import ActivityDoc, Err, Notify


@dataclass(frozen=True)
class TagDraftResult:
    drafts_path: Path | None              # today's drafts document when this run saved drafts, else None
    stories: tuple[UserStory, ...]        # the stories drafted by this run
    skipped: tuple[SkippedAction, ...]    # the tagged blocks that are not stories: new skips and stored ones re-reported (`source_line` set)
    replaced: int                         # tags replaced now
    deferred: int                         # tags not replaced because the curator held the lock; the next run replaces them
    edited: int                           # tagged lines edited meanwhile: the tag stays
    nothing_tagged: bool
    titles: dict[str, str] = field(default_factory=dict)   # id -> title of the recent stories: what a duplicate skip points to


@dataclass
class DraftStoriesFromTags:
    repo: MeetingRepository
    store: ActivityStore
    writer: StoryWriter
    renderer: StoryRenderer
    clock: Clock
    dedup_days: int = Stories.DEDUP_DAYS

    def execute(self, on_drafting: Callable[[int], None] | None = None) -> TagDraftResult:
        """`on_drafting(n)` is called with the number of blocks about to go to the writer, only when there are some."""
        document = self.store.read_document()
        if document is None:
            raise RepositoryError(Err.NO_ACTIVITIES_DOCUMENT.format(path=self.store.path()))
        blocks = tagged_blocks(doc_format(), document, ActivityDoc.STORY_TAG)
        if not blocks:
            return TagDraftResult(None, (), (), 0, 0, 0, nothing_tagged=True)
        today = self.clock.now().date()
        recent = self._recent(today)
        pending = [replace(b, ref=Stories.BLOCK_REF.format(n=n)) for n, b in enumerate((b for b in blocks if _stored(b, recent) is None), 1)]
        written = StoryDrafts(day=today)
        saved: Path | None = None
        if pending:
            if on_drafting is not None:
                on_drafting(len(pending))
            written = self.writer.draft_from_blocks(today, pending, self._analyses(pending), [s for d in recent for s in d.stories])
            self._check_provenance(written)
            self._save(today, written)
            saved = self.repo.story_drafts_path(today)
            recent = self._recent(today)
        replacements, skipped = self._handled(blocks, recent)
        replaced, deferred, edited = self._replace(replacements)
        titles = {s.id: s.title for drafts in recent for s in drafts.stories}
        return TagDraftResult(saved, tuple(written.stories), tuple(skipped), replaced, deferred, edited, nothing_tagged=False, titles=titles)

    def _recent(self, today: date) -> list[StoryDrafts]:
        """The drafts of the last `dedup_days` days and today's, oldest first."""
        return self.repo.recent_story_drafts(today + timedelta(days=1), self.dedup_days + 1)

    def _analyses(self, blocks: list[TaggedBlock]) -> list[Analysis]:
        """The analyses of the meetings the blocks link to; a label with no analysis (a deleted meeting) is left out."""
        labels = dict.fromkeys(label for block in blocks for label in block.labels)
        return [self.repo.load_analysis(m) for m in labels if self.repo.exists(m) and ANALYSIS in self.repo.files(m)]

    def _save(self, today: date, written: StoryDrafts) -> None:
        """Today's drafts with the new ones appended (numbering kept), rendered from what is stored."""
        current = self.repo.load_story_drafts(today) or StoryDrafts(day=today)
        merged = StoryDrafts(today, [*current.stories, *written.stories], [*current.skipped, *written.skipped])
        degraded = untrusted_sources(self.repo, (m for story in merged.stories for m in story.source_meetings))
        self.repo.save_story_drafts(merged, self.renderer.render(merged, recent_stories(self.repo, today, self.dedup_days), degraded))

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

    @staticmethod
    def _handled(blocks: list[TaggedBlock], recent: list[StoryDrafts]) -> tuple[list[tuple[TaggedBlock, str]], list[SkippedAction]]:
        """For every block now in the drafts: the text its tag becomes (a link to its story's drafts document, or "already
        exists" for a duplicate), and the skips (a skip with another reason keeps its tag)."""
        titles = {s.id: s.title for drafts in recent for s in drafts.stories}
        replacements: list[tuple[TaggedBlock, str]] = []
        skipped: list[SkippedAction] = []
        for block in blocks:
            found = _stored(block, recent)
            if found is None:
                continue
            item, day = found
            if isinstance(item, UserStory):
                target = Stories.DRAFTS_LINK.format(folder=Files.PLANS_DIR, name=Files.STORIES_MARKDOWN.format(day=day.isoformat()))
                replacements.append((block, ActivityDoc.STORY_LINK.format(date=day.strftime(Stories.LINK_DATE_FORMAT), target=target)))
                continue
            skipped.append(item)
            if item.duplicate_of in titles:
                replacements.append((block, ActivityDoc.STORY_EXISTS.format(title=titles[item.duplicate_of])))
        return replacements, skipped

    def _replace(self, replacements: list[tuple[TaggedBlock, str]]) -> tuple[int, int, int]:
        """(replaced, deferred, edited): each tag replaced where its line is found exactly once in a fresh read of the document,
        and in base.md, under a lock that is not waited for."""
        if not replacements:
            return 0, 0, 0
        with self.store.lock(wait=False) as held:
            if not held:
                return 0, len(replacements), 0
            document = self.store.read_document() or ""
            base = self.store.read_base()
            changed_base = False
            replaced = 0
            for block, text in replacements:
                line = block.lines[0]
                swapped = replace_tag(document, line, ActivityDoc.STORY_TAG, text)
                if swapped is None:
                    continue
                document, replaced = swapped, replaced + 1
                if base is not None and (in_base := replace_tag(base, line, ActivityDoc.STORY_TAG, text)) is not None:
                    base, changed_base = in_base, True
            if replaced:
                self.store.rewrite_document(document, base if changed_base else None)
            return replaced, 0, len(replacements) - replaced


def _stored(block: TaggedBlock, recent: list[StoryDrafts]) -> tuple[UserStory | SkippedAction, date] | None:
    """The story whose `source_text` starts with the block's tagged line, or the skip with that `source_line`, in the newest
    drafts that have one, with the day of those drafts."""
    first = block.lines[0].rstrip()
    for drafts in reversed(recent):
        for story in drafts.stories:
            if story.source_text is not None and story.source_text.split("\n", 1)[0].rstrip() == first:
                return story, drafts.day
        for skip in drafts.skipped:
            if skip.source_line is not None and skip.source_line.rstrip() == first:
                return skip, drafts.day
    return None


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
    reported and the others go on. It reads only the day's `*.stories.json`: the document is
    re-rendered from what that file stores, so no plan is needed.
    """

    repo: MeetingRepository
    publishers: list[StoryPublisher]
    renderer: StoryRenderer
    notifier: Notifier
    clock: Clock
    dedup_days: int = Stories.DEDUP_DAYS

    def execute(self, day: date, only: list[int] | None = None) -> PublishReport:
        drafts = self.repo.load_story_drafts(day)
        if drafts is None:
            raise RepositoryError(Err.STORIES_MISSING.format(day=day.isoformat()))
        selected = self._select(drafts, only)
        existing = recent_stories(self.repo, day, self.dedup_days)
        degraded = untrusted_sources(self.repo, (m for story in drafts.stories for m in story.source_meetings))
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
                self.repo.save_story_drafts(drafts, self.renderer.render(drafts, existing, degraded))
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


def untrusted_sources(repo: MeetingRepository, meeting_ids: Iterable[str]) -> dict[str, TranscriptHealth]:
    """The meetings among `meeting_ids` whose transcript cannot be trusted, by meeting id: degraded (a whisper loop
    survived the retry) or made from a Teams track recorded at the wrong sample rate. The drafts document warns
    that what came from them may be incomplete or invented (PRD decision 9). A meeting whose transcript is gone or
    unreadable is left out: the warning is advice, never a reason to fail."""
    found: dict[str, TranscriptHealth] = {}
    for meeting_id in dict.fromkeys(meeting_ids):
        try:
            if not repo.exists(meeting_id) or TRANSCRIPT_JSON not in repo.files(meeting_id):
                continue
            health = repo.load_transcript(meeting_id).health
        except TeamsRecorderError:
            continue
        if health is not None and health.untrusted:
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

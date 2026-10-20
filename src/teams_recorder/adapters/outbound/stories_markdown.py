"""StoryRenderer that writes plans/<day>.stories.md, the document the user reviews.

One section per story: title; kind, priority, due date and source meetings; where it was
published; the story sentence; acceptance criteria as a checklist; the other sections the
guide asked for; open questions; and the item of the activities document it came from, as the
user wrote it. Then the items that did not become stories, with the reason and, for duplicates,
the title of the existing story that covers them. Everything it prints is what `*.stories.json`
stores, so a re-render after a publication needs nothing else: a story drafted by the old planner
shows its stored meetings only, and one of its skipped actions its id and reason. A source meeting
whose transcript is degraded gets a warning banner under the intro, and a task card from an action
the verifier did not confirm shows the mark and its reason. Labels come from messages.StoryDoc.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from teams_recorder.domain import Criterion, SkippedAction, StoryDrafts, TranscriptHealth, UserStory, unconfirmed_reason
from teams_recorder.messages import Minutes, StoryDoc


def _br(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _source_label(criterion: Criterion) -> str:
    """Where a criterion comes from: the transcript time, "(sugestão)", or nothing for drafts made before provenance."""
    if criterion.suggested:
        return StoryDoc.CRITERION_SUGGESTION
    return StoryDoc.CRITERION_AT.format(at=criterion.source) if criterion.source else ""


def _code(text: str) -> str:
    """`text` as a Markdown code span (double backticks when it holds a backtick itself)."""
    text = text.strip()
    return (StoryDoc.LONG_CODE_SPAN if "`" in text else StoryDoc.CODE_SPAN).format(text=text)


@dataclass
class MarkdownStoryRenderer:
    def render(self, drafts: StoryDrafts, existing: list[UserStory], degraded: dict[str, TranscriptHealth] | None = None) -> str:
        titles = {s.id: s.title for s in [*existing, *drafts.stories]}
        day = _br(drafts.day)
        out: list[str] = [StoryDoc.TITLE.format(date=day), "", StoryDoc.INTRO.format(date=day)]
        for meeting_id, health in (degraded or {}).items():
            if health.degraded:
                gaps = Minutes.DEGRADED_GAPS.format(ranges=", ".join(health.uncovered_ranges())) if health.uncovered else ""   # as in the minutes
                out += ["", StoryDoc.DEGRADED.format(meeting=meeting_id, loop=health.loop_share, gaps=gaps)]
            if health.rate_mismatch:
                out += ["", StoryDoc.RATE_MISMATCH.format(meeting=meeting_id, share=health.short_padding_share)]
            if health.untrusted:
                out += ["", StoryDoc.NOT_VERIFIED.format(meeting=meeting_id)]
        if not drafts.stories:
            out += ["", StoryDoc.NO_STORIES]
        for n, story in enumerate(drafts.stories, 1):
            out += ["", *self._story(n, story)]
        if drafts.skipped:
            out += ["", StoryDoc.SKIPPED]
            out += [self._skipped(skipped, titles) for skipped in drafts.skipped]
        out += ["", StoryDoc.FOOTER]
        return "\n".join(out) + "\n"

    @staticmethod
    def _skipped(skipped: SkippedAction, titles: dict[str, str]) -> str:
        covered_by = StoryDoc.DUPLICATE_OF.format(title=titles.get(skipped.duplicate_of, skipped.duplicate_of)) if skipped.duplicate_of else ""
        if skipped.source_line is None:   # a planner-era entry: its action is no longer loadable
            return StoryDoc.SKIPPED_LINE.format(id=skipped.action_id, reason=skipped.reason, covered_by=covered_by)
        return StoryDoc.SKIPPED_BLOCK_LINE.format(line=_code(skipped.source_line), reason=skipped.reason, covered_by=covered_by)

    def _story(self, n: int, story: UserStory) -> list[str]:
        out = [StoryDoc.STORY_TITLE.format(n=n, title=story.title)]
        meta: list[str] = []
        if story.kind:
            meta.append(StoryDoc.KIND.format(label=StoryDoc.KIND_LABELS[story.kind.value]))
        if story.priority:
            meta.append(StoryDoc.PRIORITY.format(label=Minutes.PRIORITY_LABELS[story.priority.value]))
        if story.due:
            meta.append(StoryDoc.DUE.format(date=_br(story.due)))
        if story.source_meetings:
            meta.append(StoryDoc.MEETINGS.format(ids=", ".join(story.source_meetings)))
        if meta:
            out.append(StoryDoc.META_SEPARATOR.join(meta))
        out += [StoryDoc.PUBLISHED.format(destination=p.destination, ref=p.ref) for p in story.publications]
        reason = unconfirmed_reason(story.verification)
        if reason is not None:
            out.append(StoryDoc.UNCONFIRMED.format(reason=reason) if reason else StoryDoc.UNCONFIRMED_NO_REASON)
        out += ["", story.narrative]
        if story.acceptance_criteria:
            out += ["", StoryDoc.CRITERIA, *(StoryDoc.CRITERION.format(text=c.text) + _source_label(c) for c in story.acceptance_criteria)]
        if story.details:
            out += ["", story.details]
        if story.open_questions:
            out += ["", StoryDoc.QUESTIONS, *(StoryDoc.BULLET.format(text=q) for q in story.open_questions)]
        if story.source_text:
            out += ["", StoryDoc.SOURCE_BLOCK, *(StoryDoc.QUOTE.format(line=line).rstrip() for line in story.source_text.split("\n"))]
        return out

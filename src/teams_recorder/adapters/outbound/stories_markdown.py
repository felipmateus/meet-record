"""StoryRenderer that writes plans/<day>.stories.md, the document the user reviews.

One section per story: title; priority, due date and source meetings; where it was
published; the story sentence; acceptance criteria as a checklist; the other sections the
guide asked for; open questions; and the source actions with the transcript timestamp where
each was said. Then the actions
that did not become stories, with the reason and, for duplicates, the title of the existing
story that covers them. A source meeting whose transcript is degraded gets a warning banner under
the intro, and a task card from an action the verifier did not confirm shows the mark and its
reason. Labels come from messages.StoryDoc.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from teams_recorder.domain import Action, Criterion, StoryDrafts, TranscriptHealth, UserStory, unconfirmed_reason
from teams_recorder.messages import Minutes, StoryDoc


def _br(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _source(criterion: Criterion) -> str:
    """Where a criterion comes from: the transcript time, "(sugestão)", or nothing for drafts made before provenance."""
    if criterion.suggested:
        return StoryDoc.CRITERION_SUGGESTION
    return StoryDoc.CRITERION_AT.format(at=criterion.source) if criterion.source else ""


@dataclass
class MarkdownStoryRenderer:
    def render(self, drafts: StoryDrafts, actions: list[Action], existing: list[UserStory],
               degraded: dict[str, TranscriptHealth] | None = None) -> str:
        by_id = {a.id: a for a in actions}
        titles = {s.id: s.title for s in existing}
        day = _br(drafts.day)
        out: list[str] = [StoryDoc.TITLE.format(date=day), "", StoryDoc.INTRO.format(date=day)]
        for meeting_id, health in (degraded or {}).items():
            gaps = Minutes.DEGRADED_GAPS.format(ranges=", ".join(health.uncovered_ranges())) if health.uncovered else ""   # as in the minutes
            out += ["", StoryDoc.DEGRADED.format(meeting=meeting_id, loop=health.loop_share, gaps=gaps)]
        if not actions:
            out += ["", StoryDoc.NO_ACTIONS]
        elif not drafts.stories:
            out += ["", StoryDoc.NO_STORIES]
        for n, story in enumerate(drafts.stories, 1):
            out += ["", *self._story(n, story, by_id)]
        if drafts.skipped:
            out += ["", StoryDoc.SKIPPED]
            for skipped in drafts.skipped:
                action = by_id.get(skipped.action_id)
                covered_by = (
                    StoryDoc.DUPLICATE_OF.format(title=titles.get(skipped.duplicate_of, skipped.duplicate_of))
                    if skipped.duplicate_of else ""
                )
                out.append(StoryDoc.SKIPPED_LINE.format(
                    id=skipped.action_id,
                    description=action.description if action else StoryDoc.UNKNOWN_ACTION,
                    reason=skipped.reason,
                    covered_by=covered_by,
                ))
        out += ["", StoryDoc.FOOTER]
        return "\n".join(out) + "\n"

    def _story(self, n: int, story: UserStory, by_id: dict[str, Action]) -> list[str]:
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
            out += ["", StoryDoc.CRITERIA, *(StoryDoc.CRITERION.format(text=c.text) + _source(c) for c in story.acceptance_criteria)]
        if story.details:
            out += ["", story.details]
        if story.open_questions:
            out += ["", StoryDoc.QUESTIONS, *(StoryDoc.BULLET.format(text=q) for q in story.open_questions)]
        sources = [by_id[i] for i in story.source_action_ids if i in by_id]
        if sources:
            out += ["", StoryDoc.SOURCES]
            out += [
                StoryDoc.SOURCE_LINE.format(id=a.id, description=a.description, at=StoryDoc.AT.format(at=a.at) if a.at else "")
                for a in sources
            ]
        return out

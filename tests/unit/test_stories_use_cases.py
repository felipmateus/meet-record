"""Stories from tagged lines and publishing without plans: `DraftStoriesFromTags` and `PublishUserStories` on fakes (UT-070 to UT-079,
UT-121, UT-122, UT-124). Nothing here reaches a model, a board or the real data dir."""
from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterator

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.application.use_cases import (
    DraftStoriesFromTags,
    PublishUserStories,
    stories_waiting,
)
from teams_recorder.application.use_cases.stories import untrusted_sources
from teams_recorder.domain import (
    SUGGESTION,
    ActionKind,
    Criterion,
    Publication,
    PublishError,
    RepositoryError,
    Segment,
    SkippedAction,
    StoryDrafts,
    Transcript,
    TranscriptHealth,
    UserStory,
)
from teams_recorder.messages import ActivityDoc, Err, Notify, StoryDoc
from tests.fakes import (
    FakeClock,
    FakeNotifier,
    FakeStoryPublisher,
    FakeStoryRenderer,
    FakeStoryWriter,
    InMemoryActivityStore,
    InMemoryMeetingRepository,
)
from tests.fixtures.curation import FMT, NOW, seed

TAG = ActivityDoc.STORY_TAG
MEETING = datetime(2026, 10, 16, 9, 30, 11)
LABEL = "2026-10-16_09-30-11"
ESTIMATE = f"- [ ] **Estimar a integração de estoque** · seg 19/10 · [Daily 16/10][{LABEL}] {TAG}"
REVIEW = f"- [ ] **Revisar o PR do mapeamento de centros** · [Daily 16/10][{LABEL}] {TAG}"
LINK = ActivityDoc.STORY_LINK.format(date="19/10", target="../plans/2026-10-19.stories.md")
BOX = f"{FMT.box_start}\n> **Atualizado seg 19/10 10:12** · após Daily\n{FMT.box_end_prefix} 20261019-101200{FMT.box_end_suffix}\n"
LINKS = f"{FMT.links_start}\n[{LABEL}]: ../recordings/{LABEL}/minutes.md\n{FMT.links_end}\n"


def document(*lines: str) -> str:
    return f"# Atividades\n\n{BOX}\n{FMT.heading_actions}\n\n" + "".join(f"{line}\n" for line in lines) + f"\n{LINKS}"


@dataclass
class World:
    repo: InMemoryMeetingRepository
    store: EditOnLock
    writer: FakeStoryWriter
    renderer: FakeStoryRenderer
    clock: FakeClock
    draft: DraftStoriesFromTags

    @property
    def today(self) -> date:
        return self.clock.now().date()

    def stories(self, day: date | None = None) -> list[UserStory]:
        drafts = self.repo.load_story_drafts(day or self.today)
        return drafts.stories if drafts else []


class EditOnLock(InMemoryActivityStore):
    """Another editor changes the document after the use case read it and before it takes the lock."""

    edit: tuple[str, str] | None = None

    @contextmanager
    def lock(self, wait: bool = True) -> Iterator[bool]:
        if self.edit is not None and self.document is not None:
            self.document = self.document.replace(*self.edit)
        with super().lock(wait) as held:
            yield held


def world(*lines: str, base: bool = True, writer: FakeStoryWriter | None = None, dedup_days: int = 30, meeting: bool = True) -> World:
    repo = InMemoryMeetingRepository()
    if meeting:
        seed(repo, MEETING)
    text = document(*lines)
    store = EditOnLock(text, text if base else None)
    clock = FakeClock(NOW)
    writer = writer or FakeStoryWriter()
    renderer = FakeStoryRenderer()
    return World(repo, store, writer, renderer, clock, DraftStoriesFromTags(repo, store, writer, renderer, clock, dedup_days))


# --- drafting (UT-070 to UT-075) ---------------------------------------------------------------------------------------------
def test_a_tagged_block_is_drafted_with_its_meetings_and_merged_into_todays_drafts() -> None:           # UT-070
    w = world(ESTIMATE, "  - falta só o módulo de reservas", f"- [ ] sem a marca [Daily 16/10][{LABEL}]")
    result = w.draft.execute()

    day, blocks, analyses, existing = w.writer.calls[0]
    assert day == w.today and existing == []
    assert [b.lines for b in blocks] == [(ESTIMATE, "  - falta só o módulo de reservas")] and blocks[0].labels == (LABEL,)
    assert [a.meeting_id for a in analyses] == [LABEL]
    drafts, markdown = w.repo.story_drafts[w.today]
    story = drafts.stories[0]
    assert story.source_text == f"{ESTIMATE}\n  - falta só o módulo de reservas" and story.source_meetings == [LABEL]
    assert story.kind is ActionKind.FEATURE and markdown.startswith(f"# Stories {w.today}")
    assert result.stories == (story,) and result.drafts_path == w.repo.story_drafts_path(w.today) and not result.nothing_tagged
    assert (result.replaced, result.deferred, result.edited) == (1, 0, 0)
    assert w.store.locks == [False]                                             # the writer ran before, and without, the lock
    new_document, new_base = w.store.rewrites[0]
    assert ESTIMATE.replace(TAG, LINK) in new_document and TAG not in new_document
    assert new_base == new_document                                             # base.md got the same replacement


def test_the_writer_call_runs_without_the_curator_lock() -> None:
    w = world(ESTIMATE)
    seen: list[list[bool]] = []
    inner = w.writer.draft_from_blocks

    def spy(*args):  # noqa: ANN002, ANN202
        seen.append(list(w.store.locks))
        return inner(*args)

    w.writer.draft_from_blocks = spy  # type: ignore[method-assign]
    w.draft.execute()
    assert seen == [[]] and w.store.locks == [False]                            # no lock taken before the call; one try after


def test_new_stories_are_numbered_after_the_ones_todays_drafts_already_have() -> None:                # UT-071
    w = world(ESTIMATE)
    first, second = UserStory("One", "n", id="s1"), UserStory("Two", "n", id="s2")
    w.repo.save_story_drafts(StoryDrafts(w.today, [first, second]), "#")

    w.draft.execute()

    stories = w.stories()
    assert [s.title for s in stories[:2]] == ["One", "Two"] and stories[:2] == [first, second]
    assert stories[2].title.startswith("Story for ") and len(stories) == 3
    assert w.writer.calls[0][3] == [first, second]                              # today's drafts are "existing" for the writer


def test_a_duplicate_replaces_the_tag_with_where_the_story_already_is() -> None:                      # UT-072
    w = world(REVIEW, writer=FakeStoryWriter(duplicates={"Revisar o PR": "s-old"}))
    w.repo.save_story_drafts(StoryDrafts(w.today - timedelta(days=3), [UserStory("Mapeamento de centros", "n", id="s-old")]), "#")

    result = w.draft.execute()

    assert w.stories() == [] and [(k.duplicate_of, k.source_line) for k in result.skipped] == [("s-old", REVIEW)]
    assert result.titles == {"s-old": "Mapeamento de centros"} and result.replaced == 1
    assert REVIEW.replace(TAG, ActivityDoc.STORY_EXISTS.format(title="Mapeamento de centros")) in w.store.document


def test_nothing_tagged_calls_no_writer_and_takes_no_lock() -> None:                                  # UT-074
    w = world(f"- [ ] **A** [Daily 16/10][{LABEL}]")
    result = w.draft.execute()
    assert result.nothing_tagged and result.stories == () and result.drafts_path is None
    assert not w.writer.calls and w.store.locks == [] and not w.repo.story_drafts


def test_no_activities_document_is_an_error() -> None:
    w = world(ESTIMATE)
    w.store.document = None
    with pytest.raises(RepositoryError, match="No activities document yet"):
        w.draft.execute()
    assert not w.writer.calls


def test_a_block_the_writer_skips_keeps_its_tag_and_is_reported_with_its_reason() -> None:           # UT-075
    w = world(ESTIMATE, REVIEW, writer=FakeStoryWriter(skips={"Revisar o PR": "é uma revisão, não uma história"}))
    result = w.draft.execute()
    assert [s.source_text.split("\n")[0] for s in w.stories()] == [ESTIMATE]
    assert [(k.action_id, k.reason, k.source_line, k.duplicate_of) for k in result.skipped] == [("b2", "é uma revisão, não uma história", REVIEW, None)]
    assert (result.replaced, result.deferred, result.edited) == (1, 0, 0)
    assert REVIEW in w.store.document and ESTIMATE not in w.store.document      # only the drafted line lost its tag


def test_the_analyses_of_meetings_that_are_gone_are_left_out_and_the_writer_still_runs() -> None:
    w = world(f"- [ ] algo [Daily][{LABEL}] [Outra][2026-01-01_10-00-00] {TAG}", "- [ ] sem reunião #história")
    w.draft.execute()
    _, blocks, analyses, _ = w.writer.calls[0]
    assert [b.labels for b in blocks] == [(LABEL, "2026-01-01_10-00-00"), ()] and [a.meeting_id for a in analyses] == [LABEL]


def test_on_drafting_is_told_how_many_blocks_go_to_the_writer_and_only_then() -> None:
    w = world(ESTIMATE, REVIEW)
    told: list[int] = []
    w.draft.execute(told.append)
    assert told == [2]
    w.store.document = document(ESTIMATE)                  # a rerun with nothing new: every block is in the drafts
    w.draft.execute(told.append)
    assert told == [2] and len(w.writer.calls) == 1


# --- edited lines, busy lock, never re-drafted (UT-073, UT-076, UT-077, UT-122) -------------------------------------------------
class EditingWriter(FakeStoryWriter):
    """Edits the document while the model "thinks": between the use case's first read and the replacement."""

    def __init__(self, store: InMemoryActivityStore, old: str, new: str) -> None:
        super().__init__()
        self.store, self.old, self.new = store, old, new

    def draft_from_blocks(self, *args):  # noqa: ANN002, ANN201
        assert self.store.document is not None
        self.store.document = self.store.document.replace(self.old, self.new)
        return super().draft_from_blocks(*args)


def test_a_line_edited_meanwhile_keeps_its_tag_and_the_others_are_replaced_in_the_document_and_the_base() -> None:   # UT-073
    w = world(ESTIMATE, REVIEW)
    w.draft.writer = EditingWriter(w.store, "Estimar a integração", "Estimei a integração")

    result = w.draft.execute()

    assert (result.replaced, result.deferred, result.edited) == (1, 0, 1)
    assert result.drafts_path is not None and len(w.stories()) == 2             # both drafted: the edit came after the read
    document_after, base_after = w.store.rewrites[0]
    assert "Estimei a integração" in document_after and TAG in document_after.split("Estimei")[1].split("\n")[0]   # still tagged
    assert REVIEW.replace(TAG, LINK) in document_after
    assert base_after is not None and REVIEW.replace(TAG, LINK) in base_after and ESTIMATE in base_after          # the base never held the edit


def test_the_base_is_left_alone_when_it_does_not_hold_the_line() -> None:
    w = world(ESTIMATE, base=False)
    w.store.base = document("- [ ] outra coisa")
    w.draft.execute()
    document_after, base_after = w.store.rewrites[0]
    assert LINK in document_after and base_after is None and w.store.base == document("- [ ] outra coisa")
    w2 = world(ESTIMATE, base=False)                       # no base.md at all
    w2.draft.execute()
    assert w2.store.rewrites[0][1] is None and w2.store.base is None


def test_a_busy_lock_saves_the_drafts_defers_the_replacement_and_persists_nothing_else() -> None:     # UT-076
    w = world(ESTIMATE, REVIEW)
    w.store.busy = True
    result = w.draft.execute()
    assert (result.replaced, result.deferred, result.edited) == (0, 2, 0) and result.drafts_path is not None
    assert w.store.locks == [False] and w.store.rewrites == [] and w.store.document == document(ESTIMATE, REVIEW)
    assert list(w.repo.story_drafts) == [w.today] and len(w.stories()) == 2     # the drafts file is the only memory


def test_a_later_run_replaces_the_tags_from_the_drafts_without_the_writer() -> None:                  # UT-077
    w = world(ESTIMATE, REVIEW, f"- [ ] **Terceiro** {TAG}", f"- [ ] **Quarto** {TAG}",
              writer=FakeStoryWriter(duplicates={"Terceiro": "s-old"}, skips={"Quarto": "é gestão"}))
    w.repo.save_story_drafts(StoryDrafts(w.today - timedelta(days=1), [UserStory("Já feito", "n", id="s-old")]), "#")
    w.store.busy = True
    first = w.draft.execute()
    assert first.deferred == 3 and len(w.writer.calls) == 1                      # the two stories and the duplicate wait; the skip keeps its tag

    w.store.busy = False
    w.store.edit = ("Estimar a integração", "Estimei a integração")                # edited meanwhile
    second = w.draft.execute()

    assert len(w.writer.calls) == 1                                              # nothing went to the writer again
    assert (second.replaced, second.deferred, second.edited) == (2, 0, 1) and second.drafts_path is None and second.stories == ()
    assert REVIEW.replace(TAG, LINK) in w.store.document and "Estimei a integração" in w.store.document
    assert ActivityDoc.STORY_EXISTS.format(title="Já feito") in w.store.document
    assert [(k.reason, k.source_line) for k in second.skipped if not k.duplicate_of] == [("é gestão", f"- [ ] **Quarto** {TAG}")]
    assert f"- [ ] **Quarto** {TAG}" in w.store.document                          # a stored skip keeps its tag and is reported again
    assert [k.duplicate_of for k in second.skipped if k.duplicate_of] == ["s-old"]


def test_running_twice_while_the_curator_holds_the_lock_drafts_each_item_once() -> None:             # UT-122
    w = world(ESTIMATE, REVIEW)
    w.store.busy = True
    first, second = w.draft.execute(), w.draft.execute()

    assert len(w.writer.calls) == 1                                               # only the first run reached the writer
    assert [s.title for s in w.stories()] == [s.title for s in first.stories] and len(w.stories()) == 2
    assert (second.deferred, second.stories, second.drafts_path) == (2, (), None)
    assert [s.id for s in w.stories()] == [s.id for s in first.stories]            # numbering and ids are stable

    w.store.busy = False
    third = w.draft.execute()
    assert (third.replaced, third.deferred) == (2, 0) and len(w.writer.calls) == 1
    assert TAG not in w.store.document and w.store.document.count(LINK) == 2

    board = FakeStoryPublisher("board")
    PublishUserStories(w.repo, [board], FakeStoryRenderer(), FakeNotifier(), w.clock).execute(w.today)
    assert [s.title for s, _ in board.calls] == [s.title for s in w.stories()]    # each story sent once


def test_a_block_in_the_drafts_of_an_earlier_day_is_not_drafted_again_and_links_that_day() -> None:
    w = world(ESTIMATE)
    earlier = w.today - timedelta(days=4)
    story = UserStory("Estimativa", "n", source_text=ESTIMATE + "\n  - nota antiga", source_meetings=[LABEL])
    w.repo.save_story_drafts(StoryDrafts(earlier, [story]), "#")

    result = w.draft.execute()

    assert not w.writer.calls and result.replaced == 1 and w.today not in w.repo.story_drafts
    assert ESTIMATE.replace(TAG, ActivityDoc.STORY_LINK.format(date="15/10", target="../plans/2026-10-15.stories.md")) in w.store.document


def test_drafts_older_than_the_window_do_not_count_as_drafted() -> None:
    w = world(ESTIMATE, dedup_days=5)
    w.repo.save_story_drafts(StoryDrafts(w.today - timedelta(days=6), [UserStory("Velha", "n", source_text=ESTIMATE)]), "#")
    w.draft.execute()
    assert len(w.writer.calls) == 1                                               # [today - 5 days, today] only


def test_a_writer_failure_saves_nothing_and_leaves_the_document_alone() -> None:
    w = world(ESTIMATE, writer=FakeStoryWriter(fail=True))
    with pytest.raises(Exception, match="model is down"):
        w.draft.execute()
    assert not w.repo.story_drafts and w.store.locks == [] and w.store.rewrites == []


# --- provenance, kinds, planner-era drafts (UT-078, UT-079, UT-124) --------------------------------------------------------------
class CitingWriter(FakeStoryWriter):
    def draft_from_blocks(self, day, blocks, analyses, existing):  # noqa: ANN001, ANN201
        drafts = super().draft_from_blocks(day, blocks, analyses, existing)
        for story in drafts.stories:
            story.acceptance_criteria = [Criterion("Exporta em CSV", "00:00:05"), Criterion("Inventado", "01:00:00")]
        return drafts


def test_a_cited_time_must_be_a_line_of_the_source_meetings_or_it_becomes_a_suggestion() -> None:
    w = world(ESTIMATE, f"- [ ] **Outro** {TAG}", writer=CitingWriter())
    w.repo.save_transcript(LABEL, Transcript([Segment(5.0, 9.0, "Vamos exportar em CSV.")]))

    w.draft.execute()

    first, second = w.stories()
    assert first.acceptance_criteria == [Criterion("Exporta em CSV", "00:00:05"), Criterion("Inventado", SUGGESTION)]
    assert second.acceptance_criteria == [Criterion("Exporta em CSV", SUGGESTION), Criterion("Inventado", SUGGESTION)]   # no meetings: no proof
    assert w.repo.load_story_drafts(w.today).stories[0].acceptance_criteria[1].suggested                            # saved checked


def test_degraded_source_meetings_reach_the_renderer_and_an_unreadable_one_does_not_fail() -> None:
    w = world(ESTIMATE, f"- [ ] **Outro** [x][2026-01-01_10-00-00] {TAG}")
    health = TranscriptHealth(0.668, 100, 80, True)
    w.repo.save_transcript(LABEL, Transcript([Segment(0, 1, "A CIDADE NO BRASIL")], health=health))
    w.draft.execute()
    assert w.renderer.degraded[0] == {LABEL: health}


def test_a_story_with_a_stored_kind_is_a_task_card_and_a_planner_era_file_loads_renders_and_publishes() -> None:   # UT-079, UT-078
    assert UserStory("t", "", kind=ActionKind.TECHNICAL).is_task_card and UserStory("t", "", kind=ActionKind.OPERATION).is_task_card
    assert not UserStory("s", "n", kind=ActionKind.FEATURE).is_task_card and not UserStory("s", "n").is_task_card
    old = {"day": "2026-10-19", "stories": [
        {"id": "s1", "title": "Estimar o mapa", "narrative": "", "source_action_ids": ["t1"], "source_meetings": [LABEL], "kind": "technical"},
        {"id": "s2", "title": "Exportar horas", "narrative": "Como gestor, quero exportar.", "source_action_ids": ["f1"], "source_meetings": [LABEL]}],
        "skipped": [{"action_id": "e1", "reason": "fica só no plano do dia", "duplicate_of": None}]}
    drafts = codec.story_drafts_from_dict(old)
    assert drafts.stories[0].is_task_card and not drafts.stories[1].is_task_card and drafts.stories[0].source_text is None
    assert drafts.skipped == [SkippedAction("e1", "fica só no plano do dia")] and drafts.skipped[0].source_line is None

    w = world(ESTIMATE, REVIEW, writer=FakeStoryWriter(skips={"Revisar o PR": "é uma revisão"}))
    w.repo.save_story_drafts(drafts, "# old\n")
    w.draft.renderer = MarkdownStoryRenderer()

    w.draft.execute()

    saved = w.repo.load_story_drafts(w.today)
    assert [s.title for s in saved.stories][:2] == ["Estimar o mapa", "Exportar horas"] and len(saved.stories) == 3     # numbering stable
    markdown = w.repo.story_drafts[w.today][1]
    assert "## 3. Story for" in markdown and f"> {ESTIMATE}" in markdown                                             # the new block's source
    assert StoryDoc.SOURCE_BLOCK in markdown and markdown.count(StoryDoc.SOURCE_BLOCK) == 1                            # old stories: meetings only
    assert f"**Reuniões:** {LABEL}" in markdown and "- `e1` — fica só no plano do dia" in markdown                      # a planner-era skip
    assert f"- `{REVIEW}` — é uma revisão" in markdown                                                               # a new skipped block

    board = FakeStoryPublisher("board")
    report = PublishUserStories(w.repo, [board], MarkdownStoryRenderer(), FakeNotifier(), w.clock).execute(w.today)
    assert len(report.published) == 3 and [s.title for s, _ in board.calls][:2] == ["Estimar o mapa", "Exportar horas"]


def test_each_skipped_block_prints_its_own_line_whatever_ref_a_run_gave_it() -> None:               # UT-124
    w = world(ESTIMATE, writer=FakeStoryWriter(skips={"Estimar": "primeiro motivo"}))
    w.draft.renderer = MarkdownStoryRenderer()
    w.draft.execute()
    w.store.document = document(ESTIMATE, REVIEW)                                  # a second block, tagged later
    w.draft.writer = FakeStoryWriter(skips={"Revisar": "segundo motivo"})

    second = w.draft.execute()

    saved = w.repo.load_story_drafts(w.today)
    assert [(k.action_id, k.source_line) for k in saved.skipped] == [("b1", ESTIMATE), ("b1", REVIEW)]   # the same ref twice: never looked up
    assert [k.source_line for k in second.skipped] == [ESTIMATE, REVIEW] and len(w.writer.calls) == 1
    markdown = w.repo.story_drafts[w.today][1]
    assert f"`{ESTIMATE}` — primeiro motivo" in markdown and f"`{REVIEW}` — segundo motivo" in markdown
    again = codec.story_drafts_from_dict(codec.story_drafts_to_dict(saved))
    assert again == saved
    assert "source_line" not in codec.story_drafts_to_dict(StoryDrafts(w.today, skipped=[SkippedAction("a1", "x")]))["skipped"][0]


# --- publishing without plans (UT-121) ------------------------------------------------------------------------------------------
def _drafts(w: World, titles=("One", "Two", "Three")) -> list[UserStory]:
    stories = [UserStory(t, "n", id=f"s{i}", source_text=f"- [ ] {t} {TAG}", source_meetings=[LABEL]) for i, t in enumerate(titles, 1)]
    w.repo.save_story_drafts(StoryDrafts(w.today, stories), "# drafts")
    return stories


def test_publishing_needs_no_plan_and_rerenders_after_each_publication_from_the_stored_drafts() -> None:    # UT-121
    w = world(ESTIMATE)
    _drafts(w)
    health = TranscriptHealth(0.668, 100, 80, True)
    w.repo.save_transcript(LABEL, Transcript([Segment(0, 1, "oi")], health=health))
    board, other, renderer, notifier = FakeStoryPublisher("board"), FakeStoryPublisher("other"), FakeStoryRenderer(), FakeNotifier()
    uc = PublishUserStories(w.repo, [board, other], renderer, notifier, w.clock)

    report = uc.execute(w.today)

    assert len(report.published) == 6 and report.already_published == 0 and not report.failures
    saved = w.repo.load_story_drafts(w.today)
    assert [p.destination for p in saved.stories[0].publications] == ["board", "other"]
    assert saved.stories[0].publication("board").published_at == w.clock.now()
    assert len(renderer.calls) == 6 and renderer.degraded[-1] == {LABEL: health}     # degraded from the stories' source meetings
    assert notifier.messages[-1] == (Notify.STORIES_PUBLISHED, Notify.STORIES_PUBLISHED_BODY.format(count=6))

    again = uc.execute(w.today)
    assert again.published == [] and again.already_published == 6 and len(board.calls) == 3
    assert len(notifier.messages) == 1


def test_a_day_without_drafts_is_an_error_and_stories_waiting_reads_the_same_drafts() -> None:
    w = world(ESTIMATE)
    with pytest.raises(RepositoryError, match=re.escape(Err.STORIES_MISSING.format(day=w.today.isoformat()))):
        PublishUserStories(w.repo, [FakeStoryPublisher()], FakeStoryRenderer(), FakeNotifier(), w.clock).execute(w.today)
    stories = _drafts(w)
    stories[0].publications.append(Publication("board", "T-1", w.clock.now()))
    assert [s.title for s in stories_waiting(w.repo, w.today, 30, ["board"])] == ["Two", "Three"]


def test_untrusted_sources_takes_meeting_ids_and_skips_what_it_cannot_read() -> None:
    w = world(ESTIMATE)
    wrong_rate = TranscriptHealth(0.0, 12, 12, False, rate_mismatch=True, short_padding_share=0.669)
    w.repo.save_transcript(LABEL, Transcript([Segment(0, 1, "oi")], health=wrong_rate))
    assert untrusted_sources(w.repo, [LABEL, LABEL, "gone"]) == {LABEL: wrong_rate}
    assert untrusted_sources(w.repo, []) == {}


def test_publish_failure_does_not_stop_other_destinations() -> None:
    w = world(ESTIMATE)
    _drafts(w)
    board, broken = FakeStoryPublisher("board"), FakeStoryPublisher("broken", fail_all=True)
    notifier = FakeNotifier()
    report = PublishUserStories(w.repo, [broken, board], FakeStoryRenderer(), notifier, w.clock).execute(w.today)
    assert len(report.published) == 3 and len(report.failures) == 3
    assert report.failures[0].destination == "broken" and "refused One" in report.failures[0].error
    assert notifier.messages[-1] == (Notify.PUBLISH_FAILED, Notify.PUBLISH_FAILED_BODY.format(failed=3, published=3))


def test_publish_saves_each_success_before_the_next_story() -> None:
    w = world(ESTIMATE)
    _drafts(w)
    renderer = FakeStoryRenderer()
    report = PublishUserStories(w.repo, [FakeStoryPublisher("board", fail_on={"Two"})], renderer, FakeNotifier(), w.clock).execute(w.today)
    assert [bool(s.publications) for s in w.repo.load_story_drafts(w.today).stories] == [True, False, True]
    assert len(renderer.calls) == 2 and [o.story.title for o in report.failures] == ["Two"]


def test_publish_only_selected_numbers_and_validates_them_first() -> None:
    w = world(ESTIMATE)
    _drafts(w)
    board = FakeStoryPublisher("board")
    uc = PublishUserStories(w.repo, [board], FakeStoryRenderer(), FakeNotifier(), w.clock)
    with pytest.raises(PublishError, match=re.escape(Err.INVALID_STORY_NUMBER.format(number=9, day=w.today.isoformat(), count=3))):
        uc.execute(w.today, only=[2, 9])
    assert not board.calls
    assert [o.story.title for o in uc.execute(w.today, only=[2, 2]).published] == ["Two"]
    assert uc.execute(w.today, only=[]).published == []


def test_publish_rerenders_with_the_stories_of_earlier_days() -> None:
    w = world(ESTIMATE)
    _drafts(w, titles=("One",))
    earlier = UserStory("Earlier", "n", id="e1")
    w.repo.save_story_drafts(StoryDrafts(w.today - timedelta(days=3), [earlier]), "#")
    renderer = FakeStoryRenderer()
    PublishUserStories(w.repo, [FakeStoryPublisher()], renderer, FakeNotifier(), w.clock, dedup_days=30).execute(w.today)
    assert renderer.calls[0][1] == [earlier]

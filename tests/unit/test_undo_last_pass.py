"""`UndoLastPass` on fakes: the preview, the commit an undo is, walking back through the passes, busy and stale, and what the next
pass sees afterwards (UT-060 to UT-066, UT-118, UT-119, UT-126)."""
from __future__ import annotations

from datetime import datetime

import pytest

from teams_recorder.application.use_cases.activities import UndoLastPass, UndoPreview, UndoResult
from teams_recorder.domain import CuratorBusy, NothingToUndo, PassKind, PassRecord, RemovedItem, UndoStale, body_text, unified_diff
from teams_recorder.messages import Err
from tests.fakes import FakeActivityCurator, InMemoryActivityStore, InMemoryMeetingRepository
from tests.fixtures.curation import FMT, SKELETON, answer, archive, build, insert, rec, seed

FIRST = "- [ ] **Enviar o cronograma**"
SECOND = "- [ ] **Estimar a integração**"
THIRD = "- [ ] **Ligar para a Acme**"


class World:
    """A repository, a store, a curator that answers what the test scripts, and the use case under test."""

    def __init__(self, busy: bool = False) -> None:
        self.repo = InMemoryMeetingRepository()
        self.store = InMemoryActivityStore(busy=busy)
        self.curator = FakeActivityCurator()
        self.use, self.notifier, self.clock = build(self.repo, self.store, self.curator)
        self.undo = UndoLastPass(self.store, self.clock)
        self.count = 0

    def curate(self, *ops, summary: str = "1 ação nova", removed: tuple[RemovedItem, ...] = ()) -> PassRecord:
        """One pass over a meeting of its own that answers `ops`; returns its record."""
        self.count += 1
        meeting = seed(self.repo, datetime(2026, 10, 19, 8 + self.count, 0))
        self.curator.outputs = [answer(ops, summary=summary, user_removed=removed)]
        self.clock.advance(minutes=5)
        self.use.execute([meeting])
        return self.store.records[-1]

    def edit(self, old: str, new: str) -> None:
        """What the user does in the editor."""
        assert self.store.document is not None and old in self.store.document
        self.store.document = self.store.document.replace(old, new, 1)

    def undo_now(self) -> UndoResult:
        preview = self.undo.preview()
        assert preview is not None
        return self.undo.execute(preview.version)


# --- the preview (UT-060, UT-066) -------------------------------------------------------------------------------------

def test_the_preview_shows_the_last_pass_the_diff_back_and_the_lines_edited_after_it() -> None:  # UT-060
    world = World()
    world.curate(insert(FIRST))
    last = world.curate(insert(SECOND))
    reworded = FIRST + " (urgente)"
    world.edit(FIRST, reworded)
    before = world.store.version(last.version).before

    preview = world.undo.preview()

    assert isinstance(preview, UndoPreview) and preview.version == last.version and preview.record == last
    assert preview.diff == unified_diff(body_text(FMT, world.store.document or ""), body_text(FMT, before))
    assert f"-{SECOND}" in preview.diff and f"-{reworded}" in preview.diff and f"+{FIRST}" in preview.diff
    assert preview.edited_after == 1                       # one line reworded after the pass; the pass's own lines are not "edited after"


def test_a_preview_of_an_untouched_pass_counts_no_edited_line() -> None:
    world = World()
    last = world.curate(insert(FIRST))
    preview = world.undo.preview()
    assert preview is not None and preview.version == last.version and preview.edited_after == 0
    assert f"-{FIRST}" in preview.diff.splitlines()


def test_a_deleted_line_counts_as_edited() -> None:
    world = World()
    world.curate(insert(FIRST), insert(SECOND, refs=("1.a2",)))
    world.edit(SECOND + "\n", "")
    preview = world.undo.preview()
    assert preview is not None and preview.edited_after == 1


def test_the_preview_is_none_when_no_pass_can_be_undone() -> None:  # UT-066
    world = World()
    assert world.undo.preview() is None


def test_the_preview_after_an_undo_describes_the_previous_pass() -> None:  # UT-066
    world = World()
    first = world.curate(insert(FIRST))
    second = world.curate(insert(SECOND))
    one = world.undo.preview()
    assert one is not None and one.version == second.version
    world.undo.execute(one.version)
    two = world.undo.preview()
    assert two is not None and two.version == first.version != one.version
    world.undo.execute(two.version)
    assert world.undo.preview() is None


def test_failed_skipped_and_undo_records_are_never_the_target() -> None:
    world = World()
    only = world.curate(insert(FIRST))
    world.store.log_pass(rec(PassKind.FAILED, "m9", version="20261019-120000"))
    world.store.log_pass(rec(PassKind.SKIPPED_EMPTY, "m8", version="20261019-120100"))
    preview = world.undo.preview()
    assert preview is not None and preview.version == only.version
    world.undo.execute(preview.version)
    assert world.undo.preview() is None
    assert [r.kind for r in world.store.records][-1] is PassKind.UNDO       # and the undo record is not one either


# --- execute (UT-061, UT-063, UT-064, UT-065) -------------------------------------------------------------------------

def test_execute_commits_the_restore_through_the_store_with_the_base_the_pass_read() -> None:  # UT-061
    world = World()
    first = world.curate(insert(FIRST))
    first_after = world.store.document
    second = world.curate(insert(SECOND))
    world.edit(FIRST, FIRST + " (urgente)")
    current = world.store.document
    files = world.store.version(second.version)
    assert files.before == first_after and files.prevbase == world.store.version(first.version).base

    result = world.undo.execute(second.version)

    before, after, archived, base, record = world.store.commits[-1]
    assert (before, after, archived, base) == (current, files.before, [], files.prevbase)       # not `_before`: the base N read
    assert world.store.document == files.before and world.store.base == files.prevbase
    assert (record.kind, record.undoes, record.meetings) == (PassKind.UNDO, second.version, second.meetings)
    assert (record.during_edits, record.carried_edits, record.ops_applied, record.error) == (second.carried_edits, "", 0, None)
    assert record.version not in {first.version, second.version}                  # an undo has a version of its own
    assert record.ts == world.clock.now() and record.doc_chars == len(files.before)
    assert result == UndoResult(second.version, False, second.meetings)
    assert world.store.locks[-1] is False                                         # never waits


def test_executing_after_the_first_pass_commits_no_base() -> None:  # UT-061, UT-126
    world = World()
    first = world.curate(insert(FIRST))
    assert world.store.version(first.version).prevbase is None

    world.undo_now()

    assert world.store.commits[-1][3] is None and world.store.base is None
    assert world.store.document == SKELETON


def test_the_archive_is_truncated_last_and_only_through_the_store() -> None:  # UT-061
    world = World()
    world.curate(insert(FIRST))
    second = world.curate(archive(FIRST, "feito"))
    assert second.archive_bytes_after is not None and world.store.archive != ""

    result = world.undo_now()

    assert world.store.truncated == [second] and world.store.archive == "" and result.archive_left_in_place is False
    assert FIRST in (world.store.document or "")


def test_an_archive_that_is_not_as_the_pass_left_it_is_kept_and_reported() -> None:  # UT-062
    world = World()
    world.curate(insert(FIRST))
    second = world.curate(archive(FIRST, "feito"))
    world.store.archive += "### a later entry\ntext\n"

    result = world.undo_now()

    assert result.archive_left_in_place is True and world.store.truncated == []
    assert world.store.archive.endswith("### a later entry\ntext\n") and world.store.records[-1].undoes == second.version
    assert FIRST in (world.store.document or "")       # the document was restored all the same


def test_a_second_undo_walks_back_and_the_third_finds_nothing() -> None:  # UT-063
    world = World()
    first = world.curate(insert(FIRST))
    second = world.curate(insert(SECOND))
    one = world.undo_now()
    assert one.version == second.version and SECOND not in (world.store.document or "") and FIRST in (world.store.document or "")
    two = world.undo_now()
    assert two.version == first.version and world.store.document == SKELETON
    with pytest.raises(NothingToUndo, match=Err.NOTHING_TO_UNDO):
        world.undo.execute("anything")
    assert [r.kind for r in world.store.records] == [PassKind.MEETING, PassKind.MEETING, PassKind.UNDO, PassKind.UNDO]
    assert [r.undoes for r in world.store.records if r.kind is PassKind.UNDO] == [second.version, first.version]


def test_a_pass_after_an_undo_can_itself_be_undone_and_the_undone_one_stays_skipped() -> None:  # UT-063
    world = World()
    first = world.curate(insert(FIRST))
    second = world.curate(insert(SECOND))
    world.undo_now()
    third = world.curate(insert(THIRD))
    assert world.undo.preview() is not None and world.undo.preview().version == third.version     # type: ignore[union-attr]
    assert world.undo_now().version == third.version
    assert world.undo_now().version == first.version                                              # second was undone: skipped
    assert second.version not in {r.version for r in world.store.records if r.kind is PassKind.UNDO}


def test_a_busy_curator_raises_at_once_and_changes_nothing() -> None:  # UT-064
    world = World()
    last = world.curate(insert(FIRST))
    document, base, commits = world.store.document, world.store.base, len(world.store.commits)
    world.store.busy = True

    with pytest.raises(CuratorBusy, match=Err.CURATOR_BUSY):
        world.undo.execute(last.version)

    assert world.store.locks[-1] is False
    assert (world.store.document, world.store.base, len(world.store.commits)) == (document, base, commits)


def test_a_pass_that_committed_after_the_preview_makes_the_confirmation_stale() -> None:  # UT-065
    world = World()
    world.curate(insert(FIRST))
    preview = world.undo.preview()
    assert preview is not None
    newer = world.curate(insert(SECOND))
    document, base, archive_text, commits = world.store.document, world.store.base, world.store.archive, len(world.store.commits)

    with pytest.raises(UndoStale, match="A new pass ran while you were deciding"):
        world.undo.execute(preview.version)

    assert (world.store.document, world.store.base, world.store.archive, len(world.store.commits)) == (document, base, archive_text, commits)
    assert world.store.truncated == [] and world.undo.preview().version == newer.version      # type: ignore[union-attr]


def test_another_undo_after_the_preview_also_makes_it_stale() -> None:
    world = World()
    world.curate(insert(FIRST))
    world.curate(insert(SECOND))
    preview = world.undo.preview()
    assert preview is not None
    world.undo.execute(preview.version)
    with pytest.raises(UndoStale):
        world.undo.execute(preview.version)


def test_a_failing_commit_leaves_the_archive_alone() -> None:
    world = World()
    world.curate(insert(FIRST))
    second = world.curate(archive(FIRST, "feito"))
    archive_text = world.store.archive
    world.store.fail_commit = OSError("disk full")
    with pytest.raises(OSError):
        world.undo.execute(second.version)
    assert world.store.archive == archive_text and world.store.truncated == []


# --- what the next pass sees (UT-118, UT-119, UT-126) -----------------------------------------------------------------

def test_an_item_the_user_deleted_and_the_pass_archived_is_seen_as_deleted_again_after_the_undo() -> None:  # UT-118
    world = World()
    world.curate(insert(FIRST), insert(SECOND, refs=("1.a2",)))
    world.edit(SECOND + "\n", "")                                              # the user deletes an open item
    note = RemovedItem(SECOND, "tirou do documento")
    world.curate(insert(THIRD), removed=(note,))                      # the pass archives it as `removido por você`
    assert "removido por você" in world.store.archive and SECOND in world.store.archive

    world.undo_now()

    assert SECOND not in (world.store.document or "") and THIRD not in (world.store.document or "")
    assert world.store.archive == ""                                            # the archive entry is gone
    world.curate()
    edits = world.curator.inputs[-1].user_edits
    assert f"-{SECOND}" in edits                                                # the next pass sees the deletion


def test_a_tick_made_before_the_undone_pass_is_seen_again_by_the_next_pass() -> None:  # UT-118
    world = World()
    world.curate(insert(FIRST))
    world.edit(FIRST, FIRST.replace("[ ]", "[x]"))                              # the user ticks it
    world.curate(insert(SECOND))
    world.undo_now()
    assert FIRST.replace("[ ]", "[x]") in (world.store.document or "")
    world.curate()
    edits = world.curator.inputs[-1].user_edits
    assert f"-{FIRST}" in edits and f"+{FIRST.replace('[ ]', '[x]')}" in edits


def test_the_next_pass_sees_what_the_undone_pass_carried_and_the_diff_from_its_base() -> None:  # UT-119
    world = World()
    world.curate(insert(FIRST))
    world.curator.during_call = lambda: world.edit(FIRST, FIRST + " (durante)")        # an edit while pass 2 thinks
    second = world.curate(insert(SECOND))
    world.curator.during_call = None
    assert second.during_edits != ""
    world.edit(FIRST + " (durante)", FIRST + " (durante) (depois)")
    third = world.curate(insert(THIRD))
    assert third.carried_edits == second.during_edits
    world.curator.during_call = None

    world.undo_now()                                                                    # undoes the third
    undo_record = world.store.records[-1]
    assert undo_record.during_edits == third.carried_edits == second.during_edits and undo_record.carried_edits == ""

    fourth = world.curate()
    prevbase = world.store.version(third.version).prevbase
    assert prevbase is not None
    expected = "\n".join(part for part in (
        third.carried_edits, unified_diff(body_text(FMT, prevbase), body_text(FMT, world.store.versions[undo_record.version].after))) if part)
    assert world.curator.inputs[-1].user_edits == expected and fourth.carried_edits == undo_record.during_edits
    undone_fourth = world.undo_now()
    assert undone_fourth.version == fourth.version
    assert world.store.records[-1].during_edits == fourth.carried_edits == third.carried_edits      # no edit is lost on the way back


def test_undoing_the_first_pass_leaves_no_base_and_the_next_pass_starts_like_a_first_pass() -> None:  # UT-119, UT-126
    world = World()
    world.curate(insert(FIRST))
    assert world.store.base is not None
    world.undo_now()
    assert world.store.base is None and world.store.document == SKELETON
    world.curate(insert(SECOND))
    data = world.curator.inputs[-1]
    assert data.user_edits == "" and data.document == SKELETON                          # a base of "" would list the whole skeleton

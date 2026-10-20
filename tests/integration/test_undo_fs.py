"""`UndoLastPass` on the file-backed store: two undos in a row, a child process holding the lock, undos interrupted at each step of the
journal and reconciled by the next lock (UT-062, UT-126, IT-006, IT-007, IT-015, IT-020, IT-021). The pure use-case rules are in
`tests/unit/test_undo_last_pass.py`."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.activities_fs import FsActivityStore
from teams_recorder.application.use_cases.activities import UndoLastPass
from teams_recorder.domain import CuratorBusy, PassKind, PassRecord, box_stamp, body_text, unified_diff
from tests.fakes import FakeActivityCurator
from tests.fixtures.curation import FMT, SKELETON, answer, archive, insert, rec, seed
from tests.integration.test_activities_store import HOLD, Faults, HardStop, make_store
from tests.integration.test_curate_meetings_fs import AGENDA, DAILY, ITEM, LATER, OTHER, PRIMED, World, document, prime


def run_pass(world: World, *ops, at: datetime = DAILY, title: str = "Daily", summary: str = "uma passada") -> PassRecord:
    """One pass over a meeting held at `at` that answers `ops`, on the world's own store; returns its record."""
    world.clock.advance(minutes=5)
    world.use(FakeActivityCurator([answer(list(ops), summary=summary)])).execute([seed(world.repo, at, title)])
    return world.store.passes()[-1]


def undoer(world: World, store: FsActivityStore | None = None) -> UndoLastPass:
    return UndoLastPass(store or world.store, world.clock)


def undo_now(use: UndoLastPass):
    preview = use.preview()
    assert preview is not None
    return use.execute(preview.version)


def archive_text(store: FsActivityStore) -> str:
    path = store.archive_dir / "2026-10.md"
    return path.read_text() if path.exists() else ""


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


class StopsBeforeTruncating(FsActivityStore):
    """A store whose process is killed after the pass-log line of an undo and before it takes the archive entries back."""

    def truncate_archive(self, record: PassRecord) -> bool:
        raise HardStop()


# --- IT-006: two undos in a row -------------------------------------------------------------------------------------------------

def test_two_undos_walk_back_to_the_document_and_the_archive_before_the_first_pass(world: World) -> None:  # IT-006
    text = document(ITEM, OTHER, agenda=AGENDA)
    prime(world.store, text)
    base = world.store.read_base()
    run_pass(world, insert("- [ ] Nova"), archive(AGENDA, "data passou"))
    first_after = world.store.read_document()
    run_pass(world, insert("- [ ] Outra", refs=("1.a1",)), archive(OTHER, "feito"), at=LATER)
    assert AGENDA in archive_text(world.store) and OTHER in archive_text(world.store)
    use = undoer(world)

    one = undo_now(use)
    assert world.store.read_document() == first_after and one.archive_left_in_place is False
    assert AGENDA in archive_text(world.store) and OTHER not in archive_text(world.store)       # only the second pass's entry went
    two = undo_now(use)

    assert two.archive_left_in_place is False and two.version != one.version
    assert world.store.read_document() == text and world.store.read_base() == base
    assert archive_text(world.store) == "" and not (world.store.archive_dir / "2026-10.md").exists()
    assert [r.kind for r in world.store.passes()] == [PassKind.MEETING, PassKind.MEETING, PassKind.MEETING, PassKind.UNDO, PassKind.UNDO]
    older = use.preview()
    assert older is not None and older.version == PRIMED                                    # what is left is the primed pass before them


def test_an_undo_is_written_through_the_journal_with_a_version_of_its_own(world: World) -> None:
    prime(world.store, document(ITEM))
    first = run_pass(world, insert("- [ ] Nova"))
    result = undo_now(undoer(world))
    record = world.store.passes()[-1]
    assert record.kind is PassKind.UNDO and record.undoes == first.version == result.version and record.version != first.version
    files = world.store.version(record.version)
    assert files.after == world.store.version(first.version).before and files.base == world.store.version(first.version).prevbase
    assert files.before == world.store.version(first.version).after and files.prevbase == world.store.version(first.version).base


# --- UT-062 on files, UT-126 -----------------------------------------------------------------------------------------------------

def test_an_archive_something_was_appended_to_after_the_pass_keeps_its_entries(world: World) -> None:  # UT-062
    prime(world.store, document(ITEM, agenda=AGENDA))
    run_pass(world, archive(AGENDA, "data passou"))
    path = world.store.archive_dir / "2026-10.md"
    path.write_text(path.read_text() + "### 20/10/2026 — outra\nitem\n")
    kept = path.read_bytes()
    assert undo_now(undoer(world)).archive_left_in_place is True
    assert path.read_bytes() == kept and AGENDA in (world.store.read_document() or "")           # restored all the same


def test_undoing_the_first_pass_deletes_base_md_and_writes_no_base_file(world: World) -> None:  # UT-126
    first = run_pass(world, insert("- [ ] Nova"))
    assert world.store.read_base() is not None and world.store.version(first.version).prevbase is None
    undo_now(undoer(world))
    record = world.store.passes()[-1]
    assert world.store.read_base() is None and not world.store.base_file.exists()
    assert not (world.store.versions_dir / f"{record.version}_base.md").exists()
    files = world.store.version(record.version)
    assert files.base is None and files.prevbase == world.store.version(first.version).base and files.after == SKELETON
    curator = FakeActivityCurator([answer()])
    world.use(curator).execute([seed(world.repo, LATER, "Outra")])
    assert curator.inputs[0].user_edits == "" and curator.inputs[0].document == SKELETON         # as on a first pass


# --- IT-007: the lock held by another process -------------------------------------------------------------------------------------

def hold(world: World, tmp_path: Path) -> tuple[subprocess.Popen[str], Path]:
    world.store.curator_dir.mkdir(parents=True, exist_ok=True)
    ready = tmp_path / "ready"
    child = subprocess.Popen([sys.executable, "-c", HOLD, str(world.store.lock_file), str(ready)], stdin=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 120
    while not ready.exists():
        assert child.poll() is None and time.monotonic() < deadline, "the child never took the lock"
        time.sleep(0.05)
    return child, ready


def release(child: subprocess.Popen[str]) -> None:
    assert child.stdin is not None
    child.stdin.write("\n")
    child.stdin.close()
    child.wait(timeout=60)


def test_undo_is_busy_within_a_second_and_a_waiting_pass_blocks_until_the_child_lets_go(world: World, tmp_path: Path) -> None:  # IT-007
    prime(world.store, document(ITEM))
    last = run_pass(world, insert("- [ ] Nova"))
    before = (world.store.read_document(), world.store.read_base(), len(world.store.passes()))
    child, _ = hold(world, tmp_path)
    try:
        started = time.monotonic()
        with pytest.raises(CuratorBusy):
            undoer(world).execute(last.version)
        assert time.monotonic() - started < 1
        assert (world.store.read_document(), world.store.read_base(), len(world.store.passes())) == before

        waiting, done = threading.Event(), threading.Event()
        meeting = seed(world.repo, LATER, "Outra")

        def curate() -> None:
            world.use(FakeActivityCurator([answer([insert("- [ ] Depois")])])).execute([meeting], wait=True, on_wait=waiting.set)
            done.set()

        thread = threading.Thread(target=curate)
        thread.start()
        assert waiting.wait(30)                                    # it found the lock held and said so
        assert not done.wait(1.0) and len(world.store.passes()) == before[2]      # and blocks
    finally:
        release(child)
    thread.join(60)
    assert done.is_set() and len(world.store.passes()) == before[2] + 1
    assert undo_now(undoer(world)).version == world.store.passes()[-2].version      # the lock is free again: undo works


# --- IT-015: an undo killed before it takes the archive entries back ------------------------------------------------------------------

def killed_before_truncating(world: World) -> tuple[PassRecord, PassRecord]:
    """Two passes that each archive one item, then an undo of the second killed after its pass-log line."""
    prime(world.store, document(ITEM, OTHER, agenda=AGENDA))
    first = run_pass(world, archive(AGENDA, "data passou"))
    second = run_pass(world, archive(OTHER, "feito"), at=LATER)
    stopping = StopsBeforeTruncating(world.data, FMT)
    with pytest.raises(HardStop):
        undoer(world, stopping).execute(second.version)
    return first, second


def test_an_undo_killed_before_the_archive_is_truncated_leaves_surplus_entries_never_missing_ones(world: World) -> None:  # IT-015
    first, second = killed_before_truncating(world)
    assert world.store.passes()[-1].undoes == second.version                               # the pass-log line is there
    assert OTHER in (world.store.read_document() or "")                                    # and the document is restored
    assert AGENDA in archive_text(world.store) and OTHER in archive_text(world.store)       # entries of both passes kept
    assert len(archive_text(world.store).encode()) == second.archive_bytes_after


def test_truncating_afterwards_goes_down_to_the_size_before_the_pass_and_not_below(world: World) -> None:  # IT-015
    first, second = killed_before_truncating(world)
    assert world.store.truncate_archive(second) is True
    assert len(archive_text(world.store).encode()) == second.archive_bytes_before == first.archive_bytes_after
    assert AGENDA in archive_text(world.store) and OTHER not in archive_text(world.store)


def test_another_undo_refuses_to_truncate_an_archive_that_is_not_as_its_pass_left_it(world: World) -> None:  # IT-015
    first, second = killed_before_truncating(world)
    kept = archive_text(world.store)
    result = undo_now(undoer(world))
    assert result.version == first.version and result.archive_left_in_place is True        # the second pass counts as undone
    assert archive_text(world.store) == kept
    assert world.store.truncate_archive(first) is False and archive_text(world.store) == kept
    assert len(kept.encode()) > first.archive_bytes_after > first.archive_bytes_before == 0


def test_a_new_pass_after_the_stop_stops_truncate_archive_from_cutting_its_entries(world: World) -> None:  # IT-015
    prime(world.store, document(ITEM, OTHER, agenda=AGENDA))
    first = run_pass(world, archive(AGENDA, "data passou"))
    with pytest.raises(HardStop):
        undoer(world, StopsBeforeTruncating(world.data, FMT)).execute(first.version)
    run_pass(world, archive(ITEM, "feito"), at=LATER)                                        # appends after the surplus
    kept = archive_text(world.store)
    assert world.store.truncate_archive(first) is False and archive_text(world.store) == kept


# --- IT-020: killed after the document restore and before base.md ---------------------------------------------------------------------

def test_an_undo_killed_before_base_md_is_rolled_forward_and_the_next_pass_sees_only_the_users_edits(world: World, tmp_path: Path) -> None:  # IT-020
    text = document(ITEM, OTHER)
    prime(world.store, text)
    edited = text.replace(OTHER, OTHER + " e confirmar o chamado")
    world.store.path().write_text(edited)                                   # the user's edit before the pass
    run_pass(world, insert("- [ ] Nova"), archive(ITEM, "feito"))
    undone = world.store.passes()[-1]
    stopped = make_store(tmp_path, Faults(fail_at="base", error=HardStop()))
    with pytest.raises(HardStop):
        undoer(world, stopped).execute(undone.version)
    assert world.store.read_document() == edited and world.store.read_base() != text        # restored; base.md is still the pass's
    assert [r.kind for r in world.store.passes()] == [PassKind.MEETING, PassKind.MEETING]

    curator = FakeActivityCurator([answer()])
    world.use(curator).execute([seed(world.repo, LATER, "Outra")])                          # the next lock reconciles

    records = world.store.passes()
    assert [r.kind for r in records[:3]] == [PassKind.MEETING, PassKind.MEETING, PassKind.UNDO] and records[2].undoes == undone.version
    assert records[2].carried_edits == "" and records[2].during_edits == undone.carried_edits
    expected = unified_diff(body_text(FMT, text), body_text(FMT, edited))
    assert expected != "" and curator.inputs[0].user_edits == expected                      # the edit, not the whole pass as deleted
    assert "Nova" not in curator.inputs[0].user_edits and curator.inputs[0].document == edited


# --- IT-021: undo of the first pass, interrupted ----------------------------------------------------------------------------------------

def first_pass(world: World) -> PassRecord:
    first = run_pass(world, insert("- [ ] Nova"), insert("- [ ] Segunda", refs=("1.a2",)))
    assert world.store.version(first.version).prevbase is None and box_stamp(FMT, world.store.read_document() or "") == first.version
    return first


def interrupted(world: World, tmp_path: Path, step: str, first: PassRecord) -> str | None:
    """Kills the undo of the first pass at `step`; returns the pass's base.md as it stood."""
    base = world.store.read_base()
    stopped = make_store(tmp_path, Faults(fail_at=step, error=HardStop()))
    with pytest.raises(HardStop):
        undoer(world, stopped).execute(first.version)
    return base


def unstamped(text: str, version: str) -> str:
    result = text.replace(f" {version}", "", 1)
    assert box_stamp(FMT, result) is None
    return result


def test_an_undo_of_the_first_pass_killed_before_the_restore_is_rolled_back(world: World, tmp_path: Path) -> None:  # IT-021 (a)
    first = first_pass(world)
    document_then, base = world.store.read_document(), interrupted(world, tmp_path, "document", first)
    assert box_stamp(FMT, world.store.version(first.version).after) == first.version
    with world.store.lock():
        pass
    assert world.store.read_document() == document_then and world.store.read_base() == base
    assert [r.kind for r in world.store.passes()] == [PassKind.MEETING] and archive_text(world.store) == ""
    assert sorted(p.name.partition("_")[0] for p in world.store.versions_dir.iterdir()) == [first.version] * 4    # the undo's files are gone
    assert undo_now(undoer(world)).version == first.version                                  # and the undo can simply be run again


@pytest.mark.parametrize("edit", [False, True])
def test_an_undo_of_the_first_pass_killed_before_base_md_is_rolled_forward(world: World, tmp_path: Path, edit: bool) -> None:  # IT-021 (b)
    first = first_pass(world)
    pass_base = world.store.read_base()
    assert pass_base is not None
    interrupted(world, tmp_path, "log", first)                  # killed after the restore and the deletion of base.md ...
    world.store.base_file.write_text(pass_base)                 # ... which, for this test, did not happen yet
    if edit:
        world.store.path().write_text((world.store.read_document() or "") + "linha do usuário\n")    # leaves the closing marker alone
    with world.store.lock():
        assert world.store.read_base() is None and not world.store.base_file.exists()
    undo = world.store.passes()[-1]
    assert undo.kind is PassKind.UNDO and undo.undoes == first.version and undo.carried_edits == "" and undo.during_edits == first.carried_edits
    assert box_stamp(FMT, world.store.read_document() or "") == FMT.skeleton_stamp
    curator = FakeActivityCurator([answer()])
    world.use(curator).execute([seed(world.repo, LATER, "Outra")])
    assert curator.inputs[0].user_edits == ""                   # as on a first pass, never the whole skeleton as the user's additions


def test_a_first_pass_undo_killed_before_the_restore_and_a_deleted_marker_is_still_rolled_back(world: World, tmp_path: Path) -> None:  # IT-021 (c)
    first = first_pass(world)
    base = interrupted(world, tmp_path, "document", first)
    world.store.path().write_text(unstamped(world.store.read_document() or "", first.version))
    with world.store.lock():
        pass
    assert world.store.read_base() == base and [r.kind for r in world.store.passes()] == [PassKind.MEETING]
    assert archive_text(world.store) == ""
    result = undo_now(undoer(world))                                                         # not counted as undone: it can be retried
    assert result.version == first.version and world.store.read_document() == SKELETON and world.store.read_base() is None


def test_a_first_pass_undo_killed_after_the_restore_and_a_deleted_marker_rolls_back_too(world: World, tmp_path: Path) -> None:  # IT-021 (d)
    first = first_pass(world)
    pass_base = world.store.read_base()
    assert pass_base is not None
    interrupted(world, tmp_path, "log", first)
    world.store.base_file.write_text(pass_base)
    world.store.path().write_text(unstamped(world.store.read_document() or "", FMT.skeleton_stamp))
    with world.store.lock():
        pass
    assert world.store.read_base() == pass_base and [r.kind for r in world.store.passes()] == [PassKind.MEETING]    # the accepted direction
    assert archive_text(world.store) == ""
    result = undo_now(undoer(world))                                                         # the retried undo restores the skeleton again
    assert result.version == first.version and world.store.read_document() == SKELETON and world.store.read_base() is None


# --- UT-126: an undone pass whose `_before` had no stamp ----------------------------------------------------------------------------------

def test_an_undo_whose_restored_text_has_no_stamp_is_rolled_back_after_a_stop_and_a_second_undo_completes(tmp_path: Path) -> None:  # UT-126
    store = make_store(tmp_path)
    world = World(tmp_path, store)
    store.commit(SKELETON, document(ITEM), [], "BASE0\n", rec(PassKind.MEETING, "m0", version=PRIMED, ts=datetime(2026, 10, 16, 17, 40)))
    marker_removed = unstamped(document(ITEM), PRIMED)                                       # the user removed the stamp before the pass
    store.path().write_text(marker_removed)
    after = document(ITEM, OTHER).replace(PRIMED, "20261019-101200")
    record = rec(PassKind.MEETING, "m1", version="20261019-101200", ts=datetime(2026, 10, 19, 10, 12))
    store.commit(marker_removed, after, [], "BASE1\n", record)
    assert store.version(record.version).prevbase == "BASE0\n"
    stopped = make_store(tmp_path, Faults(fail_at="base", error=HardStop()))
    with pytest.raises(HardStop):
        undoer(world, stopped).execute(record.version)
    assert store.read_document() == marker_removed and store.read_base() == "BASE1\n"         # the restore reached the file, base.md not yet

    with store.lock():
        pass

    assert store.read_document() == marker_removed and store.read_base() == "BASE1\n"         # rolled back: log, base.md and archive untouched
    assert [r.kind for r in store.passes()] == [PassKind.MEETING, PassKind.MEETING]
    assert undo_now(undoer(world)).version == record.version
    assert [r.kind for r in store.passes()] == [PassKind.MEETING, PassKind.MEETING, PassKind.UNDO] and store.read_base() == "BASE0\n"

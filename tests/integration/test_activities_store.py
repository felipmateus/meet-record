"""FsActivityStore: the OS lock, the recoverable commit order, reconciliation after a hard stop, rotation and the pass log.

Covers UT-125, IT-012, IT-014 and the store cases of the spec's Testing Approach. Pass-level journeys (IT-013, IT-019) and the
undo paths (UT-062, UT-126, IT-015, IT-020, IT-021) belong to tasks 5 and 9; the reconcile rules they rely on are exercised here
at the store level.
"""
from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import pytest

from teams_recorder.adapters.outbound import fs_retry
from teams_recorder.adapters.outbound.activities_fs import FsActivityStore, append_text
from teams_recorder.adapters.outbound.fs_retry import atomic_write
from teams_recorder.application.use_cases.activities import doc_format
from teams_recorder.constants import Activities, Files
from teams_recorder.domain import CommitIncomplete, PassKind, PassRecord, RepositoryError, box_stamp, render_box

FMT = doc_format()
NOW = datetime(2026, 10, 19, 10, 12)
SKELETON = (f"# Atividades\n\n{FMT.box_start}\n{FMT.box_end_prefix} {FMT.skeleton_stamp}{FMT.box_end_suffix}\n\n"
            f"{FMT.heading_actions}\n\n{FMT.links_start}\n{FMT.links_end}\n")
LABEL = "2026-10-14_10-00-03"
OLD_ITEM = f"- [ ] Ligar para a Acme ([Revisão SAP 14/10][{LABEL}])\n"


class HardStop(BaseException):
    """What a kill looks like to the code under test: nothing catches it, so no in-process rollback runs."""


def version_of(n: int) -> str:
    return (NOW + timedelta(minutes=n)).strftime("%Y%m%d-%H%M%S")


def document(version: str, *lines: str) -> str:
    """A document whose box carries `version` as its stamp, with one open item per line."""
    text = render_box(FMT, SKELETON, ["foco"], ["Daily"], NOW, version)[0]
    return text.replace(FMT.heading_actions + "\n", FMT.heading_actions + "\n\n" + "".join(f"- [ ] {line}\n" for line in lines), 1)


def record(n: int, **changes: object) -> PassRecord:
    fields: dict[str, object] = dict(
        ts=NOW + timedelta(minutes=n), kind=PassKind.MEETING, meetings=("m1",), ops_applied=1, retried=False, retried_by_kind={},
        unaccounted_refs=(), ignored=0, user_removed=0, box_rescued=0, during_edits="", summary=f"pass {n}", version=version_of(n),
        archive_file=None, archive_bytes_before=None, archive_bytes_after=None, carried_edits="", undoes=None, doc_chars=10, error=None)
    fields.update(changes)
    return PassRecord(**fields)  # type: ignore[arg-type]


def label_of(path: Path) -> str:
    name = path.name
    for suffix, label in (("_before.md", "before"), ("_after.md", "after"), ("_prevbase.md", "prevbase"), ("_base.md", "version_base"),
                          ("_pass.json", "pass")):
        if name.endswith(suffix):
            return label
    if path.parent.name == Files.ARCHIVE_DIR:
        return "archive"
    return {Files.ACTIVITIES_DOC: "document", Files.CURATOR_BASE: "base", Files.ACTIVITIES_LOG: "log"}[name]


STEPS = ["before", "after", "version_base", "prevbase", "pass", "archive", "document", "base", "log"]


class Faults:
    """Wraps the store's two writers: records the step of every call and fails (or stops) the call at `fail_at`."""

    def __init__(self, fail_at: str | None = None, error: BaseException | None = None, times: int = 1) -> None:
        self.fail_at = fail_at
        self.error = error or OSError(errno.EIO, "disk full")
        self.times = times
        self.steps: list[str] = []

    def around(self, real: Callable[[Path, str], None]) -> Callable[[Path, str], None]:
        def run(path: Path, text: str) -> None:
            step = label_of(path)
            self.steps.append(step)
            if step == self.fail_at and self.times > 0:
                self.times -= 1
                raise self.error
            real(path, text)

        return run


def make_store(tmp_path: Path, faults: Faults | None = None, keep_versions: int = Activities.KEEP_VERSIONS) -> FsActivityStore:
    faults = faults or Faults()
    return FsActivityStore(tmp_path / "data", FMT, keep_versions, write=faults.around(atomic_write), append=faults.around(append_text))


def snapshot(store: FsActivityStore) -> dict[str, object]:
    archives = {p.name: p.read_bytes() for p in store.archive_dir.glob("*")} if store.archive_dir.is_dir() else {}
    versions = sorted(p.name for p in store.versions_dir.glob("*")) if store.versions_dir.is_dir() else []
    log = store.pass_log.read_text() if store.pass_log.exists() else None
    return {"document": store.read_document(), "base": store.read_base(), "archives": archives, "versions": versions, "log": log}


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[Path, FsActivityStore]:
    """A store after one committed pass (version 0): a document, a base and an archive entry exist."""
    store = make_store(tmp_path)
    store.commit(SKELETON, document(version_of(0), "velho"), [(OLD_ITEM, "concluído")], "BASE0\n", record(0))
    return tmp_path, store


# --- lock ---------------------------------------------------------------------------------------------------------

HOLD = (
    "import fcntl, pathlib, sys\n"
    "handle = open(sys.argv[1], 'a+b')\n"
    "fcntl.flock(handle, fcntl.LOCK_EX)\n"
    "pathlib.Path(sys.argv[2]).write_text('held')\n"
    "sys.stdin.readline()\n"
)


def test_lock_without_waiting_yields_false_while_another_process_holds_it_and_true_after(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.curator_dir.mkdir(parents=True)
    ready = tmp_path / "ready"
    child = subprocess.Popen([sys.executable, "-c", HOLD, str(store.lock_file), str(ready)], stdin=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 120
        while not ready.exists():
            assert child.poll() is None and time.monotonic() < deadline, "the child never took the lock"
            time.sleep(0.05)
        started = time.monotonic()
        with store.lock(wait=False) as got:
            assert got is False
        assert time.monotonic() - started < 5   # it did not wait
    finally:
        assert child.stdin is not None
        child.stdin.write("\n")
        child.stdin.close()
        child.wait(timeout=60)
    with store.lock(wait=False) as got:
        assert got is True
    assert store.lock_file.read_bytes() == b""   # the lock file is only a flock target


def test_lock_is_exclusive_between_stores_of_the_same_folder(tmp_path: Path) -> None:
    first, second = make_store(tmp_path), make_store(tmp_path)
    with first.lock() as got:
        assert got is True
        with second.lock(wait=False) as other:
            assert other is False
    with second.lock(wait=False) as other:
        assert other is True


# --- reads ---------------------------------------------------------------------------------------------------------

def test_an_empty_store_reads_as_nothing(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.read_document() is None and store.read_base() is None
    assert store.passes() == [] and store.recent_archive(60) == []
    assert store.path() == tmp_path / "data" / "activities" / "atividades.md"
    with store.lock() as got:
        assert got is True


def test_reads_keep_the_line_endings_of_the_document(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.path().parent.mkdir(parents=True)
    store.path().write_bytes(b"# Atividades\r\n- [ ] item\r\n")
    assert store.read_document() == "# Atividades\r\n- [ ] item\r\n"


# --- commit ------------------------------------------------------------------------------------------------------

def test_commit_writes_the_pass_in_the_order_of_the_adr(tmp_path: Path) -> None:
    faults = Faults()
    store = make_store(tmp_path, faults)
    store.commit(SKELETON, document(version_of(0), "velho"), [], "BASE0\n", record(0))
    faults.steps.clear()
    after = document(version_of(1), "novo")
    store.commit(document(version_of(0), "velho"), after, [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    assert faults.steps == STEPS
    assert store.read_document() == after and store.read_base() == "BASE1\n"
    assert [r.version for r in store.passes()] == [version_of(0), version_of(1)]


def test_commit_leaves_the_version_files_and_the_sizes_of_the_archive(seeded: tuple[Path, FsActivityStore]) -> None:
    _, store = seeded
    archive = store.archive_dir / "2026-10.md"
    size_before = archive.stat().st_size
    before, after = document(version_of(0), "velho"), document(version_of(1), "novo")
    store.commit(before, after, [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    files = store.version(version_of(1))
    assert (files.before, files.after, files.base, files.prevbase) == (before, after, "BASE1\n", "BASE0\n")
    saved = json.loads((store.versions_dir / f"{version_of(1)}_pass.json").read_text())
    assert saved["archive_file"] == "arquivo/2026-10.md"
    assert saved["archive_bytes_before"] == size_before
    assert saved["archive_bytes_after"] == archive.stat().st_size > size_before
    logged = store.passes()[-1]
    assert (logged.archive_file, logged.archive_bytes_before, logged.archive_bytes_after) == (
        "arquivo/2026-10.md", size_before, archive.stat().st_size)


def test_a_pass_that_archives_nothing_keeps_the_archive_fields_of_its_record(seeded: tuple[Path, FsActivityStore]) -> None:
    _, store = seeded
    before = snapshot(store)["archives"]
    store.commit(document(version_of(0), "velho"), document(version_of(1), "velho", "novo"), [], "BASE1\n", record(1))
    assert snapshot(store)["archives"] == before
    assert store.passes()[-1].archive_file is None and store.passes()[-1].archive_bytes_after is None


def test_the_first_pass_has_no_prevbase_and_a_pass_with_no_base_writes_no_base_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.commit(SKELETON, document(version_of(0), "a"), [], None, record(0))
    files = store.version(version_of(0))
    assert files.base is None and files.prevbase is None
    assert sorted(p.name for p in store.versions_dir.iterdir()) == [f"{version_of(0)}_after.md", f"{version_of(0)}_before.md", f"{version_of(0)}_pass.json"]
    assert not store.base_file.exists()


def test_commit_with_no_base_deletes_base_md(seeded: tuple[Path, FsActivityStore]) -> None:
    _, store = seeded
    assert store.read_base() == "BASE0\n"
    store.commit(document(version_of(0), "velho"), SKELETON, [], None, record(1))
    assert store.read_base() is None and not store.base_file.exists()
    files = store.version(version_of(1))
    assert files.base is None and files.prevbase == "BASE0\n"
    assert not (store.versions_dir / f"{version_of(1)}_base.md").exists()


def test_an_unknown_version_is_a_repository_error(tmp_path: Path) -> None:
    with pytest.raises(RepositoryError):
        make_store(tmp_path).version("20200101-000000")


@pytest.mark.parametrize("step", STEPS[:7])
def test_a_failure_up_to_the_document_replace_leaves_everything_as_before(seeded: tuple[Path, FsActivityStore], step: str) -> None:
    tmp_path, _ = seeded
    faults = Faults(fail_at=step)
    store = make_store(tmp_path, faults)
    before = snapshot(store)
    with pytest.raises(RepositoryError, match="disk full") as caught:   # the file system's error leaves the store as a RepositoryError
        store.commit(document(version_of(0), "velho"), document(version_of(1), "novo"), [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    assert isinstance(caught.value.__cause__, OSError) and not isinstance(caught.value, CommitIncomplete)
    assert snapshot(store) == before
    assert faults.steps[-1] == step   # nothing ran after the failing step


def test_the_document_replace_raising_leaves_everything_as_before(seeded: tuple[Path, FsActivityStore],
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:   # IT-012
    tmp_path, _ = seeded
    store = make_store(tmp_path)
    before = snapshot(store)
    real_replace = os.replace

    def replace(src: str | Path, dst: str | Path) -> None:
        if Path(dst) == store.path():
            raise OSError(errno.EIO, "the document cannot be replaced")
        real_replace(src, dst)

    monkeypatch.setattr(fs_retry.os, "replace", replace)
    with pytest.raises(RepositoryError, match="cannot be replaced"):
        store.commit(document(version_of(0), "velho"), document(version_of(1), "novo"), [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    assert snapshot(store) == before
    assert not list(store.path().parent.glob("*" + Files.TMP_SUFFIX))   # the temporary file went too
    assert [r.version for r in store.passes()] == [version_of(0)]


def test_a_transient_failure_of_base_md_or_the_log_line_is_retried(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, _ = seeded
    for step in ("base", "log"):
        faults = Faults(fail_at=step, times=Activities.COMMIT_ATTEMPTS - 1)
        store = make_store(tmp_path, faults)
        n = 1 if step == "base" else 2
        store.commit(store.read_document() or "", document(version_of(n), f"item {n}"), [], f"BASE{n}\n", record(n))
        assert store.read_base() == f"BASE{n}\n" and store.passes()[-1].version == version_of(n)
        assert faults.steps.count(step) == Activities.COMMIT_ATTEMPTS


@pytest.mark.parametrize("step", ["base", "log"])
def test_a_persistent_failure_after_the_replace_is_reported_and_completed_by_the_next_lock(seeded: tuple[Path, FsActivityStore],
                                                                                          step: str) -> None:
    tmp_path, _ = seeded
    store = make_store(tmp_path, Faults(fail_at=step, times=99))
    after = document(version_of(1), "novo")
    with pytest.raises(CommitIncomplete, match=version_of(1)):   # a RepositoryError of its own: the pass happened, it is not a failure
        store.commit(document(version_of(0), "velho"), after, [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    assert store.read_document() == after and [r.version for r in store.passes()] == [version_of(0)]
    later = make_store(tmp_path)
    with later.lock():
        pass
    assert later.read_base() == "BASE1\n" and [r.version for r in later.passes()] == [version_of(0), version_of(1)]
    assert OLD_ITEM in (later.archive_dir / "2026-10.md").read_text()   # the archive entry stays


def test_version_names_lists_the_committed_sets_and_the_one_a_commit_left_unfinished(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, store = seeded
    assert store.version_names() == [version_of(0)]
    unfinished = make_store(tmp_path, Faults(fail_at="log", times=99))
    with pytest.raises(CommitIncomplete):
        unfinished.commit(store.read_document() or "", document(version_of(1), "novo"), [], "BASE1\n", record(1))
    assert [r.version for r in store.passes()] == [version_of(0)]          # no log line for it yet ...
    assert store.version_names() == [version_of(0), version_of(1)]         # ... but its files are there, so its name is taken
    assert make_store(tmp_path / "empty").version_names() == []


# --- the store's edge: a file system failure is a RepositoryError, never a raw OSError (the CLI reports those) -------------------

def test_a_lock_that_cannot_be_set_up_is_a_repository_error(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.root.mkdir(parents=True)
    store.curator_dir.write_text("a file where the folder should be")
    with pytest.raises(RepositoryError, match="could not be read or written"), store.lock():
        pytest.fail("the block must not run")


def test_a_reconcile_that_cannot_complete_is_a_repository_error_and_releases_the_lock(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, store = seeded
    with pytest.raises(CommitIncomplete):
        make_store(tmp_path, Faults(fail_at="base", times=99)).commit(
            store.read_document() or "", document(version_of(1), "novo"), [], "BASE1\n", record(1))
    stuck = make_store(tmp_path, Faults(fail_at="base", times=99))
    with pytest.raises(RepositoryError, match="disk full"), stuck.lock():   # rolling the set forward writes base.md again
        pytest.fail("the block must not run")
    with make_store(tmp_path).lock(wait=False) as free:   # the failed lock() let go of the file lock
        assert free is True
    assert store.read_base() == "BASE1\n" and [r.version for r in store.passes()] == [version_of(0), version_of(1)]


def test_what_the_callers_block_raises_inside_the_lock_is_not_translated(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="the caller's own"), make_store(tmp_path).lock():
        raise OSError(errno.EIO, "the caller's own failure")


@pytest.mark.parametrize("read", ["read_document", "read_base", "passes", "recent_archive"])
def test_a_read_that_hits_the_file_system_error_is_a_repository_error(tmp_path: Path, read: str) -> None:
    store = make_store(tmp_path)
    for path in (store.document, store.base_file, store.pass_log, store.archive_dir / "2026-10.md"):
        path.mkdir(parents=True)                                       # a folder where each file belongs: reading it fails
    call = {"recent_archive": lambda: store.recent_archive(10)}.get(read, getattr(store, read))
    with pytest.raises(RepositoryError, match="could not be read or written"):
        call()


# --- archive -----------------------------------------------------------------------------------------------------

def test_an_archive_entry_has_its_heading_the_text_and_the_link_definitions(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    when = datetime(2026, 10, 16, 9, 0)
    store.commit(SKELETON, document(version_of(0)), [(OLD_ITEM, "data passou (qui 15/10)")], None, record(0, ts=when))
    assert (store.archive_dir / "2026-10.md").read_text() == (
        "### 16/10/2026 — data passou (qui 15/10)\n"
        f"{OLD_ITEM}"
        f"[{LABEL}]: ../../recordings/{LABEL}/minutes.md\n\n")


def test_archive_entries_go_to_the_file_of_the_month_of_the_pass(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.commit(SKELETON, document(version_of(0)), [("- [ ] a\n", "duplicado")], None, record(0, ts=datetime(2026, 9, 30, 23, 0)))
    store.commit(document(version_of(0)), document(version_of(1)), [("- [ ] b\n", "concluído")], None, record(1, ts=datetime(2026, 10, 1, 8, 0)))
    assert sorted(p.name for p in store.archive_dir.iterdir()) == ["2026-09.md", "2026-10.md"]
    assert store.passes()[0].archive_file == "arquivo/2026-09.md" and store.passes()[1].archive_file == "arquivo/2026-10.md"


def test_recent_archive_gives_the_last_entries_with_their_heading_and_first_line(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.commit(SKELETON, document(version_of(0)), [("- [ ] a\n  - sub\n", "um")], None, record(0, ts=datetime(2026, 9, 30, 23, 0)))
    store.commit(document(version_of(0)), document(version_of(1)), [("- [ ] b\n", "dois"), ("- [ ] c\n", "três")], None,
                 record(1, ts=datetime(2026, 10, 1, 8, 0)))
    assert store.recent_archive(60) == ["### 30/09/2026 — um\n- [ ] a", "### 01/10/2026 — dois\n- [ ] b", "### 01/10/2026 — três\n- [ ] c"]
    assert store.recent_archive(2) == ["### 01/10/2026 — dois\n- [ ] b", "### 01/10/2026 — três\n- [ ] c"]
    assert store.recent_archive(0) == []


def test_truncate_archive_takes_back_a_pass_only_while_the_archive_is_as_the_pass_left_it(seeded: tuple[Path, FsActivityStore]) -> None:
    _, store = seeded
    archive = store.archive_dir / "2026-10.md"
    first = store.passes()[0]
    store.commit(document(version_of(0), "velho"), document(version_of(1), "novo"), [("- [ ] b\n", "dois")], None, record(1))
    second = store.passes()[1]
    assert second.archive_bytes_before == first.archive_bytes_after
    assert store.truncate_archive(second) is True and archive.stat().st_size == first.archive_bytes_after   # never below its own before
    assert store.truncate_archive(second) is False   # the archive is no longer the size the pass left
    assert archive.stat().st_size == first.archive_bytes_after
    append_text(archive, "### later\n")
    assert store.truncate_archive(first) is False and archive.read_text().endswith("### later\n")
    assert store.truncate_archive(record(9)) is True   # a pass that archived nothing has nothing to take back


def test_truncating_the_only_entries_removes_the_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.commit(SKELETON, document(version_of(0)), [("- [ ] a\n", "um")], None, record(0))
    assert (store.archive_dir / "2026-10.md").exists()
    assert store.truncate_archive(store.passes()[0]) is True
    assert not (store.archive_dir / "2026-10.md").exists()


# --- rotation ----------------------------------------------------------------------------------------------------

def test_after_keep_versions_plus_one_passes_only_the_newest_version_sets_remain(tmp_path: Path) -> None:
    store = make_store(tmp_path, keep_versions=3)
    previous = SKELETON
    for n in range(4):
        current = document(version_of(n), f"item {n}")
        store.commit(previous, current, [], f"BASE{n}\n", record(n))
        previous = current
    kept = sorted({p.name.partition("_")[0] for p in store.versions_dir.iterdir()})
    assert kept == [version_of(1), version_of(2), version_of(3)]
    assert len(list(store.versions_dir.iterdir())) == 3 * 5   # before, after, base, prevbase and pass.json of each kept set
    assert len(store.passes()) == 4   # the log is never rotated


def test_the_default_keeps_fifty_passes(tmp_path: Path) -> None:
    assert FsActivityStore(tmp_path, FMT).keep_versions == 50


# --- the pass log --------------------------------------------------------------------------------------------------

def test_passes_round_trip_every_field(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    full = record(0, kind=PassKind.UNDO, meetings=("a", "b"), retried=True, retried_by_kind={"not found": 2}, unaccounted_refs=("1.a1",),
                  during_edits="@@ x", undoes="20261018-090000", error="boom", carried_edits="@@ y")
    store.commit(SKELETON, document(version_of(0)), [], None, full)
    assert store.passes() == [full]


def test_a_torn_last_line_of_the_log_is_absent(seeded: tuple[Path, FsActivityStore]) -> None:   # UT-125
    tmp_path, store = seeded
    complete = store.pass_log.read_text()
    half = json.dumps({"ts": NOW.isoformat(), "kind": "meeting", "meetings": ["m"]})[:30]
    with store.pass_log.open("a") as handle:
        handle.write(half)
    assert [r.version for r in store.passes()] == [version_of(0)]
    assert store.pass_log.read_text() == complete + half
    # the version files of that pass exist but its line does not: for reconcile it is uncommitted
    stop = Faults(fail_at="log", error=HardStop())
    crashed = make_store(tmp_path, stop)
    with pytest.raises(HardStop):
        crashed.commit(document(version_of(0), "velho"), document(version_of(1), "novo"), [], "BASE1\n", record(1))
    assert [r.version for r in crashed.passes()] == [version_of(0)]
    assert (crashed.versions_dir / f"{version_of(1)}_pass.json").exists()


def test_a_torn_line_is_dropped_when_reconcile_completes_the_pass(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, _ = seeded

    def torn_append(path: Path, text: str) -> None:
        if label_of(path) == "log":
            append_text(path, text[:25])
            raise HardStop()
        append_text(path, text)

    store = FsActivityStore(tmp_path / "data", FMT, write=atomic_write, append=torn_append)
    after = document(version_of(1), "novo")
    with pytest.raises(HardStop):
        store.commit(document(version_of(0), "velho"), after, [], "BASE1\n", record(1))
    assert [r.version for r in store.passes()] == [version_of(0)]
    later = make_store(tmp_path)
    with later.lock():
        pass
    assert [r.version for r in later.passes()] == [version_of(0), version_of(1)]
    assert later.pass_log.read_text().count("\n") == 2 and later.read_base() == "BASE1\n"


def test_a_whole_last_line_with_no_newline_is_kept_and_the_next_line_starts_on_its_own(seeded: tuple[Path, FsActivityStore]) -> None:
    _, store = seeded
    store.pass_log.write_text(store.pass_log.read_text().rstrip("\n"))
    assert [r.version for r in store.passes()] == [version_of(0)]
    store.commit(document(version_of(0), "velho"), document(version_of(1), "novo"), [], "BASE1\n", record(1))
    assert [r.version for r in store.passes()] == [version_of(0), version_of(1)]


def test_a_damaged_line_before_the_last_is_a_repository_error(seeded: tuple[Path, FsActivityStore]) -> None:
    _, store = seeded
    store.pass_log.write_text("not json\n" + store.pass_log.read_text())
    with pytest.raises(RepositoryError, match="line 1"):
        store.passes()


# --- hard stops: reconciled at the next lock ------------------------------------------------------------------------

def test_a_stop_after_the_archive_append_and_before_the_replace_is_rolled_back_at_the_next_lock(seeded: tuple[Path, FsActivityStore]) -> None:   # IT-014
    tmp_path, _ = seeded
    store = make_store(tmp_path, Faults(fail_at="document", error=HardStop()))
    before = snapshot(store)
    with pytest.raises(HardStop):
        store.commit(document(version_of(0), "velho"), document(version_of(1), "novo"), [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    stopped = snapshot(store)
    assert stopped["archives"] != before["archives"]            # the surplus entry is there
    assert f"{version_of(1)}_after.md" in stopped["versions"]    # and so are the version files
    assert stopped["document"] == before["document"] and stopped["base"] == before["base"] and stopped["log"] == before["log"]

    later = make_store(tmp_path)
    with later.lock() as got:
        assert got is True
        assert snapshot(later) == before                        # rolled back on entry, under the lock


def test_a_stop_before_the_replace_followed_by_a_user_edit_still_rolls_back(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, _ = seeded
    store = make_store(tmp_path, Faults(fail_at="document", error=HardStop()))
    before = snapshot(store)
    with pytest.raises(HardStop):
        store.commit(document(version_of(0), "velho"), document(version_of(1), "novo"), [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    edited = document(version_of(0), "velho", "linha do usuário")   # neither `_before` nor `_after`, the old stamp
    store.path().write_text(edited)
    later = make_store(tmp_path)
    with later.lock():
        pass
    assert {**snapshot(later), "document": before["document"]} == before and later.read_document() == edited


@pytest.mark.parametrize("edit", [False, True])
def test_a_stop_after_the_replace_is_rolled_forward_at_the_next_lock(seeded: tuple[Path, FsActivityStore], edit: bool) -> None:
    tmp_path, _ = seeded
    store = make_store(tmp_path, Faults(fail_at="base", error=HardStop()))
    after = document(version_of(1), "novo")
    with pytest.raises(HardStop):
        store.commit(document(version_of(0), "velho"), after, [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    assert store.read_base() == "BASE0\n" and len(store.passes()) == 1
    shown = after + "linha do usuário\n" if edit else after   # an edit that leaves the closing marker alone
    store.path().write_text(shown)
    later = make_store(tmp_path)
    with later.lock():
        assert later.read_base() == "BASE1\n"
        assert [r.version for r in later.passes()] == [version_of(0), version_of(1)]
    assert later.read_document() == shown
    assert (later.archive_dir / "2026-10.md").read_text().count(OLD_ITEM) == 2   # the entries of both passes are kept


def test_rolling_forward_a_set_with_no_base_file_deletes_base_md(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, _ = seeded
    store = make_store(tmp_path, Faults(fail_at="log", error=HardStop()))
    with pytest.raises(HardStop):
        store.commit(document(version_of(0), "velho"), SKELETON, [], None, record(1))
    store.base_file.write_text("BASE0\n")   # the stop came before the step that deletes base.md
    assert not (store.versions_dir / f"{version_of(1)}_base.md").exists()
    later = make_store(tmp_path)
    with later.lock():
        pass
    assert later.read_base() is None and not later.base_file.exists()
    assert [r.version for r in later.passes()] == [version_of(0), version_of(1)]


def test_a_document_with_no_stamp_is_never_counted_as_replaced(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, _ = seeded
    unstamped = document(version_of(1), "novo").replace(f" {version_of(1)}", "")
    assert box_stamp(FMT, unstamped) is None
    store = make_store(tmp_path, Faults(fail_at="base", error=HardStop()))
    before = snapshot(store)
    with pytest.raises(HardStop):
        # `_after` has no stamp either and the document written is `_after`: both None, which still rolls back
        store.commit(document(version_of(0), "velho"), unstamped, [(OLD_ITEM, "concluído")], "BASE1\n", record(1))
    later = make_store(tmp_path)
    with later.lock():
        pass
    assert {**snapshot(later), "document": before["document"]} == before and later.read_document() == unstamped


def test_a_skeleton_after_matches_only_a_document_carrying_the_skeleton_stamp(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, _ = seeded
    store = make_store(tmp_path, Faults(fail_at="log", error=HardStop()))
    with pytest.raises(HardStop):
        store.commit(document(version_of(0), "velho"), SKELETON, [], "BASE1\n", record(1))   # the document is now the skeleton
    assert box_stamp(FMT, store.read_document() or "") == FMT.skeleton_stamp
    store.base_file.write_text("BASE0\n")   # the stop came before the step that writes base.md
    later = make_store(tmp_path)
    with later.lock():
        pass
    assert later.read_base() == "BASE1\n" and [r.version for r in later.passes()][-1] == version_of(1)   # rolled forward

    again = make_store(tmp_path, Faults(fail_at="base", error=HardStop()))
    with pytest.raises(HardStop):
        again.commit(SKELETON, SKELETON, [], "B\n", record(2))
    again.path().write_text(document(version_of(0), "velho"))   # a stamp other than the skeleton's
    final = make_store(tmp_path)
    with final.lock():
        pass
    assert [r.version for r in final.passes()][-1] == version_of(1) and final.read_base() == "BASE1\n"   # pass 2 was rolled back


def test_the_lock_is_held_while_an_interrupted_commit_is_reconciled(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, _ = seeded
    store = make_store(tmp_path, Faults(fail_at="document", error=HardStop()))
    with pytest.raises(HardStop):
        store.commit(document(version_of(0), "velho"), document(version_of(1), "novo"), [], "BASE1\n", record(1))
    holder, waiter = make_store(tmp_path), make_store(tmp_path)
    with holder.lock():
        assert list(holder.versions_dir.glob(f"{version_of(1)}_*")) == []   # reconciled before the caller gets the lock
        with waiter.lock(wait=False) as got:
            assert got is False


def test_log_pass_appends_a_record_and_changes_nothing_else(seeded: tuple[Path, FsActivityStore]) -> None:
    tmp_path, store = seeded
    before = snapshot(store)
    skipped, failed = record(1, kind=PassKind.SKIPPED_EMPTY, summary=""), record(2, kind=PassKind.FAILED, error="timed out")
    store.log_pass(skipped)
    store.log_pass(failed)
    after = snapshot(store)
    assert {key: value for key, value in after.items() if key != "log"} == {key: value for key, value in before.items() if key != "log"}
    assert store.passes()[-2:] == [skipped, failed] and len(store.passes()) == 3
    with store.lock():                                                      # no version set without a record: nothing to reconcile
        pass
    assert snapshot(store) == after


def test_log_pass_completes_a_torn_last_line_first(seeded: tuple[Path, FsActivityStore]) -> None:
    _, store = seeded
    with store.pass_log.open("a") as handle:
        handle.write('{"torn": ')
    store.log_pass(record(1, kind=PassKind.FAILED, error="x"))
    assert [r.kind for r in store.passes()] == [PassKind.MEETING, PassKind.FAILED]

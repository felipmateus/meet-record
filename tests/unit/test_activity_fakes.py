"""The fakes of the activities ports behave like what they stand for (enough for the use-case tests of tasks 5 and 9)."""
from __future__ import annotations

from datetime import datetime

from teams_recorder.domain import CuratorInput, CuratorOutput, Meeting, Op, OpKind, PassKind, PassRecord
from tests.fakes import FakeActivityCurator, InMemoryActivityStore, InMemoryMeetingRepository

NOW = datetime(2026, 10, 19, 10, 12)


def record(version: str = "v1") -> PassRecord:
    return PassRecord(ts=NOW, kind=PassKind.MEETING, meetings=("m",), ops_applied=0, retried=False, retried_by_kind={}, unaccounted_refs=(),
                      ignored=0, user_removed=0, box_rescued=0, during_edits="", summary="", version=version, archive_file=None,
                      archive_bytes_before=None, archive_bytes_after=None, carried_edits="", undoes=None, doc_chars=0, error=None)


def output(summary: str) -> CuratorOutput:
    return CuratorOutput(ops=[], user_removed=[], focus=[], summary=summary, notify=False, ignored=[])


def data() -> CuratorInput:
    return CuratorInput(document="d", meetings=[], calendar="", user_edits="", box_lines=[], recent_archive=[], last_summary=None, today=NOW,
                        user_name="u")


def test_the_store_yields_false_only_when_busy_and_not_waiting() -> None:
    store = InMemoryActivityStore(busy=True)
    with store.lock(wait=False) as got:
        assert got is False
    with store.lock() as got:
        assert got is True
    assert store.locks == [False, True]


def test_the_store_records_commits_versions_and_the_archive() -> None:
    store = InMemoryActivityStore(document="old", base="b0")
    store.commit("old", "new", [("- [ ] x", "concluído")], "b1", record())
    assert (store.document, store.base) == ("new", "b1")
    assert store.version("v1") == ("old", "new", "b1", "b0")
    assert store.recent_archive(5) == ["### concluído\n- [ ] x"]
    saved = store.passes()[0]
    assert saved.archive_bytes_before == 0 and saved.archive_bytes_after and store.commits[0][3] == "b1"
    assert store.truncate_archive(saved) is True and store.archive == ""
    store.fail_commit = RuntimeError("boom")
    try:
        store.commit("new", "x", [], None, record("v2"))
    except RuntimeError:
        pass
    assert store.document == "new" and len(store.passes()) == 1


def test_the_store_logs_a_pass_that_changed_nothing_without_a_commit() -> None:
    store = InMemoryActivityStore(document="d")
    failed = record("v1")
    store.log_pass(failed)
    assert store.passes() == store.logged == [failed] and store.commits == [] and store.document == "d"
    store.fail_log = OSError("disk full")
    try:
        store.log_pass(record("v2"))
    except OSError:
        pass
    assert len(store.passes()) == 1


def test_the_curator_returns_scripted_outputs_and_runs_the_hook_inside_the_call() -> None:
    seen: list[str] = []
    curator = FakeActivityCurator([output("one"), output("two")], repairs=[[Op(OpKind.REPLACE, "a", "b")]], during_call=lambda: seen.append("during"))
    assert [curator.curate(data()).summary, curator.curate(data()).summary, curator.curate(data()).summary] == ["one", "two", "two"]
    assert curator.repair(data(), "cur", []) == [Op(OpKind.REPLACE, "a", "b")] and curator.repair(data(), "cur", []) == []
    assert len(curator.inputs) == 3 and len(curator.repair_calls) == 2 and seen == ["during"] * 5


def test_the_repository_fake_keeps_the_curation_error_apart_from_the_meeting_error() -> None:
    repo = InMemoryMeetingRepository()
    meeting = Meeting.start(NOW, pid=1)
    repo.seed(meeting)
    assert repo.curation_error(meeting.id) is None
    repo.mark_curation_failed(meeting.id, "bad")
    assert repo.curation_error(meeting.id) == "bad" and "curation_error.txt" in repo.files(meeting.id) and "error.txt" not in repo.files(meeting.id)
    repo.clear_curation_failed(meeting.id)
    assert repo.curation_error(meeting.id) is None and "curation_error.txt" not in repo.files(meeting.id)

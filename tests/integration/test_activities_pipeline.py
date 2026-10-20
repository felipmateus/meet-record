"""The pipeline's hook to the activities document, on files: a meeting that reaches `analyzed` updates the document (IT-001), a
failing curator leaves it `analyzed` with `curation_error.txt` and no `error.txt` (IT-002), and the real `ClaudeCurator` through
the scripted Claude Code CLI repairs one edit and commits (IT-008)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.activities_fs import FsActivityStore
from teams_recorder.adapters.outbound.curator_claude import ClaudeCurator
from teams_recorder.adapters.outbound.llm_transport import ClaudeCodeTransport
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.application.pipeline import Pipeline
from teams_recorder.application.use_cases import AnalyzeMeeting, StopRecording, TranscribeMeeting
from teams_recorder.application.use_cases.activities import CurateMeetings
from teams_recorder.constants import Files
from teams_recorder.domain import Meeting, MeetingStatus, PassKind, derive_status
from teams_recorder.domain.status import AUDIO, CURATION_ERROR, ERROR, TRANSCRIPT_JSON
from teams_recorder.messages import Err, Notify
from tests.fakes import FakeActivityCurator, FakeAnalyzer, FakeClock, FakeMicCapture, FakeMixer, FakeNotifier, FakeProcessCapture, FakeTranscriber
from tests.fixtures.curation import ACTIONS, FMT, NOW, answer, insert, transcript

FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_claude_cli.py"
STARTED = datetime(2026, 10, 19, 9, 30)


class World:
    """A meeting transcribed on disk, the pipeline with the curator hooked to it as the daemon's worker does, and the store."""

    def __init__(self, tmp_path: Path, curator: object) -> None:
        self.data = tmp_path / "data"
        self.repo = FsMeetingRepository(self.data)
        self.store = FsActivityStore(self.data, FMT)
        self.notifier = FakeNotifier()
        self.clock = FakeClock(NOW)
        self.curate = CurateMeetings(self.repo, self.store, curator, self.notifier, self.clock)   # type: ignore[arg-type]
        stop = StopRecording(self.repo, FakeProcessCapture(), FakeMicCapture(), FakeMixer(), self.notifier, self.clock)
        self.pipeline = Pipeline(self.repo, self.notifier, stop, TranscribeMeeting(self.repo, FakeTranscriber()),
                                 AnalyzeMeeting(self.repo, FakeAnalyzer()), self.after_analysis)
        self.analyzed: list[str] = []

    def after_analysis(self, meeting_id: str) -> None:
        self.analyzed.append(meeting_id)
        self.curate.execute([meeting_id])

    def transcribed_meeting(self) -> str:
        meeting = Meeting.start(STARTED, title="Daily")
        self.repo.create(meeting)
        self.repo.save_transcript(meeting.id, transcript())
        assert derive_status(self.repo.files(meeting.id)) == MeetingStatus.TRANSCRIBED
        return meeting.id


def item(mid: str) -> str:
    return f"- [ ] **Send the report** · [Daily 19/10][{mid}]"


def test_it001_a_meeting_that_reaches_analyzed_updates_the_document_with_the_curators_lines(tmp_path: Path) -> None:
    mid = Meeting.start(STARTED, title="Daily").id
    curator = FakeActivityCurator([answer([insert(item(mid))], summary="1 ação nova", focus=["**Send the report** hoje"])])
    world = World(tmp_path, curator)
    assert world.transcribed_meeting() == mid

    status = world.pipeline.process(mid)

    document = world.store.read_document()
    assert status == MeetingStatus.ANALYZED and world.analyzed == [mid]
    assert document is not None and world.store.path().is_file()
    assert f"{ACTIONS}\n{item(mid)}\n" in document                                    # the curator's line, under its heading
    assert FMT.box_start in document and "**Send the report** hoje" in document and FMT.updated_label in document   # the box, written from the focus
    assert f"{FMT.links_start}\n[{mid}]: ../recordings/{mid}/minutes.md\n{FMT.links_end}" in document   # the link block, written by code
    [record] = world.store.passes()
    assert record.kind == PassKind.MEETING and record.meetings == (mid,) and record.ops_applied == 1
    assert ERROR not in world.repo.files(mid) and CURATION_ERROR not in world.repo.files(mid)
    assert [r.meetings for r in world.store.passes()] == [(mid,)] and len(curator.inputs) == 1


def test_it002_a_failing_curator_leaves_the_meeting_analyzed_with_curation_error_txt_and_no_error_txt(tmp_path: Path) -> None:
    world = World(tmp_path, FakeActivityCurator(fail=RuntimeError("Claude Code timed out after 900 s")))
    mid = world.transcribed_meeting()

    status = world.pipeline.process(mid)

    files = world.repo.files(mid)
    assert status == MeetingStatus.ANALYZED and derive_status(files) == MeetingStatus.ANALYZED
    assert ERROR not in files and CURATION_ERROR in files
    assert world.repo.curation_error(mid) == Err.CURATION_FAILED.format(reason="Claude Code timed out after 900 s")
    assert world.store.read_document() is None and [r.kind for r in world.store.passes()] == [PassKind.FAILED]
    assert (Notify.ACTIVITIES_FAILED, Notify.ACTIVITIES_FAILED_BODY.format(
        title="Daily", meeting_id=mid, error="Claude Code timed out after 900 s")) in world.notifier.messages
    assert TRANSCRIPT_JSON in files and AUDIO not in files                                 # what the pipeline made is untouched


def test_it002_a_hook_that_raises_is_not_an_error_of_the_meeting(tmp_path: Path) -> None:
    world = World(tmp_path, FakeActivityCurator())
    mid = world.transcribed_meeting()

    def broken(meeting_id: str) -> None:
        raise RuntimeError("the queue is gone")

    world.pipeline.after_analysis = broken
    assert world.pipeline.process(mid) == MeetingStatus.ANALYZED
    assert ERROR not in world.repo.files(mid) and CURATION_ERROR not in world.repo.files(mid)


class ScriptedCli(ClaudeCodeTransport):
    """Claude Code's transport with `claude` replaced by `tests/fixtures/fake_claude_cli.py`."""

    def command(self, system, schema):
        return [sys.executable, str(FAKE)] + super().command(system, schema)[1:]


def test_it008_claude_curator_through_the_fake_cli_repairs_one_edit_and_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mid = Meeting.start(STARTED, title="Daily").id
    line = item(mid)
    wrong = {"op": "insert_after", "target": "## Seção que não existe", "text": line, "reason": None, "anchor": None, "refs": ["1.a1"]}
    right = {"op": "insert_after", "target": ACTIONS, "text": line, "reason": None, "anchor": None, "refs": ["1.a1"]}
    first = {"ops": [wrong], "user_removed": [], "focus": ["**Send the report** hoje"], "summary": "1 ação nova", "notify": False, "ignored": []}
    script = tmp_path / "script.json"
    script.write_text(json.dumps([first, {"ops": [right]}], ensure_ascii=False), encoding="utf-8")
    record = tmp_path / "record.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    data = tmp_path / "data"
    usage = data / Files.LOG_DIR / Files.LLM_USAGE_LOG
    curator = ClaudeCurator(ScriptedCli(claude_bin=sys.executable, usage_log=usage), system_prompt="SYS")
    world = World(tmp_path, curator)
    assert world.transcribed_meeting() == mid

    world.pipeline.process(mid)

    tags = [json.loads(entry)["tag"] for entry in usage.read_text(encoding="utf-8").splitlines()]
    assert tags == [f"curate:{mid}", f"curate-repair:{mid}"]                                # one call each, nothing else
    document = world.store.read_document()
    assert document is not None and f"{ACTIONS}\n{line}\n" in document
    [committed] = world.store.passes()
    assert committed.kind == PassKind.MEETING and committed.retried and committed.ops_applied == 1 and committed.retried_by_kind == {"insert_after": 1}
    assert len(record.read_text(encoding="utf-8").splitlines()) == 2                        # the CLI saw the pass and the repair
    assert derive_status(world.repo.files(mid)) == MeetingStatus.ANALYZED and CURATION_ERROR not in world.repo.files(mid)

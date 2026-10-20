"""`trec stories` through Typer's runner with the real file repository and the real file store in a temporary project, a fake story
writer and a scripted `backlog` (IT-009, IT-017, E2E-004, UT-111). Nothing here reaches a model, the user's board or the real data dir."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from teams_recorder.adapters.inbound import cli
from teams_recorder.adapters.inbound.cli import app
from teams_recorder.adapters.outbound.activities_fs import FsActivityStore
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.config import ENV_PROJECT_DIR
from teams_recorder.constants import Activities
from teams_recorder.domain import StoryDrafts, UserStory
from teams_recorder.messages import ActivityDoc, Cli
from tests.fakes import FakeClock, FakeNotifier, FakeStoryWriter
from tests.fixtures.curation import FMT, NOW, seed
from tests.integration.test_activities_store import HOLD

runner = CliRunner()
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "activities" / "atividades.md"
FAKE_BACKLOG = Path(__file__).resolve().parents[1] / "fixtures" / "fake_backlog_cli.py"
BOARD_CONFIG = 'statuses: ["Triagem", "To Do", "In Progress", "Done"]\nauto_commit: false\nremote_operations: false\n'
TAG = ActivityDoc.STORY_TAG
ESTIMATE = "- [ ] **Estimar a integração de estoque** — p/ Rafael · seg 19/10 · [Planejamento 15/10][2026-10-15_14-00-07]"
REVIEW = ("- [ ] **Revisar o PR do mapeamento de centros** — p/ Diego · ⚠️ a confirmar: não ficou claro se o pedido era para você · "
          "[Daily 16/10][2026-10-16_09-30-11]")
LINK = ActivityDoc.STORY_LINK.format(date="19/10", target="../plans/2026-10-19.stories.md")


def _project(tmp_path: Path, monkeypatch, *, publish: bool = False) -> Path:
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    (tmp_path / "guide.md").write_text("# Guia\n")
    config = '[stories]\nguide = "guide.md"\n'
    if publish:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "backlog").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_BACKLOG}" "$@"\n')
        (bin_dir / "backlog").chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_BACKLOG_LOG", str(tmp_path / "backlog-calls.jsonl"))
        (tmp_path / "backlog").mkdir()
        (tmp_path / "backlog" / "config.yml").write_text(BOARD_CONFIG)
        config += 'destinations = ["backlog-md"]\npublish = true\n[stories.backlog_md]\nproject_dir = "."\n'
    (tmp_path / "config.toml").write_text(config)
    return tmp_path


def _wire(monkeypatch, writer: FakeStoryWriter) -> FakeNotifier:
    notifier = FakeNotifier()
    build = cli.build_container
    fakes: dict[str, Any] = {"clock": FakeClock(NOW), "notifier": notifier, "story_writer": writer}
    monkeypatch.setattr(cli, "build_container", lambda settings, **kw: replace(build(settings, **kw), **fakes))
    return notifier


def _store(project: Path) -> FsActivityStore:
    return FsActivityStore(project / "data", FMT, Activities.KEEP_VERSIONS)


def _write_document(project: Path, text: str) -> FsActivityStore:
    store = _store(project)
    store.path().parent.mkdir(parents=True, exist_ok=True)
    store.path().write_text(text, encoding="utf-8")
    store.base_file.parent.mkdir(parents=True, exist_ok=True)
    store.base_file.write_text(text, encoding="utf-8")
    return store


def _tagged(*lines: str) -> str:
    """The E2E-001 document with `#história` written on these lines (and nothing else changed)."""
    text = FIXTURE.read_text(encoding="utf-8")
    for line in lines:
        assert line in text
        text = text.replace(line, f"{line} {TAG}", 1)
    return text


def _seed_meetings(project: Path) -> None:
    repo = FsMeetingRepository(project / "data")
    for started in (datetime(2026, 10, 15, 14, 0, 7), datetime(2026, 10, 16, 9, 30, 11)):
        seed(repo, started)


def test_stories_drafts_a_tagged_line_of_the_document_and_replaces_its_tag(tmp_path: Path, monkeypatch) -> None:       # IT-009, E2E-004
    project = _project(tmp_path, monkeypatch)
    _seed_meetings(project)
    store = _write_document(project, _tagged(ESTIMATE, REVIEW))
    writer = FakeStoryWriter(duplicates={"Revisar o PR": "s-old"})
    FsMeetingRepository(project / "data").save_story_drafts(
        StoryDrafts(NOW.date() - timedelta(days=5), [UserStory("Mapeamento de centros", "n", id="s-old")]), "#\n")
    _wire(monkeypatch, writer)

    result = runner.invoke(app, ["stories"])

    assert result.exit_code == 0, result.output
    story = FsMeetingRepository(project / "data").load_story_drafts(NOW.date()).stories[0]
    assert result.output == (
        "Drafting 2 tagged items… ok (1 story, 1 already exists)\n"
        f"  {story.title}\n"
        '  Skipped: Revisar o PR do mapeamento de centros — already exists ("Mapeamento de centros")\n'
        "Drafts: data/plans/2026-10-19.stories.md\n"
    )
    assert [b.lines[0] for b in writer.calls[0][1]] == [f"{ESTIMATE} {TAG}", f"{REVIEW} {TAG}"]
    drafts = (project / "data" / "plans" / "2026-10-19.stories.md").read_text(encoding="utf-8")
    assert f"> {ESTIMATE} {TAG}" in drafts and "[Planejamento 15/10][2026-10-15_14-00-07]" in drafts
    for text in (store.path().read_text(encoding="utf-8"), store.base_file.read_text(encoding="utf-8")):         # document and base.md
        assert f"{ESTIMATE} {LINK}" in text and f'{REVIEW} {ActivityDoc.STORY_EXISTS.format(title="Mapeamento de centros")}' in text
        assert TAG not in text
    assert text.replace(f"{ESTIMATE} {LINK}", ESTIMATE).replace(f'{REVIEW} {ActivityDoc.STORY_EXISTS.format(title="Mapeamento de centros")}', REVIEW) \
        == FIXTURE.read_text(encoding="utf-8")                                                                   # nothing else was touched
    assert not (project / "data" / "log" / "activities.jsonl").exists()                                          # a tag replacement is not a pass

    again = runner.invoke(app, ["stories"])
    assert again.exit_code == 0 and again.output == f"Nothing tagged {TAG} in data/activities/atividades.md.\n" and len(writer.calls) == 1


def test_nothing_tagged_and_no_document(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _wire(monkeypatch, FakeStoryWriter())
    missing = runner.invoke(app, ["stories"])
    assert missing.exit_code == 1 and "No activities document yet: data/activities/atividades.md" in missing.output
    _write_document(project, FIXTURE.read_text(encoding="utf-8"))
    empty = runner.invoke(app, ["stories"])
    assert empty.exit_code == 0 and empty.output == f"Nothing tagged {TAG} in data/activities/atividades.md.\n"
    assert runner.invoke(app, ["stories", "--date", "2026-10-19"]).exit_code == 2                                  # --date is gone


def test_a_skipped_block_keeps_its_tag_and_is_printed_with_the_writers_reason(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _seed_meetings(project)
    store = _write_document(project, _tagged(REVIEW))
    _wire(monkeypatch, FakeStoryWriter(skips={"Revisar": "é uma revisão"}))
    result = runner.invoke(app, ["stories"])
    assert result.exit_code == 0
    assert "Drafting 1 tagged item… ok (1 skipped)\n  Skipped: Revisar o PR do mapeamento de centros — é uma revisão\n" in result.output
    assert f"{REVIEW} {TAG}" in store.path().read_text(encoding="utf-8")


def test_a_writer_failure_exits_1_notifies_and_leaves_the_document_alone(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _seed_meetings(project)
    text = _tagged(ESTIMATE)
    store = _write_document(project, text)
    notifier = _wire(monkeypatch, FakeStoryWriter(fail=True))
    result = runner.invoke(app, ["stories"])
    assert result.exit_code == 1 and "Drafting 1 tagged item… FAILED: model is down" in result.output
    assert store.path().read_text(encoding="utf-8") == text and not list((project / "data" / "plans").glob("*.stories.*"))
    assert notifier.messages[-1][0] == "User story drafts failed"


# --- IT-017: the curator holds the lock --------------------------------------------------------------------------------------
def test_stories_never_waits_for_a_curator_pass_and_a_drafted_line_is_never_drafted_again(tmp_path: Path, monkeypatch) -> None:    # IT-017
    project = _project(tmp_path, monkeypatch)
    _seed_meetings(project)
    store = _write_document(project, _tagged(ESTIMATE))
    writer = FakeStoryWriter()
    _wire(monkeypatch, writer)
    store.curator_dir.mkdir(parents=True, exist_ok=True)
    ready = tmp_path / "ready"
    child = subprocess.Popen([sys.executable, "-c", HOLD, str(store.lock_file), str(ready)], stdin=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 120
        while not ready.exists():
            assert child.poll() is None and time.monotonic() < deadline, "the child never took the lock"
            time.sleep(0.05)
        started = time.monotonic()
        first = runner.invoke(app, ["stories"])
        assert time.monotonic() - started < 1.0 + 0     # returns at once (the one non-blocking try), not after the pass
        assert first.exit_code == 0, first.output
        assert Cli.STORIES_DEFERRED in first.output and "Drafts: data/plans/2026-10-19.stories.md" in first.output
        assert f"{ESTIMATE} {TAG}" in store.path().read_text(encoding="utf-8")

        second = runner.invoke(app, ["stories"])
        assert second.exit_code == 0 and Cli.STORIES_DEFERRED in second.output and "Drafts:" not in second.output
        assert len(writer.calls) == 1 and len(FsMeetingRepository(project / "data").load_story_drafts(NOW.date()).stories) == 1
    finally:
        assert child.stdin is not None
        child.stdin.write("\n")
        child.stdin.close()
        child.wait(timeout=60)

    third = runner.invoke(app, ["stories"])

    assert third.exit_code == 0 and third.output == "Replaced 1 tag in data/activities/atividades.md.\n"
    assert len(writer.calls) == 1
    for text in (store.path().read_text(encoding="utf-8"), store.base_file.read_text(encoding="utf-8")):
        assert f"{ESTIMATE} {LINK}" in text and TAG not in text


# --- UT-111: [stories] publish ------------------------------------------------------------------------------------------------
def test_publish_true_sends_the_drafts_right_after_drafting(tmp_path: Path, monkeypatch) -> None:                        # UT-111
    project = _project(tmp_path, monkeypatch, publish=True)
    _seed_meetings(project)
    _write_document(project, _tagged(ESTIMATE))
    _wire(monkeypatch, FakeStoryWriter())
    result = runner.invoke(app, ["stories"])
    assert result.exit_code == 0, result.output
    assert Cli.PUBLISHED_LINE.format(title="Story for " + f"{ESTIMATE} {TAG}".strip(), destination="backlog-md", ref="TASK-1") in result.output
    assert len((tmp_path / "backlog-calls.jsonl").read_text().splitlines()) == 1
    nothing = runner.invoke(app, ["stories"])                                   # nothing tagged now: nothing drafted, nothing published
    assert nothing.exit_code == 0 and len((tmp_path / "backlog-calls.jsonl").read_text().splitlines()) == 1


def test_publish_false_leaves_the_drafts_on_disk_only(tmp_path: Path, monkeypatch) -> None:                              # UT-111
    project = _project(tmp_path, monkeypatch)
    _seed_meetings(project)
    _write_document(project, _tagged(ESTIMATE))
    _wire(monkeypatch, FakeStoryWriter())
    result = runner.invoke(app, ["stories"])
    assert result.exit_code == 0 and "TASK-" not in result.output and Cli.PUBLISHING.format(day="2026-10-19") not in result.output

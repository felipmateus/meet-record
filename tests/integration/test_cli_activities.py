"""`trec activities`, `trec activities curate` and the curation step of `trec analyze` through Typer's runner: fakes for the model and
the notifier, the real file repository and the real file store in a temporary project (UT-080 to UT-086, UT-088, UT-089, E2E-001,
E2E-002). Nothing here reaches a real model, the real data dir or the real launchd."""
from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from teams_recorder.adapters.inbound import cli
from teams_recorder.adapters.inbound.cli import _open_document, app
from teams_recorder.adapters.outbound.activities_fs import FsActivityStore
from teams_recorder.adapters.outbound.curator_claude import CuratorOut
from teams_recorder.adapters.outbound.llm_claude import AnalysisOut, ClaudeAnalyzer
from teams_recorder.adapters.outbound.curator_claude import ClaudeCurator
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.config import ENV_PROJECT_DIR
from teams_recorder.application.use_cases.activities import CurateMeetings
from teams_recorder.adapters.inbound.daemon import Daemon
from teams_recorder.constants import Activities, Files
from teams_recorder.domain import Action, Analysis, AnalysisError, CommitIncomplete, CuratorInput, Meeting, PassKind
from teams_recorder.domain.status import CURATION_ERROR
from teams_recorder.messages import ActivityDoc, Cli, Notify
from tests.fakes import FakeActivityCurator, FakeCallDetector, FakeClock, FakeMicCapture, FakeNotifier, FakeProcessCapture, InMemoryActivityStore
from tests.fixtures.curation import ACTIONS, FMT, NOW, answer, archive, build, insert, rec, seed, transcript
from tests.unit.test_curator_worker import CuratingContainer, step_soon

runner = CliRunner()


# --- the project -----------------------------------------------------------------------------------------------------------
def _project(tmp_path: Path, monkeypatch, *, key: bool = True, config: str = "") -> Path:
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    if config:
        (tmp_path / "config.toml").write_text(config)
    return tmp_path


def _wire(monkeypatch, **fields: Any) -> tuple[FakeClock, FakeNotifier]:
    """`trec` with these fakes in the container it builds (the clock and the notifier are always fakes)."""
    clock, notifier = FakeClock(NOW), FakeNotifier()
    build = cli.build_container
    fakes: dict[str, Any] = {"clock": clock, "notifier": notifier, **fields}
    monkeypatch.setattr(cli, "build_container", lambda settings, **kw: replace(build(settings, **kw), **fakes))
    return clock, notifier


def _repo(project: Path) -> FsMeetingRepository:
    return FsMeetingRepository(project / "data")


def _store(project: Path) -> FsActivityStore:
    return FsActivityStore(project / "data", FMT, Activities.KEEP_VERSIONS)


def _document(project: Path) -> str:
    return _store(project).path().read_text(encoding="utf-8")


class _Analyzer:
    """Analyzes every meeting with one action of the user's, titled after the meeting; fails for the ids in `failing`."""

    def __init__(self, failing: tuple[str, ...] = ()) -> None:
        self.failing = failing
        self.calls: list[str] = []

    def analyze(self, transcript: Any, meeting: Meeting) -> Analysis:
        self.calls.append(meeting.id)
        if meeting.id in self.failing:
            raise AnalysisError("the model refused")
        return Analysis(meeting_id="", summary="Resumo.", title=meeting.title or "Daily",
                        my_actions=[Action("Enviar o cronograma", "usuário", meeting.id, due=date(2026, 10, 20), at="00:03:00")])


class _CuratorFailingFor(FakeActivityCurator):
    """Fails when the pass holds one of `ids` (a batch with it fails, and so does the meeting alone)."""

    def __init__(self, ids: tuple[str, ...], reason: str, outputs=None) -> None:
        super().__init__(outputs)
        self.ids, self.reason = ids, reason

    def curate(self, data: CuratorInput):
        if any(context.meeting_id in self.ids for context in data.meetings):
            self.inputs.append(data)
            raise AnalysisError(self.reason)
        return super().curate(data)


def _transcribed(repo: FsMeetingRepository, started: datetime, title: str = "Daily") -> str:
    meeting = Meeting.start(started, title=title)
    repo.create(meeting)
    repo.save_transcript(meeting.id, transcript())
    return meeting.id


# --- trec activities curate <id>: errors (UT-080) ---------------------------------------------------------------------------
def test_curate_refuses_a_meeting_that_is_not_analyzed(tmp_path: Path, monkeypatch) -> None:      # UT-080
    project = _project(tmp_path, monkeypatch)
    mid = _transcribed(_repo(project), datetime(2026, 10, 19, 16, 0, 0))
    curator = FakeActivityCurator([answer()])
    _wire(monkeypatch, curator=curator)

    result = runner.invoke(app, ["activities", "curate", mid])

    assert result.exit_code == 1
    assert f"Meeting {mid} is transcribed, not analyzed: run trec analyze {mid} first.\n" in result.output
    assert curator.inputs == []


def test_a_meeting_whose_analysis_failed_is_reported_as_transcribed(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    mid = _transcribed(repo, datetime(2026, 10, 19, 16, 0, 0))
    repo.mark_failed(mid, "analysis failed: the model refused")
    _wire(monkeypatch, curator=FakeActivityCurator([answer()]))

    result = runner.invoke(app, ["activities", "curate", mid])

    assert result.exit_code == 1 and f"Meeting {mid} is transcribed, not analyzed" in result.output


def test_curate_with_an_unknown_meeting_uses_the_existing_message(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path, monkeypatch)
    _wire(monkeypatch, curator=FakeActivityCurator([answer()]))
    result = runner.invoke(app, ["activities", "curate", "2026-01-01_00-00-00"])
    assert result.exit_code == 1 and Cli.MEETING_MISSING.format(meeting_id="2026-01-01_00-00-00") in result.output


@pytest.mark.parametrize("args", [[], ["2026-10-19_09-30-11", "--since", "2026-10-05"]])
def test_curate_wants_ids_or_since_and_not_both(tmp_path: Path, monkeypatch, args) -> None:
    _project(tmp_path, monkeypatch)
    _wire(monkeypatch, curator=FakeActivityCurator([answer()]))
    result = runner.invoke(app, ["activities", "curate", *args])
    assert result.exit_code == 1 and (Cli.CURATE_NEEDS_TARGET if not args else Cli.CURATE_ONE_TARGET) in result.output


def test_curate_checks_the_provider_prerequisites_after_the_meetings(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    mid = seed(_repo(project), datetime(2026, 10, 19, 9, 30))
    _wire(monkeypatch, curator=FakeActivityCurator([answer()]))
    result = runner.invoke(app, ["activities", "curate", mid])
    assert result.exit_code == 1 and Cli.API_KEY_MISSING in result.output


# --- trec activities curate <id>: the happy line and the wait (UT-089) ------------------------------------------------------
def test_curate_prints_the_line_of_a_curated_meeting(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    mid = seed(_repo(project), datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    ops = [insert("- [ ] **Enviar o cronograma**"), insert("- [ ] **Estimar**", refs=("1.a2",))]
    curator = FakeActivityCurator([answer(ops, summary="1 ação nova, prazo do cronograma mudou para sex 16/10")])
    _wire(monkeypatch, curator=curator)

    result = runner.invoke(app, ["activities", "curate", mid])

    assert result.exit_code == 0, result.output
    assert result.output == "Curating Revisão de sprint (19/10)… ok (2 edits) — 1 ação nova, prazo do cronograma mudou para sex 16/10\n"
    assert "- [ ] **Estimar**" in _document(project)


def test_curate_waits_for_a_pass_that_is_running_and_says_so_once(tmp_path: Path, monkeypatch) -> None:       # UT-089
    project = _project(tmp_path, monkeypatch)
    mid = seed(_repo(project), datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    store = InMemoryActivityStore(busy=True)
    _wire(monkeypatch, curator=FakeActivityCurator([answer([insert("- [ ] **Enviar o cronograma**")])]), activity_store=store)

    result = runner.invoke(app, ["activities", "curate", mid])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "waiting for the curator…" and result.output.count("waiting for the curator…") == 1
    assert lines[1].startswith("Curating Revisão de sprint (19/10)… ok (1 edits)")
    assert store.locks == [False, True]                         # tried without blocking, then blocked
    assert len(store.commits) == 1


def test_a_failed_meeting_prints_the_reason_writes_the_error_file_and_exits_1(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    mid = seed(repo, datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    _, notifier = _wire(monkeypatch, curator=FakeActivityCurator(fail=AnalysisError("Claude Code timed out after 900 s")))

    result = runner.invoke(app, ["activities", "curate", mid])

    assert result.exit_code == 1
    assert result.output == "Curating Revisão de sprint (19/10)… failed: Claude Code timed out after 900 s\n"
    assert repo.path(mid, CURATION_ERROR).read_text().strip() == "Activity curation failed: Claude Code timed out after 900 s"
    assert [title for title, _ in notifier.messages] == [Notify.ACTIVITIES_FAILED]


# --- trec activities curate --since (UT-081, UT-088, E2E-002) -----------------------------------------------------------------
def test_since_answering_no_prints_the_estimate_and_curates_nothing(tmp_path: Path, monkeypatch) -> None:        # UT-081
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    for started in (datetime(2026, 10, 5, 9, 30), datetime(2026, 10, 5, 14, 0), datetime(2026, 10, 6, 9, 30)):
        seed(repo, started)
    curator = FakeActivityCurator([answer()])
    _wire(monkeypatch, curator=curator)

    result = runner.invoke(app, ["activities", "curate", "--since", "2026-10-05"], input="n\n")

    assert result.exit_code == 0, result.output
    assert "Curate 3 meetings in 2 passes using the Anthropic API (spends API credit) (~10 min)? [y/N]: " in result.output
    assert result.output.rstrip().endswith("Nothing curated.")
    assert curator.inputs == [] and not _store(project).path().exists()


@pytest.mark.parametrize(("provider", "wording"), [
    ("claude-code", "using your Claude subscription"),
    ("api", "using the Anthropic API (spends API credit)"),
])
def test_the_confirmation_names_what_the_run_spends_and_the_estimate_is_passes_times_160_s(tmp_path: Path, monkeypatch, provider, wording) -> None:   # UT-088
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("TREC_LLM_PROVIDER", provider)
    monkeypatch.setattr("teams_recorder.adapters.inbound.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    repo = _repo(project)
    for day in range(1, 10):                                       # nine days: nine passes
        seed(repo, datetime(2026, 10, day, 9, 30))
    curator = FakeActivityCurator([answer()])
    _wire(monkeypatch, curator=curator)

    result = runner.invoke(app, ["activities", "curate", "--since", "2026-10-01"], input="n\n")

    minutes = -(-9 * Activities.EST_SECONDS_PER_PASS // 60 // 5) * 5      # 1440 s = 24 min, shown rounded up to 5
    assert Activities.EST_SECONDS_PER_PASS == 160 and minutes == 25
    assert f"Curate 9 meetings in 9 passes {wording} (~25 min)? [y/N]: " in result.output
    assert curator.inputs == []


def test_since_with_no_analyzed_meeting_says_so_and_asks_nothing(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _transcribed(_repo(project), datetime(2026, 10, 6, 9, 30))
    seed(_repo(project), datetime(2026, 9, 1, 9, 30))               # analyzed, but before the date
    _wire(monkeypatch, curator=FakeActivityCurator([answer()]))
    result = runner.invoke(app, ["activities", "curate", "--since", "2026-10-05"])
    assert result.exit_code == 0 and result.output == Cli.CURATE_NOTHING_SINCE.format(since="2026-10-05") + "\n"


def test_since_rejects_a_bad_date(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["activities", "curate", "--since", "last week"])
    assert result.exit_code == 1 and "invalid date" in result.output


class _ScriptedTransport:
    """The model's side of the API: a structured answer per schema, recording every call's tag."""

    name = "scripted"

    def __init__(self, analysis: AnalysisOut, curated: list[CuratorOut]) -> None:
        self.analysis, self.curated = analysis, list(curated)
        self.tags: list[str] = []

    def complete(self, system, user, schema, *, tag, extra=None):
        self.tags.append(tag)
        if schema is AnalysisOut:
            return self.analysis
        return self.curated.pop(0) if len(self.curated) > 1 else self.curated[0]


def _curated(text: str, summary: str, focus: list[str], notify: bool = False) -> CuratorOut:
    op = {"op": "insert_after", "target": ACTIONS, "text": text, "reason": None, "anchor": None, "refs": ["1.a1"]}
    return CuratorOut.model_validate({"ops": [op], "focus": focus, "summary": summary, "notify": notify})


def _scripted(monkeypatch, transport: _ScriptedTransport) -> tuple[FakeClock, FakeNotifier]:
    return _wire(monkeypatch, analyzer=ClaudeAnalyzer(transport, system_prompt="SYS"), curator=ClaudeCurator(transport, system_prompt="SYS"),
                 verifier=None)


def test_since_curates_a_pass_per_day_and_creates_the_document(tmp_path: Path, monkeypatch) -> None:     # E2E-002
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    first = seed(repo, datetime(2026, 10, 5, 9, 30, 11), "Daily")
    second = seed(repo, datetime(2026, 10, 5, 14, 0, 3), "Revisão de sprint")
    third = seed(repo, datetime(2026, 10, 6, 9, 30, 11), "Daily")
    seed(repo, datetime(2026, 10, 2, 9, 30, 11), "Antiga")           # before the date: left alone
    transport = _ScriptedTransport(AnalysisOut(summary="x"), [
        _curated("- [ ] **Enviar o cronograma** (segunda)", "1 ação nova (segunda)", ["**Enviar o cronograma**"]),
        _curated("- [ ] **Estimar a integração** (terça)", "1 ação nova (terça)", ["**Estimar a integração**"]),
    ])
    clock, _ = _scripted(monkeypatch, transport)

    result = runner.invoke(app, ["activities", "curate", "--since", "2026-10-05", "--yes"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "Curating Daily (05/10), Revisão de sprint (05/10)… ok (1 edits) — 1 ação nova (segunda)",
        "Curating Daily (06/10)… ok (1 edits) — 1 ação nova (terça)",
    ]
    assert transport.tags == [f"curate:{first}", f"curate:{third}"]       # two passes: the day's two meetings went together
    document = _document(project)
    assert "- [ ] **Enviar o cronograma** (segunda)" in document and "- [ ] **Estimar a integração** (terça)" in document
    records = _store(project).passes()
    assert [(r.kind, r.meetings) for r in records] == [(PassKind.MEETING, (first, second)), (PassKind.MEETING, (third,))]
    assert "Estimar a integração" in document.split(ActivityDoc.HEADING_ACTIONS)[0]        # the box carries the last focus


def test_a_failed_meeting_does_not_stop_the_next_pass_and_exits_1(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    bad = seed(repo, datetime(2026, 10, 5, 9, 30, 11), "Daily")
    good = seed(repo, datetime(2026, 10, 6, 9, 30, 11), "Alinhamento")
    _wire(monkeypatch, curator=_CuratorFailingFor((bad,), "Claude Code timed out after 900 s", [answer([insert("- [ ] **Estimar**")], summary="1 ação nova")]))

    result = runner.invoke(app, ["activities", "curate", "--since", "2026-10-05", "--yes"])

    assert result.exit_code == 1
    assert result.output.splitlines() == [
        "Curating Daily (05/10)… failed: Claude Code timed out after 900 s",
        "Curating Alinhamento (06/10)… ok (1 edits) — 1 ação nova",
    ]
    assert _repo(project).curation_error(bad) is not None and _repo(project).curation_error(good) is None


def test_a_batch_that_fails_is_rerun_one_meeting_at_a_time(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    good = seed(repo, datetime(2026, 10, 5, 9, 30, 11), "Daily")
    bad = seed(repo, datetime(2026, 10, 5, 14, 0, 3), "Revisão de sprint")
    _wire(monkeypatch, curator=_CuratorFailingFor((bad,), "the model refused", [answer([insert("- [ ] **Estimar**")], summary="1 ação nova")]))

    result = runner.invoke(app, ["activities", "curate", good, bad])

    assert result.exit_code == 1
    assert result.output.splitlines() == ["Curating Daily (05/10)… ok (1 edits) — 1 ação nova", "Curating Revisão de sprint (05/10)… failed: the model refused"]


# --- trec activities (UT-082, UT-083) -------------------------------------------------------------------------------------------
def _write_document(project: Path, actions: int = 7, waiting: int = 3, agenda: int = 2, context: int = 5) -> None:
    lines = ["# Atividades", "", ActivityDoc.BOX_START, "> **Atualizado seg 19/10 10:12** · após Daily", ">", "> **Foco**",
             "> 1. **Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10 e ela precisa dele para o aceite.",
             "> 2. **Estimar a integração de estoque**: vence seg 19/10.",
             f"{ActivityDoc.BOX_END_PREFIX} 20261019-101200{ActivityDoc.BOX_END_SUFFIX}", "", ActivityDoc.HEADING_ACTIONS, ""]
    lines += [f"- [ ] ação {i}" for i in range(actions)] + [""]
    lines += [ActivityDoc.HEADING_WAITING, ""] + [f"- [ ] espera {i}" for i in range(waiting)] + [""]
    lines += [ActivityDoc.HEADING_AGENDA, ""] + [f"- agenda {i}" for i in range(agenda)] + [""]
    lines += [ActivityDoc.HEADING_CONTEXT, ""] + [f"- contexto {i}" for i in range(context)] + ["", ActivityDoc.LINKS_START, ActivityDoc.LINKS_END, ""]
    path = _store(project).path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def test_activities_shows_where_the_document_stands(tmp_path: Path, monkeypatch) -> None:           # UT-082
    project = _project(tmp_path, monkeypatch, key=False)
    repo = _repo(project)
    daily = seed(repo, datetime(2026, 10, 19, 9, 30, 11), "Daily")
    failed = seed(repo, datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    never = seed(repo, datetime(2026, 10, 16, 17, 30, 0), "Alinhamento Acme")
    repo.mark_curation_failed(failed, "Activity curation failed: Claude Code timed out after 900 s")
    _write_document(project)
    _store(project).log_pass(rec(PassKind.MEETING, daily, version="20261019-101200", summary="1 ação nova, 1 possível conclusão"))
    clock, _ = _wire(monkeypatch)
    clock.current = datetime(2026, 10, 19, 15, 0)

    result = runner.invoke(app, ["activities"])

    assert result.exit_code == 0, result.output
    assert result.output == (
        "Document: data/activities/atividades.md\n"
        "Updated Mon 19/10 10:12 after Daily\n"
        "Focus:\n"
        "  1. **Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10 e ela precisa dele para o aceite.\n"
        "  2. **Estimar a integração de estoque**: vence seg 19/10.\n"
        "Open: 7 yours · 3 waiting on others · 2 agenda · 5 context\n"
        "Last pass: Mon 19/10 10:12 — 1 ação nova, 1 possível conclusão\n"
        "Not curated:\n"
        f"  {failed} (Revisão de sprint): Claude Code timed out after 900 s → trec activities curate {failed}\n"
        f"  {never} (Alinhamento Acme): not attempted yet → trec activities curate {never}\n"
    )


def test_activities_leaves_out_a_section_whose_heading_was_renamed(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    _write_document(project)
    path = _store(project).path()
    path.write_text(path.read_text().replace(ActivityDoc.HEADING_WAITING, "## Esperando"), encoding="utf-8")
    _wire(monkeypatch)
    result = runner.invoke(app, ["activities"])
    assert "Open: 7 yours · 2 agenda · 5 context\n" in result.output
    assert "Last pass: none recorded\n" in result.output and "Updated" not in result.output and "Not curated" not in result.output


def test_activities_without_a_document_gives_the_bootstrap_hint(tmp_path: Path, monkeypatch) -> None:      # UT-083
    _project(tmp_path, monkeypatch, key=False)
    _wire(monkeypatch)
    result = runner.invoke(app, ["activities"])
    assert result.exit_code == 0
    assert result.output == "No activities document yet. Build it from past meetings: trec activities curate --since YYYY-MM-DD\n"


def test_activities_never_takes_the_curator_lock(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    store = InMemoryActivityStore(document=(_write_document(project), _store(project).path().read_text())[1], busy=True)
    _wire(monkeypatch, activity_store=store)
    result = runner.invoke(app, ["activities"])
    assert result.exit_code == 0 and "Open: 7 yours" in result.output
    assert store.locks == []


def test_open_hands_the_document_to_the_default_application(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    _write_document(project)
    opened: list[Path] = []
    monkeypatch.setattr(cli, "_open_document", opened.append)
    _wire(monkeypatch)

    assert runner.invoke(app, ["activities"]).exit_code == 0 and opened == []
    result = runner.invoke(app, ["activities", "--open"])

    assert result.exit_code == 0 and opened == [_store(project).path()]
    assert result.output.startswith("Document: data/activities/atividades.md\n")


def test_open_without_a_document_opens_nothing(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path, monkeypatch, key=False)
    opened: list[Path] = []
    monkeypatch.setattr(cli, "_open_document", opened.append)
    _wire(monkeypatch)
    result = runner.invoke(app, ["activities", "--open"])
    assert result.exit_code == 0 and opened == [] and result.output.startswith("No activities document yet.")


def test_a_failing_opener_is_reported_and_exits_1(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    _write_document(project)

    def broken(path: Path) -> None:
        raise subprocess.CalledProcessError(1, ["open"])

    monkeypatch.setattr(cli, "_open_document", broken)
    _wire(monkeypatch)
    result = runner.invoke(app, ["activities", "--open"])
    assert result.exit_code == 1 and "could not open" in result.output


def test_the_opener_is_open_on_macos_and_startfile_on_windows(tmp_path: Path) -> None:
    path = tmp_path / "atividades.md"
    ran: list[list[str]] = []
    started: list[str] = []

    _open_document(path, platform="darwin", run=lambda command, **kw: ran.append(command))
    assert ran == [["open", str(path)]] and started == []

    _open_document(path, platform="win32", startfile=started.append, run=lambda command, **kw: ran.append(command))
    assert started == [str(path)] and len(ran) == 1


# --- trec analyze: the curation step (UT-084, UT-085, UT-086, E2E-001) ---------------------------------------------------------
def test_analyze_curates_what_it_analyzed_in_batches_of_four_oldest_first(tmp_path: Path, monkeypatch) -> None:     # UT-084
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    started = [datetime(2026, 10, 19, 15, 0), datetime(2026, 10, 19, 9, 0), datetime(2026, 10, 19, 13, 0), datetime(2026, 10, 19, 11, 0),
               datetime(2026, 10, 19, 17, 0)]
    ids = [_transcribed(repo, at, f"Reunião {n}") for n, at in enumerate(started)]
    ordered = sorted(ids)
    curator = FakeActivityCurator([answer([insert("- [ ] **A**")], summary="1 ação nova"), answer([insert("- [ ] **B**")], summary="1 ação nova")])
    _wire(monkeypatch, analyzer=_Analyzer(), curator=curator, verifier=None)

    result = runner.invoke(app, ["analyze"])

    assert result.exit_code == 0, result.output
    assert [[c.meeting_id for c in data.meetings] for data in curator.inputs] == [ordered[:4], ordered[4:]]
    out = result.output
    assert out.count("Analyzing ") == 5 and out.count("Curating ") == 2
    assert out.index("Analyzing " + ordered[-1]) < out.index("Curating ")                  # the step runs after the whole loop
    curating = [line for line in out.splitlines() if line.startswith("Curating ")]
    assert curating[0].endswith("… ok (1 edits) — 1 ação nova") and curating[1].endswith("… ok (1 edits) — 1 ação nova")
    assert curating[1].startswith("Curating Reunião") and curating[1].count("(19/10)") == 1


def test_a_curation_failure_after_a_good_analysis_keeps_exit_0(tmp_path: Path, monkeypatch) -> None:     # UT-085
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    mid = _transcribed(repo, datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    _, notifier = _wire(monkeypatch, analyzer=_Analyzer(), verifier=None, curator=FakeActivityCurator(fail=AnalysisError("Claude Code timed out after 900 s")))

    result = runner.invoke(app, ["analyze", mid])

    assert result.exit_code == 0, result.output
    assert "Curating Revisão de sprint (19/10)… failed: Claude Code timed out after 900 s\n" in result.output
    assert repo.path(mid, CURATION_ERROR).read_text().strip() == "Activity curation failed: Claude Code timed out after 900 s"
    assert [title for title, _ in notifier.messages] == [Notify.ACTIVITIES_FAILED]
    assert "analyzed" in runner.invoke(app, ["status"]).output                              # the meeting stays analyzed


def _no_traceback(result: Any) -> bool:
    """The command ended by itself (an exit code, even 1), not by an exception escaping it."""
    return result.exception is None or isinstance(result.exception, SystemExit)


def _break_the_store(project: Path) -> None:
    """A file where the store's `.curator` folder belongs: the lock cannot even be set up (the same OSError a full disk gives)."""
    store = _store(project)
    store.root.mkdir(parents=True)
    store.curator_dir.write_text("not a folder", encoding="utf-8")


def test_a_store_that_cannot_lock_is_a_failed_curation_line_not_a_traceback_after_analyze(tmp_path: Path, monkeypatch) -> None:     # review 006, issue 004
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    mid = _transcribed(repo, datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    _break_the_store(project)
    curator = FakeActivityCurator([answer([insert("- [ ] **A**")])])
    _wire(monkeypatch, analyzer=_Analyzer(), verifier=None, curator=curator)

    result = runner.invoke(app, ["analyze", mid])

    assert result.exit_code == 0 and _no_traceback(result), result.output     # every analysis succeeded: a curation failure never changes it
    assert "Curating Revisão de sprint (19/10)… failed: the activities files could not be read or written" in result.output
    assert curator.inputs == [] and "analyzed" in runner.invoke(app, ["status"]).output


def test_a_store_that_cannot_lock_fails_the_explicit_curate_with_exit_1_and_no_traceback(tmp_path: Path, monkeypatch) -> None:     # review 006, issue 004
    project = _project(tmp_path, monkeypatch)
    mid = seed(_repo(project), datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    _break_the_store(project)
    _wire(monkeypatch, curator=FakeActivityCurator([answer()]))

    result = runner.invoke(app, ["activities", "curate", mid])

    assert result.exit_code == 1 and _no_traceback(result), result.output
    assert "failed: the activities files could not be read or written" in result.output


def test_a_commit_left_unfinished_is_said_after_the_ok_line_and_keeps_exit_0(tmp_path: Path, monkeypatch) -> None:     # review 006, issue 001
    project = _project(tmp_path, monkeypatch)
    mid = seed(_repo(project), datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    store = InMemoryActivityStore()
    store.fail_commit = CommitIncomplete("the activities pass 20261019-101200 replaced the document but could not finish (base.md: disk full)")
    _, notifier = _wire(monkeypatch, activity_store=store, curator=FakeActivityCurator([answer([insert("- [ ] **A**")])]))

    result = runner.invoke(app, ["activities", "curate", mid])

    assert result.exit_code == 0, result.output
    assert Cli.CURATION_UNFINISHED.format(reason=str(store.fail_commit)) + "\n" in result.output and "failed:" not in result.output
    assert _repo(project).curation_error(mid) is None and Notify.ACTIVITIES_FAILED not in [title for title, _ in notifier.messages]


class _FirstCallFails(FakeActivityCurator):
    """The first call (the batch) raises; the next ones answer as scripted."""

    def curate(self, data: CuratorInput) -> Any:
        if not self.inputs:
            self.inputs.append(data)
            raise RuntimeError("batch call failed")
        return super().curate(data)


def test_a_meeting_deferred_by_an_unfinished_rerun_is_named_and_keeps_exit_0(tmp_path: Path, monkeypatch) -> None:     # review 008, issue 001
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    first = seed(repo, datetime(2026, 10, 19, 9, 0, 3), "Daily")
    second = seed(repo, datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    store = InMemoryActivityStore()
    store.fail_commit = CommitIncomplete("the activities pass 20261019-101200 replaced the document but could not finish (base.md: disk full)")
    curator = _FirstCallFails([answer([insert("- [ ] **A**")])])
    _wire(monkeypatch, activity_store=store, curator=curator)

    result = runner.invoke(app, ["activities", "curate", first, second])

    assert result.exit_code == 0, result.output
    assert len(curator.inputs) == 2                                       # the failed batch and the first meeting alone; the second waits
    assert Cli.CURATION_UNFINISHED.format(reason=str(store.fail_commit)) + "\n" in result.output
    assert Cli.CURATION_DEFERRED.format(meeting="Revisão de sprint (19/10)") + "\n" in result.output
    assert "Deferred Daily" not in result.output and "failed:" not in result.output
    assert repo.curation_error(first) is None and repo.curation_error(second) is None


def test_a_failed_analysis_exits_1_and_is_not_curated(tmp_path: Path, monkeypatch) -> None:       # UT-085
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    bad = _transcribed(repo, datetime(2026, 10, 19, 9, 0), "Daily")
    good = _transcribed(repo, datetime(2026, 10, 19, 14, 0), "Revisão de sprint")
    curator = FakeActivityCurator([answer([insert("- [ ] **A**")], summary="1 ação nova")])
    _wire(monkeypatch, analyzer=_Analyzer(failing=(bad,)), verifier=None, curator=curator)

    result = runner.invoke(app, ["analyze"])

    assert result.exit_code == 1
    assert "FAILED: the model refused" in result.output
    assert [[c.meeting_id for c in data.meetings] for data in curator.inputs] == [[good]]
    assert "Curating Revisão de sprint (19/10)… ok (1 edits)" in result.output and "Curating Daily" not in result.output


def test_nothing_is_curated_when_every_analysis_failed(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    only = _transcribed(_repo(project), datetime(2026, 10, 19, 9, 0), "Daily")
    curator = FakeActivityCurator([answer()])
    _wire(monkeypatch, analyzer=_Analyzer(failing=(only,)), verifier=None, curator=curator)
    result = runner.invoke(app, ["analyze", only])
    assert result.exit_code == 1 and curator.inputs == [] and "Curating" not in result.output


def test_curation_can_be_switched_off_for_analyze_but_not_for_the_explicit_command(tmp_path: Path, monkeypatch) -> None:     # UT-086
    project = _project(tmp_path, monkeypatch, config="[activities]\nenabled = false\n")
    mid = _transcribed(_repo(project), datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    curator = FakeActivityCurator([answer([insert("- [ ] **A**")], summary="1 ação nova")])
    _wire(monkeypatch, analyzer=_Analyzer(), verifier=None, curator=curator)

    analyzed = runner.invoke(app, ["analyze", mid])

    assert analyzed.exit_code == 0, analyzed.output
    assert "Curating" not in analyzed.output and curator.inputs == [] and not _store(project).path().exists()

    explicit = runner.invoke(app, ["activities", "curate", mid])

    assert explicit.exit_code == 0 and explicit.output.startswith("Curating Revisão de sprint (19/10)… ok (1 edits)")
    assert len(curator.inputs) == 1


def test_analyze_waits_when_the_daemon_is_curating(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    mid = _transcribed(_repo(project), datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    _wire(monkeypatch, analyzer=_Analyzer(), verifier=None, activity_store=InMemoryActivityStore(busy=True),
          curator=FakeActivityCurator([answer([insert("- [ ] **A**")])]))
    result = runner.invoke(app, ["analyze", mid])
    assert result.exit_code == 0 and "waiting for the curator…\nCurating Revisão de sprint (19/10)… ok" in result.output


def test_analyze_then_activities_on_a_fixture_meeting(tmp_path: Path, monkeypatch) -> None:       # E2E-001
    project = _project(tmp_path, monkeypatch)
    repo = _repo(project)
    mid = _transcribed(repo, datetime(2026, 10, 19, 9, 30, 11), "Daily")
    analysis = AnalysisOut.model_validate({
        "summary": "Daily do projeto.", "title": "Daily",
        "my_actions": [{"description": "Enviar cronograma revisado do go-live", "owner": "usuário", "due": "2026-10-16", "priority": "high",
                        "at": "00:03:00", "kind": "communication", "for_whom": "Carla"}],
        "others_actions": [{"description": "Liberar o acesso ao SAP PRD", "owner": "Bruno", "due": None, "kind": "operation"}],
    })
    insert_mine = "- [ ] **Enviar cronograma revisado do go-live** — p/ Carla · sex 16/10 · alta"
    insert_theirs = "- [ ] **Bruno**: liberar o seu acesso ao SAP PRD"
    transport = _ScriptedTransport(analysis, [CuratorOut.model_validate({
        "ops": [
            {"op": "insert_after", "target": ACTIONS, "text": insert_mine, "refs": ["1.a1"]},
            {"op": "insert_after", "target": ActivityDoc.HEADING_WAITING, "text": insert_theirs, "refs": ["1.o1"]},
        ],
        "focus": ["**Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10 e ela precisa dele para o aceite.",
                  "Cobrar o **Bruno** pelo acesso ao PRD: trava a validação de ter 20/10."],
        "summary": "1 ação nova, 1 possível conclusão", "notify": True})])
    _, notifier = _scripted(monkeypatch, transport)

    analyzed = runner.invoke(app, ["analyze", mid])

    assert analyzed.exit_code == 0, analyzed.output
    assert transport.tags == [f"analyze:{mid}", f"curate:{mid}"]
    assert analyzed.output.rstrip().endswith("Curating Daily (19/10)… ok (2 edits) — 1 ação nova, 1 possível conclusão")
    assert notifier.messages == [(Notify.ACTIVITIES_UPDATED, "1 ação nova, 1 possível conclusão")]

    shown = runner.invoke(app, ["activities"])

    assert shown.exit_code == 0, shown.output
    assert shown.output == (
        "Document: data/activities/atividades.md\n"
        "Updated Mon 19/10 10:12 after Daily\n"
        "Focus:\n"
        "  1. **Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10 e ela precisa dele para o aceite.\n"
        "  2. Cobrar o **Bruno** pelo acesso ao PRD: trava a validação de ter 20/10.\n"
        "Open: 1 yours · 1 waiting on others · 0 agenda · 0 context\n"
        "Last pass: Mon 19/10 10:12 — 1 ação nova, 1 possível conclusão\n"
    )
    document = _document(project)
    assert insert_mine in document and insert_theirs in document


# --- not curated in `trec activities`, `trec doctor` and `trec status` (UT-087, E2E-005) -------------------------------------------
DOCTOR_LINE = "[{mark}] Activities document: data/activities/atividades.md ({state})"


def _doctor_activities_line(output: str) -> str:
    return next(line for line in output.splitlines() if "Activities document:" in line)


def _status_activities_line(output: str) -> str:
    return next(line for line in output.splitlines() if line.startswith("Activities:"))


def _two_meetings_not_curated(project: Path) -> tuple[str, str]:
    repo = _repo(project)
    failed = seed(repo, datetime(2026, 10, 19, 14, 0, 3), "Revisão de sprint")
    never = seed(repo, datetime(2026, 10, 16, 17, 30, 0), "Alinhamento Acme")
    repo.mark_curation_failed(failed, "Activity curation failed: Claude Code timed out after 900 s")
    return failed, never


def test_ut087_activities_lists_a_failed_and_a_never_attempted_meeting_and_doctor_counts_both(tmp_path: Path, monkeypatch) -> None:     # UT-087
    project = _project(tmp_path, monkeypatch, key=False)
    failed, never = _two_meetings_not_curated(project)
    _write_document(project)
    clock, _ = _wire(monkeypatch)
    clock.current = datetime(2026, 10, 19, 15, 0)

    listed = runner.invoke(app, ["activities"])
    doctor = runner.invoke(app, ["doctor"])

    assert listed.exit_code == 0, listed.output
    assert ("Not curated:\n"
            f"  {failed} (Revisão de sprint): Claude Code timed out after 900 s → trec activities curate {failed}\n"
            f"  {never} (Alinhamento Acme): not attempted yet → trec activities curate {never}\n") in listed.output
    assert _doctor_activities_line(doctor.output) == DOCTOR_LINE.format(mark="WARNING", state="2 meetings not curated (trec activities)")


def test_doctor_counts_a_single_meeting_in_the_singular(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    seed(_repo(project), datetime(2026, 10, 16, 17, 30, 0), "Alinhamento Acme")
    _write_document(project)
    _wire(monkeypatch)
    doctor = runner.invoke(app, ["doctor"])
    assert _doctor_activities_line(doctor.output) == DOCTOR_LINE.format(mark="WARNING", state="1 meeting not curated (trec activities)")


def test_doctor_lists_only_the_last_ten_working_days(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    repo = _repo(project)
    inside = seed(repo, datetime(2026, 10, 5, 9, 0, 0), "Dentro")        # Mon 19/10 is day 0: the window starts Mon 05/10
    seed(repo, datetime(2026, 10, 2, 9, 0, 0), "Fora")
    _write_document(project)
    _wire(monkeypatch)
    doctor = runner.invoke(app, ["doctor"])
    listed = runner.invoke(app, ["activities"])
    assert "1 meeting not curated" in doctor.output
    assert f"{inside} (Dentro)" in listed.output and "(Fora)" not in listed.output


def test_doctor_says_ok_with_the_last_pass_when_nothing_is_missing(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    daily = seed(_repo(project), datetime(2026, 10, 19, 9, 30, 11), "Daily")
    _write_document(project)
    _store(project).log_pass(rec(PassKind.MEETING, daily, version="20261019-101200", summary="1 ação nova"))
    _wire(monkeypatch)
    doctor = runner.invoke(app, ["doctor"])
    assert _doctor_activities_line(doctor.output) == DOCTOR_LINE.format(mark="ok ", state="ok, last pass Mon 19/10 10:12")


def test_doctor_says_ok_without_a_pass_when_the_document_has_no_record(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    _write_document(project)
    _wire(monkeypatch)
    doctor = runner.invoke(app, ["doctor"])
    assert _doctor_activities_line(doctor.output) == DOCTOR_LINE.format(mark="ok ", state="ok, no pass recorded")


def test_doctor_without_a_document_gives_the_bootstrap_command_even_with_analyzed_meetings(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    _two_meetings_not_curated(project)
    _wire(monkeypatch)
    doctor = runner.invoke(app, ["doctor"])
    assert _doctor_activities_line(doctor.output) == DOCTOR_LINE.format(mark="info", state="not created yet (trec activities curate --since YYYY-MM-DD)")


def test_doctor_reports_an_unreadable_pass_log_and_keeps_its_exit_code(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    _write_document(project)
    log = project / "data" / Files.LOG_DIR / Files.ACTIVITIES_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("not json\n{}\n", encoding="utf-8")
    _wire(monkeypatch)
    broken = runner.invoke(app, ["doctor"])
    log.unlink()
    fine = runner.invoke(app, ["doctor"])
    line = _doctor_activities_line(broken.output)
    assert line.startswith("[WARNING] Activities document: unreadable (") and Files.ACTIVITIES_LOG in line
    assert broken.exit_code == fine.exit_code   # the line never changes the exit code


def test_status_shows_the_documents_counts_and_no_open_actions_line(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    daily = seed(_repo(project), datetime(2026, 10, 19, 9, 30, 11), "Daily")
    _write_document(project)      # 7 open own items, 3 waiting
    _store(project).log_pass(rec(PassKind.MEETING, daily, version="20261019-101200", summary="1 ação nova"))
    _wire(monkeypatch)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert _status_activities_line(result.output) == "Activities: 7 yours · 3 waiting on others (last pass Mon 19/10 10:12)"
    assert "Open actions" not in result.output


def test_status_without_a_pass_record_or_a_document(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    _wire(monkeypatch)
    none = runner.invoke(app, ["status"])
    _write_document(project, waiting=0)
    bare = runner.invoke(app, ["status"])
    path = _store(project).path()
    path.write_text(path.read_text().replace(ActivityDoc.HEADING_ACTIONS, "## A").replace(ActivityDoc.HEADING_WAITING, "## B"), encoding="utf-8")
    renamed = runner.invoke(app, ["status"])
    assert _status_activities_line(none.output) == "Activities: not created yet (trec activities curate --since YYYY-MM-DD)"
    assert _status_activities_line(bare.output) == "Activities: 7 yours · 0 waiting on others"
    assert _status_activities_line(renamed.output) == "Activities: document has no actions or waiting sections"
    assert none.exit_code == bare.exit_code == renamed.exit_code == 0


def test_a_pass_log_the_file_system_cannot_read_is_reported_by_status_and_doctor_not_a_traceback(tmp_path: Path, monkeypatch) -> None:     # review 006, issue 004
    project = _project(tmp_path, monkeypatch, key=False)
    _write_document(project)
    (project / "data" / Files.LOG_DIR / Files.ACTIVITIES_LOG).mkdir(parents=True)     # a folder where the log belongs: an OSError, not bad JSON
    _wire(monkeypatch)

    status, doctor = runner.invoke(app, ["status"]), runner.invoke(app, ["doctor"])

    assert _no_traceback(status) and _no_traceback(doctor)
    assert "Activities: unreadable (the activities files could not be read or written" in status.output and "Meetings: 0" in status.output
    assert _doctor_activities_line(doctor.output).startswith("[WARNING] Activities document: unreadable (the activities files could not be read")


def test_status_reports_an_unreadable_pass_log_and_exits_1(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch, key=False)
    _write_document(project)
    log = project / "data" / Files.LOG_DIR / Files.ACTIVITIES_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("not json\n{}\n", encoding="utf-8")
    _wire(monkeypatch)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "Activities: unreadable (invalid JSON in" in result.output and Files.ACTIVITIES_LOG in result.output
    assert "Meetings: 0" in result.output     # the rest of the status is still shown


def test_e2e005_the_daemon_start_on_a_monday_curates_fridays_pending_meeting(tmp_path: Path, monkeypatch) -> None:     # E2E-005
    project = _project(tmp_path, monkeypatch, key=False)
    friday = seed(_repo(project), datetime(2026, 10, 16, 17, 30, 0), "Alinhamento Acme")    # analyzed Friday, no pass record
    store, clock = _store(project), FakeClock(NOW)                                          # NOW is Monday 19/10 10:12
    curator = FakeActivityCurator([answer([insert("- [ ] **Enviar o cronograma**")], summary="1 ação nova")])
    use, _, _ = build(_repo(project), store, curator, now=NOW)
    use.clock = clock
    daemon = Daemon(CuratingContainer(_repo(project), FakeCallDetector([]), FakeNotifier(), clock, FakeProcessCapture(), FakeMicCapture(), curate=use),
                    poll_seconds=0, start_after=2, stop_after=3, sleep=lambda s: None, run_in_background=lambda fn: fn())
    assert daemon.curator_worker is not None
    daemon._resume_pending()       # the start of the daemon queues what no pass covers
    step_soon(daemon.curator_worker)

    assert [(r.kind, r.meetings) for r in store.passes()] == [(PassKind.MEETING, (friday,))] and len(curator.inputs) == 1
    _wire(monkeypatch)
    listed = runner.invoke(app, ["activities"])
    doctor = runner.invoke(app, ["doctor"])
    assert listed.exit_code == 0, listed.output
    assert "Not curated" not in listed.output and "Last pass: Mon 19/10 10:12 — 1 ação nova\n" in listed.output
    assert _doctor_activities_line(doctor.output) == DOCTOR_LINE.format(mark="ok ", state="ok, last pass Mon 19/10 10:12")


# --- trec activities undo (UT-060 to UT-066 through the CLI, E2E-003) ----------------------------------------------------------
def _passes(project: Path, *items: str, archive_item: str | None = None) -> list[str]:
    """Runs one real pass per item (on the file store, a fake curator) and returns the meeting ids; the clock is a fake at NOW."""
    repo, store = _repo(project), _store(project)
    ids: list[str] = []
    clock = FakeClock(NOW)
    for n, item in enumerate(items):
        ids.append(seed(repo, datetime(2026, 10, 19, 8 + n, 0), "Daily"))
        ops = [insert(item)] if archive_item is None or n == 0 else [archive(archive_item, "feito")]
        clock.advance(minutes=5)
        CurateMeetings(repo, store, FakeActivityCurator([answer(ops, summary=f"passada {n + 1}")]), FakeNotifier(), clock).execute([ids[-1]])
    return ids


def test_undo_shows_the_pass_and_the_diff_asks_and_restores(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    ids = _passes(project, "- [ ] **A**", "- [ ] **B**")
    _wire(monkeypatch)
    store = _store(project)
    before = store.version(store.passes()[-1].version).before

    result = runner.invoke(app, ["activities", "undo"], input="y\n")

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "Last pass: Mon 19/10 10:22 after Daily (passada 2)"
    assert lines[1:3] == ["--- now", "+++ before the pass"] and lines[3].startswith("@@") and "-- [ ] **B**" in lines
    assert lines[-2].startswith("Restore the document to before this pass? [y/N]: ")
    assert lines[-1] == f"Restored. Run trec activities curate {ids[1]} to curate that meeting again."
    assert _document(project) == before and "**B**" not in _document(project) and "**A**" in _document(project)
    assert [r.kind for r in store.passes()] == [PassKind.MEETING, PassKind.MEETING, PassKind.UNDO]


def test_undo_answering_no_changes_nothing(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _passes(project, "- [ ] **A**")
    _wire(monkeypatch)
    document = _document(project)

    result = runner.invoke(app, ["activities", "undo"], input="n\n")

    assert result.exit_code == 0 and result.output.rstrip().endswith("Nothing restored.")
    assert _document(project) == document and [r.kind for r in _store(project).passes()] == [PassKind.MEETING]


def test_undo_with_yes_asks_nothing_and_says_how_many_lines_of_the_user_it_discards(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _passes(project, "- [ ] **A**")
    _wire(monkeypatch)
    path = _store(project).path()
    path.write_text(path.read_text().replace("- [ ] **A**", "- [ ] **A** (ajustei)"), encoding="utf-8")

    result = runner.invoke(app, ["activities", "undo", "--yes"])

    assert result.exit_code == 0, result.output
    assert "This also discards 1 line you edited after the pass.\n" in result.output and "[y/N]" not in result.output
    assert result.output.rstrip().splitlines()[-1].startswith("Restored. Run trec activities curate ")


def test_undo_says_how_many_lines_with_more_than_one(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _passes(project, "- [ ] **A**")
    _wire(monkeypatch)
    path = _store(project).path()
    path.write_text(path.read_text().replace("- [ ] **A**", "- [ ] **A** (1)\n- [ ] **Z**"), encoding="utf-8")
    result = runner.invoke(app, ["activities", "undo", "--yes"])
    assert "This also discards 2 lines you edited after the pass.\n" in result.output


def test_undo_names_every_meeting_of_a_pass_with_several(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    repo, store = _repo(project), _store(project)
    first, second = seed(repo, datetime(2026, 10, 19, 9, 0), "Daily"), seed(repo, datetime(2026, 10, 19, 10, 0), "Revisão")
    CurateMeetings(repo, store, FakeActivityCurator([answer([insert("- [ ] **A**")])]), FakeNotifier(), FakeClock(NOW)).execute([first, second])
    _wire(monkeypatch)
    result = runner.invoke(app, ["activities", "undo", "--yes"])
    assert result.output.splitlines()[0].endswith("after Daily, Revisão (1 ação nova)")
    assert result.output.rstrip().splitlines()[-1] == f"Restored. Run trec activities curate {first} {second} to curate those meetings again."


def test_undo_tells_when_the_archive_changed_after_the_pass(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _passes(project, "- [ ] **A**", "x", archive_item="- [ ] **A**")
    _wire(monkeypatch)
    archive_file = _store(project).archive_dir / "2026-10.md"
    archive_file.write_text(archive_file.read_text() + "### 20/10/2026 — outra\nitem\n")

    result = runner.invoke(app, ["activities", "undo", "--yes"])

    assert result.exit_code == 0, result.output
    assert result.output.rstrip().endswith("The archive changed after this pass; its entries were left in place.")
    assert "outra" in archive_file.read_text()


def test_undo_with_a_pass_running_says_so_and_exits_1_without_asking(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _passes(project, "- [ ] **A**")
    document = _document(project)
    busy = InMemoryActivityStore(busy=True)
    store = _store(project)
    busy.records, busy.versions = store.passes(), {r.version: store.version(r.version) for r in store.passes()}
    busy.document = document
    _wire(monkeypatch, activity_store=busy)

    result = runner.invoke(app, ["activities", "undo", "--yes"])

    assert result.exit_code == 1
    assert result.output.rstrip().splitlines()[-1] == "The curator is working; try again in a few minutes."
    assert busy.commits == [] and _document(project) == document


def test_undo_with_nothing_to_undo_exits_1(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _wire(monkeypatch)
    result = runner.invoke(app, ["activities", "undo"])
    assert result.exit_code == 1 and result.output == "No pass to undo.\n"


def test_undo_skips_failed_and_skipped_passes(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    ids = _passes(project, "- [ ] **A**")
    store = _store(project)
    store.log_pass(rec(PassKind.FAILED, "m9", version="20261019-120000"))
    store.log_pass(rec(PassKind.SKIPPED_EMPTY, "m8", version="20261019-120100"))
    _wire(monkeypatch)
    result = runner.invoke(app, ["activities", "undo", "--yes"])
    assert result.exit_code == 0 and f"curate {ids[0]} to curate that meeting again" in result.output


def test_undo_refuses_when_a_pass_committed_while_the_user_was_deciding(tmp_path: Path, monkeypatch) -> None:       # UT-065
    project = _project(tmp_path, monkeypatch)
    _passes(project, "- [ ] **A**")
    _wire(monkeypatch)
    answers: list[str] = []

    def a_pass_runs_meanwhile(*args: Any, **kwargs: Any) -> bool:
        answers.append("asked")
        repo, store = _repo(project), _store(project)
        CurateMeetings(repo, store, FakeActivityCurator([answer([insert("- [ ] **B**")])]), FakeNotifier(), FakeClock(NOW + timedelta(hours=1))
                       ).execute([seed(repo, datetime(2026, 10, 19, 14, 0), "Outra")])
        return True

    monkeypatch.setattr(cli.typer, "confirm", a_pass_runs_meanwhile)
    document = _document(project)

    result = runner.invoke(app, ["activities", "undo"])

    assert answers == ["asked"] and result.exit_code == 1
    assert result.output.rstrip().splitlines()[-1] == "A new pass ran while you were deciding; run trec activities undo again."
    assert "**B**" in _document(project) and _document(project) != document
    assert [r.kind for r in _store(project).passes()] == [PassKind.MEETING, PassKind.MEETING]


def test_undo_reports_a_pass_whose_version_files_are_gone(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path, monkeypatch)
    _passes(project, "- [ ] **A**")
    for part in _store(project).versions_dir.glob("*_before.md"):
        part.unlink()
    _wire(monkeypatch)
    result = runner.invoke(app, ["activities", "undo", "--yes"])
    assert result.exit_code == 1 and "error: file not found:" in result.output


def test_undo_after_an_analysis_and_a_curation_then_nothing_is_left(tmp_path: Path, monkeypatch) -> None:       # E2E-003
    project = _project(tmp_path, monkeypatch)
    mid = _transcribed(_repo(project), datetime(2026, 10, 19, 9, 30, 11), "Daily")
    item = "- [ ] **Enviar cronograma revisado do go-live** — p/ Carla · sex 16/10 · alta"
    transport = _ScriptedTransport(
        AnalysisOut.model_validate({"summary": "Daily do projeto.", "title": "Daily", "my_actions": [
            {"description": "Enviar cronograma revisado do go-live", "owner": "usuário", "due": "2026-10-16", "priority": "high",
             "at": "00:03:00", "kind": "communication", "for_whom": "Carla"}]}),
        [_curated(item, "1 ação nova", ["**Enviar cronograma revisado do go-live** à Carla"])])
    _scripted(monkeypatch, transport)
    analyzed = runner.invoke(app, ["analyze", mid])
    assert analyzed.exit_code == 0, analyzed.output
    assert item in _document(project) and _store(project).read_base() is not None

    undone = runner.invoke(app, ["activities", "undo"], input="y\n")

    assert undone.exit_code == 0, undone.output
    assert undone.output.splitlines()[0] == "Last pass: Mon 19/10 10:12 after Daily (1 ação nova)"
    assert undone.output.rstrip().endswith(f"Restored. Run trec activities curate {mid} to curate that meeting again.")
    assert item not in _document(project) and _store(project).read_base() is None             # the first pass: no base is left
    assert [r.kind for r in _store(project).passes()] == [PassKind.MEETING, PassKind.UNDO]

    again = runner.invoke(app, ["activities", "undo"])

    assert again.exit_code == 1 and again.output == "No pass to undo.\n"

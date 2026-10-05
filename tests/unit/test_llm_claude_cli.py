"""ClaudeCliAnalyzer com um `claude` simulado (script Python)."""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.llm_claude_cli import ClaudeCliAnalyzer
from teams_recorder.domain import AnalysisError, Meeting, Segment, Transcript

FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_claude_cli.py"


class Scripted(ClaudeCliAnalyzer):
    def command(self) -> list[str]:
        cmd = super().command()
        return [sys.executable, str(FAKE)] + cmd[1:]

    def analyze(self, transcript, meeting):  # pula a checagem de binário no PATH
        self.claude_bin = sys.executable
        return super().analyze(transcript, meeting)


@pytest.fixture
def meeting():
    return Meeting.start(datetime(2026, 10, 6, 14, 0, 0), title="Sprint")


@pytest.fixture
def transcript():
    return Transcript(segments=[Segment(0, 3, "Bom dia."), Segment(3, 9, "Felipe, relatório até quarta.")])


def test_success_maps_structured_output(tmp_path: Path, meeting, transcript, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "success")
    analyzer = Scripted(system_prompt="SYS", usage_log=tmp_path / "usage.jsonl", model="opus", effort="low")

    analysis = analyzer.analyze(transcript, meeting)

    assert analysis.meeting_id == meeting.id
    assert analysis.my_actions[0].due == date(2026, 10, 8) and analysis.my_actions[0].owner == "usuário"
    entry = json.loads((tmp_path / "usage.jsonl").read_text())
    assert entry["provider"] == "claude-code" and entry["input"] == 900 and entry["cost_usd_equiv"] == 0.0123


def test_command_shape():
    cmd = ClaudeCliAnalyzer(system_prompt="SYS", model="sonnet", effort="medium").command()
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert "--restricted" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "sonnet" and cmd[cmd.index("--effort") + 1] == "medium"
    assert cmd[cmd.index("--system-prompt") + 1] == "SYS"
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert schema["additionalProperties"] is False and "my_actions" in schema["properties"]


def test_error_envelope(meeting, transcript, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error")
    with pytest.raises(AnalysisError, match="error_during_execution.*Not logged in"):
        Scripted(system_prompt="SYS").analyze(transcript, meeting)


def test_falls_back_to_result_text(meeting, transcript, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "no_structured")
    analysis = Scripted(system_prompt="SYS").analyze(transcript, meeting)
    assert analysis.decisions[0].text == "Relatório até quarta."


def test_schema_violation(meeting, transcript, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "bad_schema")
    with pytest.raises(AnalysisError, match="fora do esquema"):
        Scripted(system_prompt="SYS").analyze(transcript, meeting)


def test_missing_binary(tmp_path: Path, meeting, transcript):
    with pytest.raises(AnalysisError, match="não encontrado"):
        ClaudeCliAnalyzer(system_prompt="SYS", claude_bin=str(tmp_path / "nao-existe")).analyze(transcript, meeting)


def test_empty_transcript_short_circuits(meeting):
    assert "vazia" in ClaudeCliAnalyzer(system_prompt="SYS").analyze(Transcript(), meeting).summary

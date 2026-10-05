import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from teams_recorder.adapters.outbound.llm_transport import ApiTransport, ClaudeCodeTransport
from teams_recorder.domain import AnalysisError

FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_claude_cli.py"


class Out(BaseModel):
    summary: str
    decisions: list[str] = []
    my_actions: list[dict] = []
    others_actions: list[dict] = []
    deadlines: list[dict] = []
    open_questions: list[str] = []
    next_meetings: list[str] = []


def _resp(text, stop="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop, model="m",
                           usage=SimpleNamespace(input_tokens=1, output_tokens=2, cache_read_input_tokens=0, cache_creation_input_tokens=0), _request_id="r")


class Client:
    def __init__(self, resp):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: self._rec(kw)))
        self.messages = SimpleNamespace(create=lambda **kw: self._rec(kw))
        self.resp, self.calls = resp, []

    def _rec(self, kw):
        self.calls.append(kw)
        return self.resp


def test_api_transport_success_and_log(tmp_path: Path):
    client = Client(_resp(json.dumps({"summary": "ok"})))
    t = ApiTransport(client=client, usage_log=tmp_path / "u.jsonl", effort="low")
    out = t.complete("SYS", "USER", Out, tag="plan:x")
    assert out.summary == "ok"
    kw = client.calls[0]
    assert kw["fallbacks"] == "default" and kw["output_config"]["effort"] == "low" and kw["system"][0]["text"] == "SYS"
    assert json.loads((tmp_path / "u.jsonl").read_text())["tag"] == "plan:x"


def test_api_transport_errors():
    with pytest.raises(AnalysisError, match="refused"):
        ApiTransport(client=Client(_resp("", "refusal"))).complete("S", "U", Out, tag="t")
    with pytest.raises(AnalysisError, match="truncated"):
        ApiTransport(client=Client(_resp("{", "max_tokens"))).complete("S", "U", Out, tag="t")
    with pytest.raises(AnalysisError, match="does not match the schema"):
        ApiTransport(client=Client(_resp(json.dumps({"summary": 1})))).complete("S", "U", Out, tag="t")


class ScriptedCli(ClaudeCodeTransport):
    def command(self, system, schema):
        return [sys.executable, str(FAKE)] + super().command(system, schema)[1:]


def test_claude_code_transport(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "success")
    t = ScriptedCli(claude_bin=sys.executable, usage_log=tmp_path / "u.jsonl")
    out = t.complete("SYS", "Transcript: x", Out, tag="plan:y")
    assert out.summary.startswith("Revisão")
    assert json.loads((tmp_path / "u.jsonl").read_text())["provider"] == "claude-code"
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error")
    with pytest.raises(AnalysisError, match="error_during_execution"):
        t.complete("SYS", "Transcript: x", Out, tag="plan:y")


def test_claude_code_missing_binary(tmp_path: Path):
    with pytest.raises(AnalysisError, match="not found"):
        ClaudeCodeTransport(claude_bin=str(tmp_path / "missing")).complete("S", "U", Out, tag="t")


def test_claude_code_transport_strips_anthropic_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "success")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-leak")
    out = ScriptedCli(claude_bin=sys.executable).complete("SYS", "Transcript: x", Out, tag="t")
    assert out.summary

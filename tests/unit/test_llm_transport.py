"""ApiTransport with a fake SDK client and ClaudeCodeTransport with a scripted `claude`."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from teams_recorder.adapters.outbound.llm_schema import AnalysisOut
from teams_recorder.adapters.outbound.llm_transport import FALLBACK_BETA, ApiTransport, ClaudeCodeTransport, claude_code_env
from teams_recorder.domain import AnalysisError

FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_claude_cli.py"
OK_JSON = json.dumps({"summary": "ok"})


def _resp(text, stop="end_turn", **extra):
    usage = SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=1000, cache_creation_input_tokens=0)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop, model="claude-opus-5-5", usage=usage, _request_id="req_1", **extra)


class Client:
    def __init__(self, resp):
        self.resp, self.calls, self.plain_calls = resp, [], []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._beta))
        self.messages = SimpleNamespace(create=self._plain)

    def _beta(self, **kw):
        self.calls.append(kw)
        return self.resp

    def _plain(self, **kw):
        self.plain_calls.append(kw)
        return self.resp


# --- API -------------------------------------------------------------------
def test_api_request_shape_and_usage_log(tmp_path: Path):
    client = Client(_resp(OK_JSON))
    t = ApiTransport(client=client, usage_log=tmp_path / "u.jsonl", effort="medium", model="claude-opus-5-5")

    out = t.complete("SYS", "USER", AnalysisOut, tag="analyze:m1", extra={"meeting": "m1"})

    assert out.summary == "ok"
    kw = client.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default" and kw["betas"] == [FALLBACK_BETA]
    assert kw["system"][0] == {"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}
    assert kw["output_config"]["effort"] == "medium" and kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["messages"] == [{"role": "user", "content": "USER"}]
    entry = json.loads((tmp_path / "u.jsonl").read_text())
    assert entry["tag"] == "analyze:m1" and entry["meeting"] == "m1" and entry["provider"] == "api"
    assert entry["input"] == 1200 and entry["cache_read"] == 1000 and entry["request_id"] == "req_1"


def test_api_without_fallbacks_uses_plain_messages():
    client = Client(_resp(OK_JSON))
    ApiTransport(client=client, use_fallbacks=False).complete("S", "U", AnalysisOut, tag="t")
    assert client.plain_calls and not client.calls and "fallbacks" not in client.plain_calls[0]


def test_api_refusal_includes_category():
    details = SimpleNamespace(category="cyber", explanation="x")
    with pytest.raises(AnalysisError, match="refused.*cyber"):
        ApiTransport(client=Client(_resp("", "refusal", stop_details=details))).complete("S", "U", AnalysisOut, tag="t")


def test_api_truncation_schema_and_missing_text():
    with pytest.raises(AnalysisError, match="truncated"):
        ApiTransport(client=Client(_resp("{", "max_tokens"))).complete("S", "U", AnalysisOut, tag="t")
    with pytest.raises(AnalysisError, match="does not match the schema"):
        ApiTransport(client=Client(_resp(json.dumps({"summary": 1})))).complete("S", "U", AnalysisOut, tag="t")
    resp = _resp(OK_JSON); resp.content = []
    with pytest.raises(AnalysisError, match="no text block"):
        ApiTransport(client=Client(resp)).complete("S", "U", AnalysisOut, tag="t")


# --- Claude Code -------------------------------------------------------------
class ScriptedCli(ClaudeCodeTransport):
    def command(self, system, schema):
        return [sys.executable, str(FAKE)] + super().command(system, schema)[1:]


def test_claude_code_success_and_usage_log(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "success")
    t = ScriptedCli(claude_bin=sys.executable, usage_log=tmp_path / "u.jsonl", model="opus", effort="low")

    out = t.complete("SYS", "Transcript: x", AnalysisOut, tag="analyze:m1", extra={"meeting": "m1"})

    assert out.summary.startswith("Revisão") and out.my_actions[0].due == "2026-10-08"
    entry = json.loads((tmp_path / "u.jsonl").read_text())
    assert entry["provider"] == "claude-code" and entry["meeting"] == "m1" and entry["input"] == 900 and entry["cost_usd_equiv"] == 0.0123


def test_claude_code_command_shape():
    cmd = ClaudeCodeTransport(model="sonnet", effort="medium").command("SYS", AnalysisOut)
    assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--output-format") + 1] == "json"
    assert "--restricted" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "sonnet" and cmd[cmd.index("--effort") + 1] == "medium"
    assert cmd[cmd.index("--system-prompt") + 1] == "SYS"
    assert json.loads(cmd[cmd.index("--json-schema") + 1])["additionalProperties"] is False


@pytest.mark.parametrize("mode,match", [("error", "error_during_execution.*Not logged in"), ("bad_schema", "does not match the schema")])
def test_claude_code_errors(monkeypatch, mode, match):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    with pytest.raises(AnalysisError, match=match):
        ScriptedCli(claude_bin=sys.executable).complete("SYS", "Transcript: x", AnalysisOut, tag="t")


def test_claude_code_falls_back_to_result_text(monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "no_structured")
    out = ScriptedCli(claude_bin=sys.executable).complete("SYS", "Transcript: x", AnalysisOut, tag="t")
    assert out.decisions[0].text == "Relatório até quarta." and out.decisions[0].at == "00:00:03"


def test_claude_code_missing_binary(tmp_path: Path):
    with pytest.raises(AnalysisError, match="not found"):
        ClaudeCodeTransport(claude_bin=str(tmp_path / "nope")).complete("S", "U", AnalysisOut, tag="t")


def test_claude_code_env_strips_anthropic_variables(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-leak")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    env = claude_code_env()
    assert not any(k.startswith("ANTHROPIC_") for k in env) and "PATH" in env
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "success")
    ScriptedCli(claude_bin=sys.executable).complete("SYS", "Transcript: x", AnalysisOut, tag="t")  # fake exits 4 on leak

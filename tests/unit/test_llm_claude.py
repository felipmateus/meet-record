"""ClaudeAnalyzer with a simulated client: no network, no key."""
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from teams_recorder.adapters.outbound.llm_claude import (
    FALLBACK_BETA,
    AnalysisOut,
    ClaudeAnalyzer,
    _strict_schema,
    build_user_message,
    to_domain,
)
from teams_recorder.domain import AnalysisError, Meeting, Segment, Transcript

SAMPLE_OUT = {
    "summary": "Revisão da sprint e definição de entregas.",
    "decisions": ["Relatório até quarta."],
    "my_actions": [{"description": "Enviar relatório de integração", "owner": "usuário", "due": "2026-10-08"}],
    "others_actions": [{"description": "Revisar escopo do SAP", "owner": "Mariana", "due": None}],
    "deadlines": [{"what": "Relatório de integração", "when": "2026-10-08", "who": "usuário"}],
    "open_questions": ["Escopo final da integração?"],
    "next_meetings": ["Cliente, semana de 13/10"],
}


def _response(text: str, stop_reason: str = "end_turn", **extra):
    usage = SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=1000, cache_creation_input_tokens=0)
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=usage,
        model="claude-opus-5-5",
        _request_id="req_test",
        **extra,
    )


@dataclass
class FakeMessages:
    response: object
    calls: list[dict] = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.beta = SimpleNamespace(messages=FakeMessages(response))
        self.messages = FakeMessages(response)


@pytest.fixture
def meeting():
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0), title="Planejamento")
    m.ended_at = datetime(2026, 10, 6, 14, 45, 0)
    return m


@pytest.fixture
def transcript():
    return Transcript(segments=[Segment(0, 3, "Bom dia."), Segment(3, 9, "Felipe, relatório até quarta.")])


def test_analyze_maps_to_domain_and_logs_usage(tmp_path: Path, meeting, transcript):
    client = FakeClient(_response(json.dumps(SAMPLE_OUT)))
    analyzer = ClaudeAnalyzer(system_prompt="SYS", min_words=1, client=client, usage_log=tmp_path / "usage.jsonl", effort="medium")

    analysis = analyzer.analyze(transcript, meeting)

    assert analysis.meeting_id == meeting.id
    assert analysis.summary.startswith("Revisão")
    assert analysis.my_actions[0].owner == "usuário" and analysis.my_actions[0].due == date(2026, 10, 8)
    assert analysis.others_actions[0].owner == "Mariana" and analysis.others_actions[0].due is None
    assert analysis.deadlines[0].when == date(2026, 10, 8)
    # request
    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default" and call["betas"] == [FALLBACK_BETA]
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"} and call["system"][0]["text"] == "SYS"
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "Transcript" in call["messages"][0]["content"]
    # usage log
    entry = json.loads((tmp_path / "usage.jsonl").read_text().strip())
    assert entry["meeting"] == meeting.id and entry["input"] == 1200 and entry["cache_read"] == 1000


def test_without_fallbacks_uses_plain_messages(meeting, transcript):
    client = FakeClient(_response(json.dumps(SAMPLE_OUT)))
    ClaudeAnalyzer(system_prompt="SYS", min_words=1, client=client, use_fallbacks=False).analyze(transcript, meeting)
    assert client.messages.calls and not client.beta.messages.calls
    assert "fallbacks" not in client.messages.calls[0]


def test_empty_transcript_short_circuits(meeting):
    client = FakeClient(_response("{}"))
    analysis = ClaudeAnalyzer(system_prompt="SYS", min_words=1, client=client).analyze(Transcript(), meeting)
    assert "Empty transcript" in analysis.summary and not client.beta.messages.calls


def test_refusal_is_an_error(meeting, transcript):
    details = SimpleNamespace(category="cyber", explanation="x")
    client = FakeClient(_response("", stop_reason="refusal", stop_details=details))
    with pytest.raises(AnalysisError, match="refused.*cyber"):
        ClaudeAnalyzer(system_prompt="SYS", min_words=1, client=client).analyze(transcript, meeting)


def test_truncation_is_an_error(meeting, transcript):
    client = FakeClient(_response("{", stop_reason="max_tokens"))
    with pytest.raises(AnalysisError, match="truncated"):
        ClaudeAnalyzer(system_prompt="SYS", min_words=1, client=client).analyze(transcript, meeting)


def test_schema_violation_is_an_error(meeting, transcript):
    client = FakeClient(_response(json.dumps({"summary": 123})))
    with pytest.raises(AnalysisError, match="does not match the schema"):
        ClaudeAnalyzer(system_prompt="SYS", min_words=1, client=client).analyze(transcript, meeting)


def test_to_domain_tolerates_bad_dates(meeting):
    out = AnalysisOut(summary="s", my_actions=[{"description": "x", "owner": "usuário", "due": "quarta-feira"}])
    assert to_domain(out, meeting).my_actions[0].due is None


def test_user_message_has_context(meeting, transcript):
    msg = build_user_message(transcript, meeting)
    assert "Meeting date: 2026-10-06 (Tuesday)" in msg and "Title: Planejamento" in msg and "Duration: 45 min" in msg
    assert "[00:00:03] Felipe" in msg


def test_strict_schema_closes_objects_and_requires_all_fields():
    schema = _strict_schema(AnalysisOut)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    action = schema["$defs"]["ActionOut"]
    assert action["additionalProperties"] is False and set(action["required"]) == {"description", "owner", "due"}
    assert "default" not in action["properties"]["due"]


def test_prompt_is_loaded_lazily_from_path(tmp_path: Path, meeting, transcript):
    prompt = tmp_path / "analyze_system.md"
    prompt.write_text("PROMPT FROM FILE\n")
    client = FakeClient(_response(json.dumps(SAMPLE_OUT)))
    analyzer = ClaudeAnalyzer(prompt_path=prompt, min_words=1, client=client)

    analyzer.analyze(transcript, meeting)

    assert client.beta.messages.calls[0]["system"][0]["text"] == "PROMPT FROM FILE"


def test_missing_prompt_file_is_an_error(tmp_path: Path, meeting, transcript):
    client = FakeClient(_response("{}"))
    with pytest.raises(AnalysisError, match="prompt not found"):
        ClaudeAnalyzer(prompt_path=tmp_path / "missing.md", min_words=1, client=client).analyze(transcript, meeting)


def test_short_transcript_is_not_sent(meeting):
    client = FakeClient(_response("{}"))
    short = Transcript(segments=[Segment(0, 1, "Tchau, tchau, tchau.")])
    analysis = ClaudeAnalyzer(system_prompt="SYS", client=client).analyze(short, meeting)
    assert "too short" in analysis.summary and "Tchau" in analysis.summary
    assert not client.beta.messages.calls

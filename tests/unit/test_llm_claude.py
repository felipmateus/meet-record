"""ClaudeAnalyzer with a fake transport: message building, trivial cases and domain mapping."""
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.llm_claude import AnalysisOut, ClaudeAnalyzer, build_user_message, strict_schema, to_domain
from teams_recorder.domain import AnalysisError, Meeting, Segment, Transcript

SAMPLE_OUT = AnalysisOut.model_validate({
    "summary": "Revisão da sprint e definição de entregas.",  # Portuguese: model output is data
    "decisions": ["Relatório até quarta."],
    "my_actions": [{"description": "Enviar relatório de integração", "owner": "usuário", "due": "2026-10-08"}],
    "others_actions": [{"description": "Revisar escopo do SAP", "owner": "Mariana", "due": None}],
    "deadlines": [{"what": "Relatório de integração", "when": "2026-10-08", "who": "usuário"}],
    "open_questions": ["Escopo final da integração?"],
    "next_meetings": ["Cliente, semana de 13/10"],
})


@dataclass
class FakeTransport:
    out: AnalysisOut = field(default_factory=lambda: SAMPLE_OUT)
    name: str = "fake"
    calls: list[dict] = field(default_factory=list)

    def complete(self, system, user, schema, *, tag, extra=None):
        self.calls.append({"system": system, "user": user, "schema": schema, "tag": tag, "extra": extra})
        return self.out


@pytest.fixture
def meeting():
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0), title="Planejamento")
    m.ended_at = datetime(2026, 10, 6, 14, 45, 0)
    return m


@pytest.fixture
def transcript():
    return Transcript(segments=[Segment(0, 3, "Bom dia."), Segment(3, 9, "Felipe, relatório até quarta.")])


def test_analyze_maps_to_domain_and_tags_the_call(meeting, transcript):
    transport = FakeTransport()
    analysis = ClaudeAnalyzer(transport, system_prompt="SYS", min_words=1).analyze(transcript, meeting)

    assert analysis.meeting_id == meeting.id
    assert analysis.summary.startswith("Revisão")
    assert analysis.my_actions[0].owner == "usuário" and analysis.my_actions[0].due == date(2026, 10, 8)
    assert analysis.others_actions[0].owner == "Mariana" and analysis.others_actions[0].due is None
    assert analysis.deadlines[0].when == date(2026, 10, 8)
    call = transport.calls[0]
    assert call["system"] == "SYS" and call["schema"] is AnalysisOut
    assert call["tag"] == f"analyze:{meeting.id}" and call["extra"] == {"meeting": meeting.id}
    assert "Transcript (with timestamps)" in call["user"]


def test_empty_and_short_transcripts_skip_the_transport(meeting):
    transport = FakeTransport()
    analyzer = ClaudeAnalyzer(transport, system_prompt="SYS")
    assert "Empty transcript" in analyzer.analyze(Transcript(), meeting).summary
    short = Transcript(segments=[Segment(0, 1, "Tchau, tchau, tchau.")])
    result = analyzer.analyze(short, meeting)
    assert "too short" in result.summary and "Tchau" in result.summary
    assert transport.calls == []


def test_prompt_is_loaded_lazily_from_path(tmp_path: Path, meeting, transcript):
    prompt = tmp_path / "analyze_system.md"
    prompt.write_text("PROMPT FROM FILE\n")
    transport = FakeTransport()
    ClaudeAnalyzer(transport, prompt_path=prompt, min_words=1).analyze(transcript, meeting)
    assert transport.calls[0]["system"] == "PROMPT FROM FILE"


def test_missing_prompt_is_an_error(tmp_path: Path, meeting, transcript):
    with pytest.raises(AnalysisError, match="prompt not found"):
        ClaudeAnalyzer(FakeTransport(), prompt_path=tmp_path / "nope.md", min_words=1).analyze(transcript, meeting)
    with pytest.raises(AnalysisError, match="no system prompt"):
        ClaudeAnalyzer(FakeTransport(), min_words=1).analyze(transcript, meeting)


def test_to_domain_tolerates_bad_dates(meeting):
    out = AnalysisOut(summary="s", my_actions=[{"description": "x", "owner": "usuário", "due": "quarta-feira"}])
    assert to_domain(out, meeting).my_actions[0].due is None


def test_user_message_has_context(meeting, transcript):
    msg = build_user_message(transcript, meeting)
    assert "Meeting date: 2026-10-06 (Tuesday)" in msg and "Title: Planejamento" in msg and "Duration: 45 min" in msg
    assert "[00:00:03] Felipe" in msg


def test_strict_schema_closes_objects_and_requires_all_fields():
    schema = strict_schema(AnalysisOut)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    action = schema["$defs"]["ActionOut"]
    assert action["additionalProperties"] is False and set(action["required"]) == {"description", "owner", "due"}
    assert "default" not in action["properties"]["due"]

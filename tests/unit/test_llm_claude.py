"""ClaudeAnalyzer with a fake transport: message building, trivial cases and domain mapping."""
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.llm_claude import AnalysisOut, ClaudeAnalyzer, build_user_message, strict_schema, to_domain
from teams_recorder.config import load_settings
from teams_recorder.constants import Files, Llm
from teams_recorder.domain import ActionKind, AnalysisError, Meeting, Segment, Transcript
from teams_recorder.messages import Prompt

SAMPLE_OUT = AnalysisOut.model_validate({
    "summary": "Revisão da sprint e definição de entregas.",  # Portuguese: model output is data
    "title": "Revisão da sprint",
    "purpose": "Definir as entregas da semana.",
    "meeting_type": "project_review",
    "participants": ["Felipe", "Mariana"],
    "topics": [{"title": "Integração SAP", "points": ["Escopo em aberto", " "]}],
    "decisions": [{"text": "Relatório até quarta.", "at": "00:00:03"}, {"text": "  ", "at": None}],
    "risks": ["Escopo do SAP indefinido"],
    "my_actions": [{"description": "Enviar relatório de integração", "owner": "usuário", "due": "2026-10-08", "priority": "high", "at": "00:00:03", "kind": "communication"}],
    "others_actions": [{"description": "Revisar escopo do SAP", "owner": "Mariana", "due": None, "kind": "management"}],
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
    out = AnalysisOut(summary="s", my_actions=[{"description": "x", "owner": "usuário", "due": "quarta-feira", "kind": "feature"}])
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
    assert action["additionalProperties"] is False and set(action["required"]) == {"description", "owner", "due", "priority", "at", "kind"}
    assert "default" not in action["properties"]["due"]


def test_new_fields_are_mapped(meeting, transcript):
    from teams_recorder.domain import MeetingType, Priority
    analysis = ClaudeAnalyzer(FakeTransport(), system_prompt="SYS", min_words=1).analyze(transcript, meeting)
    assert analysis.title == "Revisão da sprint" and analysis.purpose.startswith("Definir")
    assert analysis.meeting_type is MeetingType.PROJECT_REVIEW
    assert analysis.participants == ["Felipe", "Mariana"]
    assert analysis.topics[0].title == "Integração SAP" and analysis.topics[0].points == ["Escopo em aberto"]
    assert [d.text for d in analysis.decisions] == ["Relatório até quarta."] and analysis.decisions[0].at == "00:00:03"
    assert analysis.my_actions[0].priority is Priority.HIGH and analysis.my_actions[0].at == "00:00:03"
    assert analysis.others_actions[0].priority is None
    assert analysis.risks == ["Escopo do SAP indefinido"]


def test_user_name_goes_first_in_the_message(meeting, transcript):
    transport = FakeTransport()
    ClaudeAnalyzer(transport, system_prompt="SYS", min_words=1, user_name="Felipe").analyze(transcript, meeting)
    assert transport.calls[0]["user"].startswith("User (recording owner): Felipe\n")
    assert "User (recording owner)" not in build_user_message(transcript, meeting)


def test_schema_exposes_enums_and_timestamps():
    schema = strict_schema(AnalysisOut)
    props = schema["properties"]
    for key in ("title", "purpose", "meeting_type", "participants", "topics", "risks"):
        assert key in props and key in schema["required"]
    action = schema["$defs"]["ActionOut"]
    assert {"priority", "at"} <= set(action["required"])


def test_actions_keep_the_kind_the_model_gave_them():
    analysis = to_domain(SAMPLE_OUT, Meeting.start(datetime(2026, 10, 6, 10, 0)))
    assert analysis.my_actions[0].kind == ActionKind.COMMUNICATION and analysis.others_actions[0].kind == ActionKind.MANAGEMENT


def test_the_analysis_prompt_carries_the_fidelity_rules():
    """Fidelity guard task 6.0: the four rules the evaluation's analysis errors called for (evaluation §14.2)."""
    prompt = (load_settings().prompts_dir / Files.ANALYZE_PROMPT).read_text(encoding="utf-8")
    assert "Never infer the owner from who usually does that kind of work" in prompt                            # owners
    assert "the user speaks in the first person taking on a commitment" in prompt   # kept: the verifier marks the doubt
    assert "A person only talked about" in prompt and "is not a participant" in prompt                          # participants
    assert "A statement with doubt" in prompt and '"preciso confirmar"' in prompt                               # tentative
    assert "No sensitive personal data in any field" in prompt and "without the reason" in prompt               # sensitive
    assert "names of people mentioned or addressed" not in prompt   # the old participant rule is gone


def test_the_analysis_prompt_takes_owners_from_labels_and_participants_from_the_roster():
    """Speaker attribution UT-050 and UT-051b."""
    prompt = (load_settings().prompts_dir / Files.ANALYZE_PROMPT).read_text(encoding="utf-8")
    assert "A name after the timestamp" in prompt and "is the person who said the line" in prompt
    assert "There is no speaker identification" not in prompt
    assert "the user speaks in the first person taking on a commitment" in prompt and "applies to unlabelled lines only" in prompt
    assert "`participants` is exactly that list" in prompt
    assert "Do not replace `usuário` with the user's name" in prompt                       # the data contract keeps the literal
    assert "lines labelled with the owner's label, whatever name it is" in prompt          # ...for any label, a fallback one too


def test_the_message_names_the_roster_and_the_owners_label(meeting):
    """Speaker attribution UT-051."""
    names = ("Felipe Mateus de Carvalho", "Lucas Huguenin Gurgel de Moura")
    labelled = Transcript(segments=[Segment(0, 3, "Bom dia.", speaker=names[1]), Segment(3, 9, "Eu envio hoje.", speaker=names[0])],
                          roster=names, user_label=names[0])

    msg = build_user_message(labelled, meeting)

    assert "Participants seen in the meeting window: Felipe Mateus de Carvalho, Lucas Huguenin Gurgel de Moura\n" in msg
    assert 'Speaker labels: the name after a timestamp is who said the line; "Felipe Mateus de Carvalho" is the recording owner' in msg
    assert msg.index("Duration:") < msg.index("Participants seen") < msg.index("Speaker labels") < msg.index("Transcript (with timestamps)")
    assert "[00:00:03] Felipe Mateus de Carvalho: Eu envio hoje." in msg
    fallback = Transcript(segments=[Segment(0, 3, "Oi.", speaker="Você")], user_label="Você")
    assert 'Speaker labels: the name after a timestamp is who said the line; "Você" is the recording owner' in build_user_message(fallback, meeting)
    assert "Participants seen" not in build_user_message(fallback, meeting)


def test_an_unlabelled_transcript_gives_the_message_it_always_had(meeting, transcript):
    msg = build_user_message(transcript, meeting)
    assert "Participants seen" not in msg and "Speaker labels" not in msg
    assert msg == ("Meeting date: 2026-10-06 (Tuesday)\nStart: 14:00\nTitle: Planejamento\nDuration: 45 min"
                   "\n\nTranscript (with timestamps):\n\n[00:00:00] Bom dia.\n[00:00:03] Felipe, relatório até quarta.")


def test_the_schema_descriptions_repeat_the_owner_and_participant_rules():
    schema = json.dumps(strict_schema(AnalysisOut), ensure_ascii=False)
    for description in (Prompt.FIELD_PARTICIPANTS, Prompt.FIELD_ACTION_OWNER, Prompt.FIELD_DEADLINE_WHO):
        assert description.format(self_owner=Llm.OWNER_SELF, unknown=Llm.OWNER_UNKNOWN) in schema
    assert "exactly the listed participants" in schema and "lines labelled with the owner's label" in schema   # UT-055
    assert "not people only talked about" in Prompt.FIELD_PARTICIPANTS and "only when the transcript makes it evident" in Prompt.FIELD_DEADLINE_WHO

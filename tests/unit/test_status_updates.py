"""Progress statements: schema mapping, codec, verifier claims and the minutes section (UT-050 to UT-059)."""
import json
from datetime import date, datetime
from pathlib import Path

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.llm_schema import ActionOut, AnalysisOut, StatusUpdateOut, strict_schema, to_domain
from teams_recorder.adapters.outbound.minutes_markdown import MarkdownMinutesRenderer
from teams_recorder.adapters.outbound.verifier_claude import ClaudeClaimVerifier, VerdictOut, VerifyOut, claims_of, describe, to_verification
from teams_recorder.config import load_settings
from teams_recorder.constants import Files, Llm
from teams_recorder.domain import (
    Action, ActionKind, Analysis, ClaimKind, ClaimRef, Meeting, Segment, StatusChange, StatusUpdate, Transcript, Verification,
    VerificationStatus, claim_refs, claims, with_verifications,
)
from teams_recorder.messages import Minutes, Prompt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MEETING = Meeting.start(datetime(2026, 10, 12, 9, 0, 0))   # a Monday
NO = Verification(VerificationStatus.UNCONFIRMED, "a frase não aparece nesse trecho")
YES = Verification(VerificationStatus.CONFIRMED, "dito às 00:02:55")


def _updates() -> list[StatusUpdate]:
    return [
        StatusUpdate("timesheet de outubro", StatusChange.DONE, Llm.OWNER_SELF, "o timesheet eu já subi", "00:02:55"),
        StatusUpdate("conversão de unidade no relatório de estoque", StatusChange.DONE, "Diego", "o fix já tá em homologação", "00:06:40"),
        StatusUpdate("cronograma do go-live", StatusChange.DUE_CHANGED, Llm.OWNER_SELF, "o cronograma eu fecho hoje à tarde", "00:05:02",
                     new_due=date(2026, 10, 16)),
        StatusUpdate("relatório de testes", StatusChange.REASSIGNED, "Rafael", "passa o relatório para a Ana", "00:12:04", new_owner="Ana"),
    ]


def _analysis(**kw) -> Analysis:
    return Analysis(meeting_id=MEETING.id, summary="s", status_updates=_updates(), **kw)


def _out(**kw) -> AnalysisOut:
    return AnalysisOut.model_validate({"summary": "s", **kw})


# --- schema (UT-050, UT-051) -------------------------------------------------------------------------------------
def test_to_domain_maps_a_status_update_and_its_new_date():
    out = _out(status_updates=[
        {"about": " cronograma do go-live ", "change": "due_changed", "who": "usuário", "evidence": " o cronograma eu fecho hoje ", "at": "00:05:02",
         "new_due": "2026-10-16", "new_owner": None},
        {"about": "relatório de testes", "change": "reassigned", "who": "", "evidence": "passa para a Ana", "at": None, "new_due": "sexta", "new_owner": " Ana "},
        {"about": "  ", "change": "done", "who": "Ana", "evidence": "x", "at": None, "new_due": None, "new_owner": None},
    ])

    updates = to_domain(out, MEETING).status_updates

    assert updates[0] == StatusUpdate("cronograma do go-live", StatusChange.DUE_CHANGED, "usuário", "o cronograma eu fecho hoje", "00:05:02", date(2026, 10, 16))
    assert updates[1].who == Llm.OWNER_UNKNOWN and updates[1].new_due is None and updates[1].new_owner == "Ana" and updates[1].at is None
    assert len(updates) == 2   # an update about nothing is dropped


def test_for_whom_is_mapped_and_blank_is_none():
    action = {"description": "Enviar o cronograma", "owner": "usuário", "kind": "communication"}
    out = _out(my_actions=[{**action, "for_whom": "Carla"}], others_actions=[{**action, "for_whom": "  "}, action])

    analysis = to_domain(out, MEETING)

    assert analysis.my_actions[0].for_whom == "Carla"
    assert [a.for_whom for a in analysis.others_actions] == [None, None]


def test_the_schema_is_strict_and_describes_the_new_fields():
    schema = strict_schema(AnalysisOut)
    update = schema["$defs"]["StatusUpdateOut"]
    assert update["additionalProperties"] is False
    assert set(update["required"]) == {"about", "change", "who", "evidence", "at", "new_due", "new_owner"}
    assert "default" not in update["properties"]["new_due"] and "status_updates" in schema["required"]
    assert set(schema["$defs"]["StatusChange"]["enum"]) == {c.value for c in StatusChange}
    text = json.dumps(schema, ensure_ascii=False)
    for description in (Prompt.FIELD_FOR_WHOM, Prompt.FIELD_STATUS_ABOUT, Prompt.FIELD_STATUS_EVIDENCE, Prompt.FIELD_STATUS_NEW_DUE):
        assert description in text
    assert Prompt.FIELD_STATUS_WHO.format(self_owner=Llm.OWNER_SELF, unknown=Llm.OWNER_UNKNOWN) in text
    assert ActionOut(description="d", owner="o", kind=ActionKind.MANAGEMENT).for_whom is None
    assert StatusUpdateOut(about="a", change=StatusChange.DONE, who="w", evidence="e").new_due is None


def test_the_analysis_prompt_teaches_progress_and_says_an_intention_is_not_progress():
    prompt = (load_settings().prompts_dir / Files.ANALYZE_PROMPT).read_text(encoding="utf-8")
    assert "**status_updates**" in prompt and "for_whom" in prompt
    for change in StatusChange:
        assert f"`{change.value}`" in prompt
    assert "an intention is not progress" in prompt and "20 words" in prompt and "hedges kept" in prompt


# --- codec (UT-055) ----------------------------------------------------------------------------------------------
def test_old_analyses_load_without_the_new_fields_and_save_without_new_keys():
    for name in ("sample_analysis.json", "sample_analysis_v2.json"):
        raw = json.loads((FIXTURES / name).read_text())
        analysis = codec.analysis_from_dict(raw)
        assert analysis.status_updates == [] and all(a.for_whom is None for a in analysis.all_actions)
        written = codec.analysis_to_dict(analysis)
        assert "status_updates" not in written and not any("for_whom" in a for k in ("my_actions", "others_actions") for a in written[k])
        assert set(written) - set(raw) <= {"title", "purpose", "meeting_type", "participants", "topics", "risks"}   # nothing from this feature
        assert codec.analysis_from_dict(written) == analysis


def test_status_updates_and_for_whom_round_trip_with_optional_keys_only_when_set():
    analysis = _analysis(my_actions=[Action("Enviar o cronograma", "usuário", MEETING.id, id="a1", for_whom="Carla")],
                         others_actions=[Action("Revisar o mapa", "Ana", MEETING.id, id="a2")])
    analysis.status_updates[3].verification = NO

    written = json.loads(json.dumps(codec.analysis_to_dict(analysis)))

    assert written["my_actions"][0]["for_whom"] == "Carla" and "for_whom" not in written["others_actions"][0]
    first, third, fourth = written["status_updates"][0], written["status_updates"][2], written["status_updates"][3]
    assert set(first) == {"about", "change", "who", "evidence", "at"}
    assert third["new_due"] == "2026-10-16" and "new_owner" not in third
    assert fourth["new_owner"] == "Ana" and fourth["verification"] == {"status": "unconfirmed", "reason": NO.reason}
    assert codec.analysis_from_dict(written) == analysis


# --- verifier (UT-052, UT-057, UT-058, UT-059) -------------------------------------------------------------------
def test_each_status_update_is_a_claim_keyed_by_position_with_its_fields():
    found = [c for c in claims(_analysis()) if c.ref.kind is ClaimKind.STATUS_UPDATE]

    assert [c.ref for c in found] == [ClaimRef(ClaimKind.STATUS_UPDATE, str(i)) for i in range(4)]
    assert found[0].text == 'done: timesheet de outubro — "o timesheet eu já subi"'
    assert (found[0].owner, found[0].due, found[0].at) == (Llm.OWNER_SELF, None, "00:02:55")
    assert (found[2].text, found[2].owner, found[2].due, found[2].at) == (
        'due_changed: cronograma do go-live — "o cronograma eu fecho hoje à tarde"', Llm.OWNER_SELF, date(2026, 10, 16), "00:05:02")
    assert claim_refs(_analysis())[-4:] == [c.ref for c in found]   # after decisions, actions, deadlines and participants


def test_a_reassignment_names_the_new_owner_and_an_unknown_owner_is_not_an_owner():
    update = StatusUpdate("relatório de testes", StatusChange.REASSIGNED, Llm.OWNER_UNKNOWN, "passa para a Ana", new_owner="Ana")
    analysis = Analysis(meeting_id="m", summary="s", status_updates=[update])

    claim = claims(analysis)[0]
    sent = claims_of(analysis, "Felipe")[0]

    assert claim.text == 'reassigned to Ana: relatório de testes — "passa para a Ana"'
    assert sent.owner is None and claims_of(_analysis(), "Felipe")[0].owner == "Felipe"
    assert claims_of(_analysis())[2].due == "2026-10-16"   # the date_said axis applies


def test_the_verdict_maps_back_by_position_and_an_intention_planted_as_done_is_unconfirmed():
    planted = StatusUpdate("timesheet de outubro", StatusChange.DONE, Llm.OWNER_SELF, "vou subir o timesheet", "00:01:00")
    analysis = Analysis(meeting_id=MEETING.id, summary="s", status_updates=[planted, _updates()[1]])
    claim = claims_of(analysis, "Felipe")[0]
    verdict = VerdictOut(id="c1", support="unsupported", owner_evident=True, date_said=None, tentative=False, sensitive=False,
                         reason="  é uma intenção,\nnão um fato ")

    verification = to_verification(claim, verdict)
    verified = with_verifications(analysis, {ClaimRef(ClaimKind.STATUS_UPDATE, "0"): verification})

    assert verification == Verification(VerificationStatus.UNCONFIRMED, "é uma intenção, não um fato")
    assert verified.status_updates[0].verification == verification and verified.status_updates[1].verification is None
    assert analysis.status_updates[0].verification is None   # the analysis passed in is untouched
    line = MarkdownMinutesRenderer("Felipe").render(MEETING, verified)
    assert 'Você: concluído — timesheet de outubro · "vou subir o timesheet" [00:01:00] ⚠️ não confirmado: é uma intenção, não um fato' in line
    assert Minutes.UNCONFIRMED_LEGEND in line


def test_a_new_date_the_transcript_does_not_say_makes_the_update_unconfirmed():
    claim = claims_of(_analysis(), "Felipe")[2]
    assert claim.due == "2026-10-16"
    wrong = VerdictOut(id="c1", support="supported", owner_evident=True, date_said=False, tentative=False, sensitive=False, reason="outra data")
    assert to_verification(claim, wrong).status is VerificationStatus.UNCONFIRMED


def test_the_verifier_message_carries_the_change_the_quote_and_the_new_date():
    claim = claims_of(_analysis(), "Felipe")[2]

    line = describe(claim)

    assert 'due_changed: cronograma do go-live — "o cronograma eu fecho hoje à tarde"' in line and "(status_update)" in line
    assert "| date: 2026-10-16" in line and "| owner: Felipe" in line and "| cited at 00:05:02" in line

    class Transport:
        calls: list[dict] = []

        def complete(self, system, user, schema, *, tag, extra=None):
            self.calls.append({"user": user})
            return VerifyOut(verdicts=[VerdictOut(id="c3", support="supported", owner_evident=True, date_said=True, tentative=False,
                                                   sensitive=False, reason="ok")])

    transport = Transport()
    result = ClaudeClaimVerifier(transport, system_prompt="SYS", user_name="Felipe").verify(
        MEETING, _analysis(), Transcript([Segment(0, 3, "o cronograma eu fecho hoje à tarde")]))
    assert describe(claims_of(_analysis(), "Felipe")[2]) in transport.calls[0]["user"]
    assert result[ClaimRef(ClaimKind.STATUS_UPDATE, "2")].status is VerificationStatus.CONFIRMED
    assert result[ClaimRef(ClaimKind.STATUS_UPDATE, "0")] == Verification(VerificationStatus.UNCONFIRMED, Minutes.REASON_NO_VERDICT)


def test_the_verifier_prompt_names_the_two_axes_of_a_status_update():
    prompt = (load_settings().prompts_dir / Files.VERIFY_PROMPT).read_text(encoding="utf-8")
    assert "status_update" in prompt and "intention" in prompt and "does not support `done`" in prompt
    assert "that new date or that new owner" in prompt and "`date_said`" in prompt


# --- minutes (UT-054) --------------------------------------------------------------------------------------------
def test_the_minutes_list_the_status_updates_after_the_actions_in_the_shape_of_the_dx():
    analysis = _analysis(my_actions=[Action("Enviar o cronograma", "usuário", MEETING.id)], risks=["Escopo indefinido"])
    analysis.status_updates[3].verification = NO
    analysis.status_updates[0].verification = YES

    md = MarkdownMinutesRenderer("Felipe").render(MEETING, analysis)

    assert "\n".join(md.split("### 🔄 Andamento informado\n")[1].splitlines()[:4]) == "\n".join([
        '- Você: concluído — timesheet de outubro · "o timesheet eu já subi" [00:02:55]',
        '- Diego: concluído — conversão de unidade no relatório de estoque · "o fix já tá em homologação" [00:06:40]',
        '- Você: prazo alterado — cronograma do go-live (nova data sex 16/10) · "o cronograma eu fecho hoje à tarde" [00:05:02]',
        '- Rafael: reatribuído — relatório de testes (para Ana) · "passa o relatório para a Ana" [00:12:04] ⚠️ não confirmado: a frase não aparece nesse trecho',
    ])
    assert md.index("### 📌 Ações") < md.index("### 🔄 Andamento informado") < md.index("### ⚠️ Riscos e bloqueios")
    assert Minutes.UNCONFIRMED_LEGEND in md


def test_other_changes_and_missing_pieces_render_without_gaps():
    updates = [
        StatusUpdate("deploy da API", StatusChange.BLOCKED, Llm.OWNER_UNKNOWN, "estou esperando o acesso"),
        StatusUpdate("migração", StatusChange.DELAYED, "Ana", "só consigo na segunda", "00:01:00", new_due=date(2026, 10, 19)),
        StatusUpdate("migração", StatusChange.DELAYED, "Ana", "vai atrasar", "00:01:30"),
        StatusUpdate("piloto", StatusChange.CANCELLED, "Ana", "não precisa mais", "00:02:00", verification=Verification(VerificationStatus.UNCONFIRMED)),
        StatusUpdate("revisão", StatusChange.IN_PROGRESS, Llm.OWNER_SELF, "estou em cima", "00:03:00"),
    ]

    lines = MarkdownMinutesRenderer().render(MEETING, Analysis(meeting_id="m", summary="s", status_updates=updates)).splitlines()
    section = lines[lines.index("### 🔄 Andamento informado") + 1:][:5]

    assert section == [
        '- Alguém: bloqueado — deploy da API · "estou esperando o acesso"',
        '- Ana: atrasado — migração (nova data seg 19/10) · "só consigo na segunda" [00:01:00]',
        '- Ana: atrasado — migração · "vai atrasar" [00:01:30]',
        '- Ana: cancelado — piloto · "não precisa mais" [00:02:00] ⚠️ não confirmado',
        '- Você: em andamento — revisão · "estou em cima" [00:03:00]',
    ]


def test_without_status_updates_the_minutes_have_no_section():
    assert "Andamento" not in MarkdownMinutesRenderer().render(MEETING, Analysis(meeting_id="m", summary="s"))

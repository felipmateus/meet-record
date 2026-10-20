"""ClaudeCurator: the user message, the strict schema, the mapping to CuratorOutput, the repair call, and the same answer
through both transports (the API with a fake client, Claude Code with `tests/fixtures/fake_claude_cli.py`)."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from teams_recorder.adapters.outbound.curator_claude import (
    ClaudeCurator,
    CuratorOut,
    OpOut,
    RepairOut,
    build_repair_message,
    build_user_message,
    to_output,
)
from teams_recorder.adapters.outbound.llm_schema import strict_schema
from teams_recorder.adapters.outbound.llm_transport import ApiTransport, ClaudeCodeTransport
from teams_recorder.application.use_cases.activities import doc_format
from teams_recorder.domain import (
    Action,
    Analysis,
    AnalysisError,
    CuratorInput,
    CuratorOutput,
    Deadline,
    Decision,
    IgnoredRef,
    MeetingContext,
    Op,
    OpFailure,
    OpKind,
    RemovedItem,
    StatusChange,
    StatusUpdate,
    TranscriptHealth,
    Verification,
    VerificationStatus,
    apply_ops,
)
from teams_recorder.messages import Err, Prompt
from tests.fixtures.curator_example import ANSWER, DOCUMENT, MEETING_ID, example_input

FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_claude_cli.py"


class FakeTransport:
    name = "fake"

    def __init__(self, *outs: Any) -> None:
        self.outs = list(outs)
        self.calls: list[dict[str, Any]] = []

    def complete(self, system, user, schema, *, tag, extra=None):
        self.calls.append({"system": system, "user": user, "schema": schema, "tag": tag, "extra": extra})
        return self.outs.pop(0) if len(self.outs) > 1 else self.outs[0]


def _second_meeting() -> MeetingContext:
    analysis = Analysis(
        meeting_id="2026-10-19_14-00-03", summary="Revisão.", title="Revisão de sprint",
        my_actions=[Action("Enviar a ata", "usuário", "2026-10-19_14-00-03", due=date(2026, 10, 21), at="00:01:00", for_whom="Carla",
                           verification=Verification(VerificationStatus.UNCONFIRMED, "não ficou claro que era para você"))],
        deadlines=[Deadline("Go-live do piloto", date(2026, 10, 30), "indefinido",
                            Verification(VerificationStatus.CONFIRMED, "dito"))],
        decisions=[Decision("Adiar a migração.", "00:02:00", Verification(VerificationStatus.UNCONFIRMED, ""))],
        open_questions=["Quem assina o aceite?"], risks=["Sem acesso ao PRD"], next_meetings=["Cliente, ter 27/10 às 10:00"],
        status_updates=[StatusUpdate("o relatório de testes", StatusChange.REASSIGNED, "Rafael", "passa o relatório para a Ana",
                                     at="00:03:00", new_owner="Ana", verification=Verification(VerificationStatus.UNCONFIRMED, "a frase não aparece"))],
    )
    health = TranscriptHealth(loop_share=0.4, covered_minutes=10, total_minutes=30, degraded=True, rate_mismatch=True)
    return MeetingContext("2026-10-19_14-00-03", 'Revisão "de" sprint', analysis, health, "[00:02:58] Rafael: Passa o relatório para a Ana.")


def _two_meetings() -> CuratorInput:
    data = example_input()
    return replace(data, meetings=[*data.meetings, _second_meeting()], box_lines=["- [ ] Pagar a licença"])


# --- the user message -------------------------------------------------------------------------------------------
def test_the_message_has_every_part_in_order_and_the_meetings_oldest_first():
    message = build_user_message(_two_meetings())

    tags = ["<document>", '<meeting n="1"', '<meeting n="2"', "<excerpts>", "<calendar>", "<user_edits>", "<box_lines>", "<last_pass>", "<recent_archive>", "<task>"]
    positions = [message.index(tag) for tag in tags]
    assert positions == sorted(positions) and len(set(positions)) == len(tags)
    for name in ("document", "excerpts", "calendar", "user_edits", "box_lines", "last_pass", "recent_archive", "task"):
        assert len(re.findall(rf"^<{name}>$", message, re.M)) == 1 and len(re.findall(rf"^</{name}>$", message, re.M)) == 1
    assert message.startswith("User (recording owner): Felipe\nNow: seg 19/10/2026 10:12\n<document>\n# Atividades")
    assert DOCUMENT.rstrip("\n") in message                      # the document as on disk, box and link block included
    assert "- [ ] Pagar a licença" in message.split("<box_lines>")[1]
    assert "2 ações novas, 1 aguardando" in message.split("<last_pass>")[1]
    assert "data passou (qui 15/10)" in message.split("<recent_archive>")[1]
    assert Prompt.CURATE_TASK in message.split("<task>")[1]


def test_a_meeting_block_lists_every_kind_of_ref_with_its_time_and_unconfirmed_reason():
    message = build_user_message(_two_meetings())
    first = message.split('<meeting n="1"')[1].split("</meeting>")[0]
    second = message.split('<meeting n="2"')[1].split("</meeting>")[0]

    assert first.startswith(' id="2026-10-19_09-30-11" title="Daily" when="19/10/2026 09:30">')
    assert "health" not in first.split("\n")[0]
    assert "\n1.a1 Validar a carga de materiais no QAS | due: 2026-10-20 | for: time de dados | at: 00:07:30\n" in first
    assert "1.o1 Liberar o acesso do Felipe ao SAP PRD | owner: Bruno | due: 2026-10-21 | at: 00:09:10 | ⚠️ unconfirmed: não ficou claro que o Bruno assumiu o pedido" in first
    assert '1.u1 due_changed: o cronograma do go-live | who: usuário | new date: 2026-10-19 | quote: "o cronograma eu fecho hoje à tarde" | at: 00:05:02' in first
    assert "1.d1 A carga inicial usa a planilha de sexta, não o extrato do SAP. | at: 00:10:40" in first

    assert second.split("\n")[0] == ' id="2026-10-19_14-00-03" title="Revisão \'de\' sprint" when="19/10/2026 14:00" health="degraded, wrong_sample_rate">'
    assert second.split("\n")[1:] == [
        "2.a1 Enviar a ata | due: 2026-10-21 | for: Carla | at: 00:01:00 | ⚠️ unconfirmed: não ficou claro que era para você",
        '2.u1 reassigned: o relatório de testes | who: Rafael | new owner: Ana | quote: "passa o relatório para a Ana" | at: 00:03:00 | ⚠️ unconfirmed: a frase não aparece',
        "2.p1 Go-live do piloto | date: 2026-10-30 | who: indefinido",
        "2.n1 Cliente, ter 27/10 às 10:00",
        "2.d1 Adiar a migração. | at: 00:02:00 | ⚠️ unconfirmed",
        "2.q1 Quem assina o aceite?",
        "2.r1 Sem acesso ao PRD",
        "",
    ]


def test_the_excerpts_are_numbered_by_meeting_and_empty_parts_say_none():
    message = build_user_message(_two_meetings())
    excerpts = message.split("<excerpts>")[1].split("</excerpts>")[0]
    assert '<excerpt n="1">\n[00:02:50] Marina: E o timesheet, Felipe?' in excerpts
    assert '<excerpt n="2">\n[00:02:58] Rafael: Passa o relatório para a Ana.\n</excerpt>' in excerpts

    quiet = replace(example_input(), meetings=[replace(example_input().meetings[0], excerpts="")], user_edits="", box_lines=[],
                    last_summary=None, recent_archive=[], user_name="")
    bare = build_user_message(quiet)
    assert bare.startswith("Now: seg 19/10/2026 10:12\n<document>")           # no user name, no header line for it
    for name in ("excerpts", "user_edits", "box_lines", "last_pass", "recent_archive"):
        assert f"<{name}>\n(none)\n</{name}>" in bare


def test_an_id_that_is_not_a_timestamp_has_no_when_and_a_healthy_transcript_no_health():
    meeting = replace(example_input().meetings[0], meeting_id="m1", health=TranscriptHealth(0.0, 30, 30, degraded=False))
    message = build_user_message(replace(example_input(), meetings=[meeting]))
    assert '<meeting n="1" id="m1" title="Daily">' in message


def test_the_repair_message_carries_the_current_text_and_each_failure_with_its_reason():
    data = example_input()
    failures = [
        OpFailure(0, Op(OpKind.REPLACE, "- [ ] Linha que não existe", "- [ ] Outra", refs=("1.u1",)), "not found"),
        OpFailure(3, Op(OpKind.REPLACE, "- [ ] A\n- [x] B", "- [ ] A", refs=()), "breaks the checkbox rule", "target: 1 open, 1 ticked; text: 1 open, 0 ticked"),
        OpFailure(5, Op(OpKind.MOVE, "- [ ] A", anchor="- [ ] Z"), "anchor found 2 times"),
    ]
    message = build_repair_message(data, "TEXTO ATUAL\n", failures)

    order = [message.index(tag) for tag in ("<document>", "<calendar>", "<failed_edits>", "<task>")]
    assert order == sorted(order)
    assert "<document>\nTEXTO ATUAL\n</document>" in message
    assert Prompt.CURATE_REPAIR_TASK in message
    failed = message.split("<failed_edits>")[1].split("</failed_edits>")[0]
    assert '[0] not found\n{"op":"replace","target":"- [ ] Linha que não existe","text":"- [ ] Outra","reason":null,"anchor":null,"refs":["1.u1"]}' in failed
    assert "[3] breaks the checkbox rule (target: 1 open, 1 ticked; text: 1 open, 0 ticked)\n" in failed
    assert '[5] anchor found 2 times\n{"op":"move","target":"- [ ] A","text":null,"reason":null,"anchor":"- [ ] Z","refs":[]}' in failed
    assert "<meeting" not in message and "<excerpts>" not in message          # the repair does not resend the meetings


# --- the strict schema and the mapping --------------------------------------------------------------------------
def _objects(schema: dict[str, Any]) -> list[dict[str, Any]]:
    found = [schema] if schema.get("type") == "object" else []
    return found + [d for d in schema.get("$defs", {}).values() if d.get("type") == "object"]


@pytest.mark.parametrize("model", [CuratorOut, RepairOut])
def test_the_generated_schema_is_strict_at_every_object_level(model):
    schema = strict_schema(model)
    objects = _objects(schema)
    assert len(objects) >= 2
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])
    op = schema["$defs"]["OpOut"]
    assert set(op["required"]) == {"op", "target", "text", "reason", "anchor", "refs"}
    assert {"type": "null"} in op["properties"]["text"]["anyOf"] and {"type": "null"} in op["properties"]["anchor"]["anyOf"]
    assert set(schema["$defs"]["OpKind"]["enum"]) == {"replace", "insert_after", "move", "archive"}
    assert set(strict_schema(CuratorOut)["required"]) == {"ops", "user_removed", "focus", "summary", "notify", "ignored"}
    assert strict_schema(RepairOut)["required"] == ["ops"]


SCRIPTED = {
    "ops": [
        {"op": "replace", "target": "- [ ] A", "text": "- [ ] A2", "reason": None, "anchor": None, "refs": ["1.u1"]},
        {"op": "insert_after", "target": "## Minhas ações", "text": "- [ ] Nova", "reason": None, "anchor": None, "refs": ["1.a1", "1.a2"]},
        {"op": "move", "target": "- [x] B", "text": None, "reason": None, "anchor": "- [ ] C", "refs": []},
        {"op": "archive", "target": "- [x] D ✔ qui 15/10", "text": None, "reason": "concluído", "anchor": None, "refs": []},
        {"op": "replace", "target": "- [ ] E", "text": "", "reason": None, "anchor": None, "refs": []},
    ],
    "user_removed": [{"text": "- [ ] Item apagado\n  - sub-linha", "note": "  apagado   por você  "}],
    "focus": ["**A**: vence hoje, seg 19/10.", "   ", "**B**:  amanhã,\nter 20/10."],
    "summary": "1 ação nova,\n1 possível conclusão ",
    "notify": True,
    "ignored": [{"ref": " 1.o2 ", "why": "não afeta você"}],
}


def test_a_scripted_answer_maps_field_by_field_and_nulls_become_none():
    out = to_output(CuratorOut.model_validate(SCRIPTED))

    assert out == CuratorOutput(
        ops=[
            Op(OpKind.REPLACE, "- [ ] A", text="- [ ] A2", refs=("1.u1",)),
            Op(OpKind.INSERT_AFTER, "## Minhas ações", text="- [ ] Nova", refs=("1.a1", "1.a2")),
            Op(OpKind.MOVE, "- [x] B", anchor="- [ ] C"),
            Op(OpKind.ARCHIVE, "- [x] D ✔ qui 15/10", reason="concluído"),
            Op(OpKind.REPLACE, "- [ ] E", text=""),
        ],
        user_removed=[RemovedItem("- [ ] Item apagado\n  - sub-linha", "apagado por você")],
        focus=["**A**: vence hoje, seg 19/10.", "**B**: amanhã, ter 20/10."],
        summary="1 ação nova, 1 possível conclusão",
        notify=True,
        ignored=[IgnoredRef("1.o2", "não afeta você")],
    )
    move, archive = out.ops[2], out.ops[3]
    assert move.text is None and move.reason is None and archive.anchor is None and archive.text is None
    assert out.ops[4].text == ""                         # an empty replace text removes the lines; it is not a null
    assert isinstance(out.ops[0].refs, tuple)


def test_an_answer_missing_the_optional_fields_still_validates():
    out = CuratorOut.model_validate({"ops": [{"op": "archive", "target": "- [x] A", "reason": "concluído"}], "summary": "", "notify": False})
    assert to_output(out).ops == [Op(OpKind.ARCHIVE, "- [x] A", reason="concluído")]
    assert to_output(out).focus == [] and to_output(out).ignored == []


def test_an_answer_without_ops_is_a_schema_violation_not_an_empty_pass():
    with pytest.raises(ValueError):
        CuratorOut.model_validate({"summary": "", "notify": False})
    with pytest.raises(ValueError):
        RepairOut.model_validate({"summary": 42})


def test_the_worked_example_answer_is_a_valid_curator_answer_that_applies_cleanly():
    out = to_output(CuratorOut.model_validate(ANSWER))
    applied = apply_ops(doc_format(), DOCUMENT, out.ops)
    assert applied.failures == () and len(applied.archived) == 1 and out.notify


# --- the calls --------------------------------------------------------------------------------------------------
def test_curate_sends_the_message_with_the_schema_and_the_tag_of_the_first_meeting():
    transport = FakeTransport(CuratorOut.model_validate(SCRIPTED))
    curator = ClaudeCurator(transport, system_prompt="SYS")
    data = _two_meetings()

    out = curator.curate(data)

    call = transport.calls[0]
    assert call["system"] == "SYS" and call["schema"] is CuratorOut
    assert call["user"] == build_user_message(data)
    assert call["tag"] == f"curate:{MEETING_ID}" and call["extra"] == {"meeting": MEETING_ID}
    assert out.summary == "1 ação nova, 1 possível conclusão" and len(out.ops) == 5


def test_repair_sends_the_text_and_the_failures_and_returns_only_ops():
    transport = FakeTransport(RepairOut(ops=[OpOut(op=OpKind.REPLACE, target="- [ ] A", text="- [ ] A2", refs=["1.u1"])]))
    curator = ClaudeCurator(transport, system_prompt="SYS")
    failures = [OpFailure(1, Op(OpKind.ARCHIVE, "- [ ] Falta", reason="x"), "found 2 times")]

    ops = curator.repair(_two_meetings(), "TEXTO EM MEMÓRIA\n", failures)

    assert ops == [Op(OpKind.REPLACE, "- [ ] A", text="- [ ] A2", refs=("1.u1",))]
    call = transport.calls[0]
    assert call["schema"] is RepairOut
    assert call["user"] == build_repair_message(_two_meetings(), "TEXTO EM MEMÓRIA\n", failures)
    assert "TEXTO EM MEMÓRIA" in call["user"] and "found 2 times" in call["user"] and "- [ ] Falta" in call["user"]
    assert call["tag"] == f"curate-repair:{MEETING_ID}" and call["extra"] == {"meeting": MEETING_ID}


def test_the_prompt_is_loaded_lazily_from_its_path(tmp_path: Path):
    path = tmp_path / "curate.md"
    path.write_text("  PROMPT FROM FILE\n", encoding="utf-8")
    transport = FakeTransport(CuratorOut.model_validate(SCRIPTED))
    curator = ClaudeCurator(transport, prompt_path=path)

    curator.curate(example_input())
    path.unlink()
    curator.curate(example_input())                      # read once, kept

    assert [c["system"] for c in transport.calls] == ["PROMPT FROM FILE", "PROMPT FROM FILE"]
    with pytest.raises(AnalysisError, match="ClaudeCurator"):
        ClaudeCurator(transport).curate(example_input())
    with pytest.raises(AnalysisError, match=Err.PROMPT_MISSING.split("{")[0].strip()):
        ClaudeCurator(transport, prompt_path=tmp_path / "missing.md").curate(example_input())


# --- both transports --------------------------------------------------------------------------------------------
def _resp(text: str, stop: str = "end_turn", **extra: Any) -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=1000, cache_creation_input_tokens=0)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop, model="claude-opus-5-5", usage=usage, _request_id="req_1", **extra)


class Client:
    def __init__(self, *responses: SimpleNamespace) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw: Any) -> SimpleNamespace:
        self.calls.append(kw)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


class ScriptedCli(ClaudeCodeTransport):
    def command(self, system, schema):
        return [sys.executable, str(FAKE)] + super().command(system, schema)[1:]


def test_the_same_answer_through_the_api_and_through_claude_code_gives_the_same_output(tmp_path: Path, monkeypatch):
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps(ANSWER, ensure_ascii=False), encoding="utf-8")
    record = tmp_path / "record.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT_FILE", str(answer))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    data = example_input()

    via_api = ClaudeCurator(ApiTransport(client=Client(_resp(json.dumps(ANSWER, ensure_ascii=False)))), system_prompt="SYS").curate(data)
    via_cli = ClaudeCurator(ScriptedCli(claude_bin=sys.executable), system_prompt="SYS").curate(data)

    assert via_cli == via_api == to_output(CuratorOut.model_validate(ANSWER))
    sent = json.loads(record.read_text(encoding="utf-8").splitlines()[0])
    assert sent == {"system": "SYS", "user": build_user_message(data)}


def test_a_repair_through_claude_code_returns_the_ops_and_logs_both_tags(tmp_path: Path, monkeypatch):
    bad = {"ops": [{"op": "replace", "target": "- [ ] Não existe", "text": "- [ ] X", "reason": None, "anchor": None, "refs": ["1.u1"]}],
           "user_removed": [], "focus": ["**A**: hoje."], "summary": "1 edição", "notify": False, "ignored": []}
    fixed = {"ops": [{"op": "replace", "target": "- [ ] Ligar para o suporte da VPN", "text": "- [ ] Ligar para o suporte da VPN", "reason": None, "anchor": None, "refs": []}]}
    script = tmp_path / "script.json"
    script.write_text(json.dumps([bad, fixed]), encoding="utf-8")
    record = tmp_path / "record.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    usage = tmp_path / "usage.jsonl"
    curator = ClaudeCurator(ScriptedCli(claude_bin=sys.executable, usage_log=usage), system_prompt="SYS")
    data = example_input()

    first = curator.curate(data)
    failures = apply_ops(doc_format(), DOCUMENT, first.ops).failures
    assert [f.error for f in failures] == ["not found"]
    ops = curator.repair(data, DOCUMENT, list(failures))

    assert ops == [Op(OpKind.REPLACE, "- [ ] Ligar para o suporte da VPN", text="- [ ] Ligar para o suporte da VPN")]
    messages = [json.loads(line)["user"] for line in record.read_text(encoding="utf-8").splitlines()]
    assert messages[1] == build_repair_message(data, DOCUMENT, list(failures)) and "- [ ] Não existe" in messages[1]
    tags = [json.loads(line)["tag"] for line in usage.read_text(encoding="utf-8").splitlines()]
    assert tags == [f"curate:{MEETING_ID}", f"curate-repair:{MEETING_ID}"]


def test_the_api_usage_log_carries_the_curate_and_repair_tags(tmp_path: Path):
    client = Client(_resp(json.dumps(ANSWER, ensure_ascii=False)), _resp(json.dumps({"ops": []})))
    curator = ClaudeCurator(ApiTransport(client=client, usage_log=tmp_path / "u.jsonl", effort="medium"), system_prompt="SYS")

    curator.curate(example_input())
    assert curator.repair(example_input(), DOCUMENT, [OpFailure(0, Op(OpKind.ARCHIVE, "x"), "not found")]) == []

    entries = [json.loads(line) for line in (tmp_path / "u.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(e["tag"], e["meeting"], e["provider"]) for e in entries] == [
        (f"curate:{MEETING_ID}", MEETING_ID, "api"), (f"curate-repair:{MEETING_ID}", MEETING_ID, "api"),
    ]
    schemas = [call["output_config"]["format"]["schema"] for call in client.calls]
    assert schemas[0]["required"] == ["ops", "user_removed", "focus", "summary", "notify", "ignored"] and schemas[1]["required"] == ["ops"]
    assert client.calls[0]["system"][0]["text"] == "SYS" and client.calls[0]["messages"][0]["content"] == build_user_message(example_input())


@pytest.mark.parametrize("call", ["curate", "repair"])
def test_a_refusal_a_truncation_and_a_schema_violation_are_analysis_errors(call: str):
    def run(response: SimpleNamespace) -> Any:
        curator = ClaudeCurator(ApiTransport(client=Client(response)), system_prompt="SYS")
        if call == "curate":
            return curator.curate(example_input())
        return curator.repair(example_input(), DOCUMENT, [OpFailure(0, Op(OpKind.ARCHIVE, "x"), "not found")])

    details = SimpleNamespace(category="cyber", explanation="x")
    with pytest.raises(AnalysisError, match="refused.*cyber"):
        run(_resp("", "refusal", stop_details=details))
    with pytest.raises(AnalysisError, match="truncated"):
        run(_resp('{"ops": [', "max_tokens"))
    with pytest.raises(AnalysisError, match="does not match the schema"):
        run(_resp(json.dumps({"ops": [{"op": "delete", "target": "x"}], "summary": "", "notify": False})))
    with pytest.raises(AnalysisError, match="does not match the schema"):
        run(_resp(json.dumps({"ops": "not a list"})))


@pytest.mark.parametrize("mode,match", [("error", "error_during_execution.*Not logged in"), ("bad_schema", "does not match the schema")])
def test_claude_code_errors_surface_as_analysis_errors(tmp_path: Path, monkeypatch, mode: str, match: str):
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps(ANSWER, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT_FILE", str(answer))
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    curator = ClaudeCurator(ScriptedCli(claude_bin=sys.executable), system_prompt="SYS")
    with pytest.raises(AnalysisError, match=match):
        curator.curate(example_input())
    with pytest.raises(AnalysisError, match=match):
        curator.repair(example_input(), DOCUMENT, [OpFailure(0, Op(OpKind.ARCHIVE, "x"), "not found")])


def test_the_curator_module_imports_only_the_allowed_adapters_and_not_the_sdk():
    import ast

    path = Path(__file__).resolve().parents[2] / "src" / "teams_recorder" / "adapters" / "outbound" / "curator_claude.py"
    imported = [n.module for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.ImportFrom) and n.module]
    adapters = {m for m in imported if m.startswith("teams_recorder.adapters")}
    assert adapters == {"teams_recorder.adapters.outbound.llm_schema", "teams_recorder.adapters.outbound.llm_transport"}
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) and "anthropic" in ast.dump(n) for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))))

"""Deterministic parts of the evaluation harness (scripts/wiki_corpus.py, scripts/fidelity_eval.py).

The model calls are not tested here: these are the pieces the reported numbers rest on (text
normalization, word error rate, the code checks, the injected errors, the parsers).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fidelity_eval as fe  # noqa: E402
import wiki_corpus as wc  # noqa: E402

TRANSCRIPT = [
    (0.0, "Bom dia, Carla. Vamos começar."),
    (30.0, "O prazo da fase dois é treze de fevereiro."),
    (95.0, "Talvez o relatório fique para a fase três, preciso confirmar."),
    (200.0, "Felipe, você manda o cronograma até sexta?"),
    (205.0, "Pode deixar, eu mando."),
]


def test_words_turns_spoken_numbers_into_digits_and_drops_accents():
    assert fe.words("Quarenta e cinco veículos") == ["45", "veiculos"]
    assert fe.words("[00:00:01] Treze de Fevereiro, fase dois") == ["13", "de", "fevereiro", "fase", "2"]


def test_wer_counts_substitutions_insertions_and_deletions():
    assert fe.wer(["a", "b", "c", "d"], ["a", "b", "c", "d"]) == 0
    assert fe.wer(["a", "b", "c", "d"], ["a", "x", "c", "d"]) == 0.25
    assert fe.wer(["a", "b"], ["a", "b", "c", "d"]) == 1.0


def test_seconds_and_window():
    assert fe.seconds("01:02:03") == 3723
    assert fe.seconds(None) is None and fe.seconds("1:2") is None
    win = fe.window(TRANSCRIPT, "00:03:20", radius=10)
    assert "cronograma" in win and "eu mando" in win and "treze" not in win
    assert fe.window(TRANSCRIPT, None).count("\n") == len(TRANSCRIPT) - 1


def test_extract_claims_covers_every_checkable_field_and_names_the_user():
    analysis = {
        "meeting_id": "2026-01-05_10-00-00",
        "decisions": [{"text": "Usar o Mapbox", "at": "00:00:30"}, "decisão antiga em texto puro"],
        "my_actions": [{"description": "Enviar o cronograma", "owner": "usuário", "due": "2026-01-09", "at": "00:03:20"}],
        "others_actions": [{"description": "Mandar a chave", "owner": "Carla", "due": None, "at": None}],
        "deadlines": [{"what": "Fase 2", "when": "2026-02-13", "who": "usuário"}],
        "participants": ["Carla"], "topics": [{"title": "t", "points": ["ponto um"]}], "risks": ["risco"],
    }
    claims = fe.extract_claims(analysis)
    assert [c["type"] for c in claims] == ["decision", "decision", "action", "action", "deadline", "participant", "statement", "statement"]
    assert claims[2]["owner"] == "Felipe" and claims[4]["owner"] == "Felipe"
    assert len({c["id"] for c in claims}) == len(claims)


def claim(**fields):
    return {"id": "x", "meeting": "2026-01-05_10-00-00", "source": "original", **fields}


def test_code_checks_flag_a_date_nobody_said_and_accept_a_spoken_weekday():
    said = claim(type="action", text="Mandar o cronograma", owner="Felipe", due="2026-01-09", at="00:03:20")
    invented = claim(type="action", text="Mandar o cronograma", owner="Felipe", due="2026-01-21", at="00:00:30")
    assert "date_unsupported" not in fe.l2_flags(said, TRANSCRIPT)
    assert "date_unsupported" in fe.l2_flags(invented, TRANSCRIPT)


def test_code_checks_on_owners():
    user_took_it = claim(type="action", text="Mandar o cronograma", owner="Felipe", at="00:03:25")
    other_person = claim(type="action", text="Mandar o cronograma", owner="Bruno", at="00:03:25")
    assert "owner_unconfirmed" not in fe.l2_flags(user_took_it, TRANSCRIPT)
    assert "owner_unconfirmed" in fe.l2_flags(other_person, TRANSCRIPT)


def test_code_checks_flag_tentative_decisions_sensitive_data_and_unsupported_text():
    tentative = claim(type="decision", text="O relatório fica para a fase 3", at="00:01:35")
    sensitive = claim(type="statement", text="Bruno faltou por consulta médica de rotina")
    fabricated = claim(type="decision", text="Contratar consultoria externa para arquitetura", at="00:00:30")
    assert "tentative_context" in fe.l2_flags(tentative, TRANSCRIPT)
    assert "sensitive" in fe.l2_flags(sensitive, TRANSCRIPT)
    assert "low_support" in fe.l2_flags(fabricated, TRANSCRIPT)


def test_code_checks_on_participants():
    addressed = claim(type="participant", text="Carla")
    mentioned_nowhere = claim(type="participant", text="Marcos")
    user = claim(type="participant", text="Felipe")
    assert fe.l2_flags(addressed, TRANSCRIPT) == []
    assert fe.l2_flags(mentioned_nowhere, TRANSCRIPT) == ["participant_unconfirmed"]
    assert fe.l2_flags(user, TRANSCRIPT) == []


def test_verifier_verdicts_become_flags():
    action = claim(type="action", text="t", owner="Bruno", due="2026-01-09")
    ok = {"support": "supported", "owner_evident": True, "date_said": True, "tentative": False, "sensitive": False}
    assert fe.l1_flag(action, ok) == []
    assert fe.l1_flag(action, ok | {"support": "partial"}) == ["l1_partial"]
    assert fe.l1_flag(action, ok | {"owner_evident": False, "date_said": False}) == ["l1_owner", "l1_date"]
    assert fe.l1_flag(claim(type="decision", text="t"), ok | {"tentative": True}) == ["l1_tentative"]
    assert fe.l1_flag(action, None) == ["no_verdict"]


def test_corrupt_handover_swaps_who_owns_the_routing_module():
    analysis = {
        "meeting_id": "2026-01-12_09-30-00",
        "decisions": [{"text": "Felipe assume o módulo de rotas e Bruno vai para o WhatsApp", "at": "00:00:40"}],
        "my_actions": [{"description": "Assumir o módulo de rotas", "owner": "usuário"}],
        "others_actions": [{"description": "Cuidar da integração com o WhatsApp", "owner": "Bruno"}],
        "topics": [],
    }
    out = fe.corrupt_handover(analysis)
    assert out["decisions"][0]["text"].startswith("Bruno assume o módulo de rotas e Felipe")
    assert [a["owner"] for a in out["others_actions"]] == ["Bruno"]
    assert out["others_actions"][0]["description"] == "Assumir o módulo de rotas"
    assert [a["description"] for a in out["my_actions"]] == ["Cuidar da integração com o WhatsApp"]
    assert analysis["decisions"][0]["text"].startswith("Felipe")   # the input is not modified


def test_filter_analysis_drops_flagged_claims_only():
    analysis = {"decisions": [{"text": "A"}, {"text": "B"}], "my_actions": [{"description": "C"}], "others_actions": [],
                "deadlines": [], "participants": ["Marcos", "Carla"], "risks": [], "topics": [{"points": ["D", "E"]}]}
    out = fe.filter_analysis(analysis, {"B", "Marcos", "E"})
    assert [d["text"] for d in out["decisions"]] == ["A"] and out["participants"] == ["Carla"] and out["topics"][0]["points"] == ["D"]


def test_cited_wiki_bullets_are_parsed():
    line = "- [ ] Enviar o cronograma — Felipe — prazo 16/01 ([[meetings/2026-01-14_11-00-00|14/01]] 00:01:50)"
    m = fe.CITED.match(line)
    assert m and m.group(2) == "2026-01-14_11-00-00" and m.group(3) == "00:01:50" and m.group(1).startswith("Enviar o cronograma")


def test_answer_checks_accept_alternatives_and_catch_forbidden_text():
    q = {"must_include": [["13/02", "13 de fevereiro"]], "must_not_include": ["cardiolog"], "must_cite": [["2026-01-14", "14/01"]]}
    assert wc.code_checks(q, "O prazo é 13 de Fevereiro (14/01).")[0]
    ok, failures, fabricated = wc.code_checks(q, "Prazo 30/01; ele foi ao cardiologista.")
    assert not ok and fabricated and len(failures) == 3


def test_distractor_filter_and_schedule():
    assert wc.forbidden_hits("só um lembrete: amanhã tem reunião") == []
    assert wc.forbidden_hits("a Ana sai de férias em março")
    assert wc.forbidden_hits("lembrete de consulta por SMS")
    ids = wc.filler_schedule(81)
    planted = {m["id"] for m in wc.load_corpus()["meeting"]}
    assert len(ids) == len(set(ids)) == 81 and not planted & set(ids)


@pytest.mark.parametrize(("message", "expected"), [
    ("You've hit your session limit · resets 11:30pm (America/Sao_Paulo)", ("11", "30", "pm")),
    ("session limit · resets 6pm (America/Sao_Paulo)", ("6", None, "pm")),
])
def test_reset_time_is_read_from_the_limit_message(message, expected):
    import re
    assert re.search(wc.RESET_PATTERN, message).groups() == expected


def test_wait_for_reset_ignores_other_errors():
    assert wc.wait_for_reset("Claude Code returned an error: Not logged in") is False


def test_mark_analysis_keeps_flagged_claims_visible_and_unowned():
    analysis = {"decisions": [{"text": "Usar o Mapbox"}], "my_actions": [{"description": "Testar o SMS", "owner": "usuário"}],
                "others_actions": [{"description": "Mandar a chave", "owner": "Carla"}], "deadlines": [], "participants": ["Rafael", "Carla"],
                "risks": [], "topics": [{"points": ["Bruno faltou por consulta médica"]}]}
    flags = {"Testar o SMS": ["l1_owner"], "Usar o Mapbox": ["l1_partial"], "Rafael": ["participant_unconfirmed"],
             "Bruno faltou por consulta médica": ["sensitive"]}
    out = fe.mark_analysis(analysis, flags)
    assert out["my_actions"][0]["owner"] == "indefinido" and out["my_actions"][0]["description"].endswith("(a confirmar na transcrição)")
    assert out["others_actions"][0] == {"description": "Mandar a chave", "owner": "Carla"}
    assert out["decisions"][0]["text"] == "(a confirmar) Usar o Mapbox"
    assert out["participants"] == ["Carla"] and out["topics"][0]["points"][0].startswith("(a confirmar) ")


def test_story_claims_split_title_sentence_criteria_and_details():
    drafts = {"stories": [{"title": "Lembrete", "narrative": "Como paciente, quero…", "acceptance_criteria": ["Dado A, então B", ""],
                           "details": "- **Dependências:** modelo aprovado pela Meta\n- curto"}]}
    claims = fe.story_claims(drafts)
    assert [c["part"] for c in claims] == ["title", "narrative", "criterion", "detail"]
    assert claims[-1]["text"] == "Dependências:** modelo aprovado pela Meta"   # list markers and leading emphasis stripped


def test_story_claims_judge_cited_criteria_as_the_reviewer_sees_them():
    # since task 5.0 the product stores {text, source}; the judge must see the source, as the board shows it
    drafts = {"stories": [{"title": "t", "narrative": "", "acceptance_criteria": [
        {"text": "Exporta em CSV", "source": "00:00:05"}, {"text": "Também em PDF", "source": "sugestao"}, "Antigo"]}]}
    texts = [c["text"] for c in fe.story_claims(drafts) if c["part"] == "criterion"]
    assert texts == ["Exporta em CSV [00:00:05]", "Também em PDF (sugestão)", "Antigo"]

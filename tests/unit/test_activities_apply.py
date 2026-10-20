"""apply_ops and the checkbox rule (UT-001 to UT-009, UT-019 to UT-024, UT-029, UT-112 to UT-115): table-driven, no fakes."""
from __future__ import annotations

from pathlib import Path

import pytest

from teams_recorder.application.use_cases.activities import doc_format
from teams_recorder.domain import Op, OpKind, apply_ops, body_text, open_count, ticked_count

FMT = doc_format()
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "activities" / "atividades.md"
BOX = f"{FMT.box_start}\n> **Atualizado seg 19/10 10:12** · após Daily\n{FMT.box_end_prefix} 20261019-101200{FMT.box_end_suffix}\n"
LINKS = f"{FMT.links_start}\n[2026-10-16_09-30-11]: ../recordings/2026-10-16_09-30-11/minutes.md\n{FMT.links_end}\n"


def make(body: str) -> str:
    return f"# Atividades\n\n{BOX}\n{body}\n{LINKS}"


BODY = (
    f"{FMT.heading_actions}\n\n"
    "- [ ] **A** · sex 16/10 · [Daily 16/10][2026-10-16_09-30-11]\n"
    "  - nota de A\n"
    "- [ ] **B**\n"
    "- [x] **C** ✔ sex 16/10\n"
    f"\n{FMT.heading_waiting}\n\n"
    "- [ ] **Bruno**: liberar o acesso\n"
)
DOC = make(BODY)


def rep(target: str, text: str) -> Op:
    return Op(OpKind.REPLACE, target, text=text)


def ins(target: str, text: str) -> Op:
    return Op(OpKind.INSERT_AFTER, target, text=text)


def mv(target: str, anchor: str) -> Op:
    return Op(OpKind.MOVE, target, anchor=anchor)


def arc(target: str, reason: str = "duplicado") -> Op:
    return Op(OpKind.ARCHIVE, target, reason=reason)


def errors(applied) -> list[str]:  # noqa: ANN001
    return [f.error for f in applied.failures]


def test_replace_one_line_leaves_the_rest_byte_identical() -> None:                      # UT-001
    out = apply_ops(FMT, DOC, [rep("- [ ] **B**", "- [ ] **B** · ter 20/10")])
    assert out.failures == ()
    assert out.text == DOC.replace("- [ ] **B**\n", "- [ ] **B** · ter 20/10\n")


def test_target_not_found_fails_and_later_ops_still_apply() -> None:                      # UT-002
    out = apply_ops(FMT, DOC, [rep("- [ ] **Z**", "- [ ] **Z** x"), rep("- [ ] **B**", "- [ ] **B** x")])
    assert [(f.index, f.error) for f in out.failures] == [(0, "not found")]
    assert out.text == DOC.replace("- [ ] **B**\n", "- [ ] **B** x\n")


def test_target_found_twice_is_ambiguous() -> None:                                       # UT-003
    doc = make(f"{FMT.heading_actions}\n\n- [ ] **B**\n- [ ] **B**\n")
    out = apply_ops(FMT, doc, [rep("- [ ] **B**", "- [ ] **B** x")])
    assert errors(out) == ["found 2 times"]
    assert out.text == doc


def test_a_replace_that_ticks_fails_with_the_counts() -> None:                            # UT-004
    out = apply_ops(FMT, DOC, [rep("- [ ] **B**", "- [x] **B**")])
    assert errors(out) == ["breaks the checkbox rule"]
    assert out.failures[0].detail == "target: 1 open, 0 ticked; text: 0 open, 1 ticked"
    assert out.text == DOC


def test_removing_an_open_line_needs_archive() -> None:                                   # UT-005
    removed = apply_ops(FMT, DOC, [rep("- [ ] **B**", "")])
    assert errors(removed) == ["breaks the checkbox rule"] and removed.text == DOC
    moved = apply_ops(FMT, DOC, [rep("- [ ] **B**", ""), ins("- [ ] **Bruno**: liberar o acesso", "- [ ] **B**")])
    assert errors(moved) == ["breaks the checkbox rule"]          # the replace fails, so B is not removed and not duplicated by a move
    assert moved.text.count("- [ ] **B**\n") == 2                  # the insert alone applied: the documented way to lose nothing
    archived = apply_ops(FMT, DOC, [arc("- [ ] **B**", "duplicado de: X")])
    assert archived.failures == () and archived.archived == ("- [ ] **B**",) and archived.reasons == ("duplicado de: X",)
    assert archived.text == DOC.replace("- [ ] **B**\n", "")


def test_ops_apply_to_the_document_as_re_read_with_the_users_lines() -> None:             # UT-006
    reread = DOC.replace("- [ ] **B**\n", "- [ ] **B**\n- [ ] Ligar para o João\n")
    out = apply_ops(FMT, reread, [rep("- [ ] **B**", "- [ ] **B** x")])
    assert out.failures == () and "- [ ] Ligar para o João\n" in out.text and "- [ ] **B** x\n" in out.text


def test_targets_in_the_box_or_link_block_are_refused() -> None:                          # UT-007
    in_box = apply_ops(FMT, DOC, [rep("> **Atualizado seg 19/10 10:12** · após Daily", "x")])
    assert errors(in_box) == ["targets the box or link block"] and in_box.text == DOC
    link = "[2026-10-16_09-30-11]: ../recordings/2026-10-16_09-30-11/minutes.md"
    assert errors(apply_ops(FMT, DOC, [rep(link, "x")])) == ["targets the box or link block"]
    both = make(f"{FMT.heading_actions}\n\n> **Atualizado seg 19/10 10:12** · após Daily\n")
    out = apply_ops(FMT, both, [rep("> **Atualizado seg 19/10 10:12** · após Daily", "texto")])
    assert out.failures == () and out.text.count("texto") == 1 and BOX in out.text


def test_an_op_text_cannot_carry_a_marker_line() -> None:
    for text in (FMT.box_start, f"{FMT.box_end_prefix}{FMT.box_end_suffix}", FMT.links_start, FMT.links_end):
        out = apply_ops(FMT, DOC, [ins("- [ ] **B**", text)])
        assert errors(out) == ["targets the box or link block"] and out.text == DOC


def test_150_items() -> None:                                                              # UT-008
    items = "".join(f"- [ ] **Item {n}** · [Daily][2026-10-16_09-30-11]\n" for n in range(150))
    doc = make(f"{FMT.heading_actions}\n\n{items}")
    assert open_count(FMT, doc) == 150 and ticked_count(FMT, doc) == 0
    out = apply_ops(FMT, doc, [rep(f"- [ ] **Item {n}** · [Daily][2026-10-16_09-30-11]", f"- [ ] **Item {n}** · seg 19/10") for n in (0, 77, 149)])
    assert out.failures == () and open_count(FMT, out.text) == 150


def test_trailing_whitespace_is_ignored_and_nothing_else() -> None:                       # UT-009
    doc = make(f"{FMT.heading_actions}\n\n- [ ] **B**   \n- [ ] “aspas”\n")
    assert apply_ops(FMT, doc, [rep("- [ ] **B**", "- [ ] **B** x")]).failures == ()
    assert apply_ops(FMT, doc, [rep("- [ ] **B**\t \n", "- [ ] **B** x")]).failures == ()
    assert errors(apply_ops(FMT, doc, [rep('- [ ] "aspas"', "x")])) == ["not found"]


def test_text_after_the_checkbox_may_change() -> None:                                    # UT-019
    out = apply_ops(FMT, DOC, [
        rep("- [ ] **B**", "- [ ] **B** · ter 20/10 · 💤 sem menção"),
        rep("- [x] **C** ✔ sex 16/10", "- [x] **C** ✔ sex 16/10 [Daily 19/10][2026-10-19_09-30-11]"),
    ])
    assert out.failures == ()


def test_merging_open_lines_by_replace_fails() -> None:                                   # UT-020
    doc = make(f"{FMT.heading_actions}\n\n- [ ] **A**\n- [ ] **A2**\n")
    merged = apply_ops(FMT, doc, [rep("- [ ] **A**\n- [ ] **A2**", "- [ ] **A**")])
    assert errors(merged) == ["breaks the checkbox rule"]
    assert merged.failures[0].detail == "target: 2 open, 0 ticked; text: 1 open, 0 ticked"
    assert errors(apply_ops(FMT, doc, [rep("- [ ] **A**\n- [ ] **A2**", "")])) == ["breaks the checkbox rule"]


@pytest.mark.parametrize("target,text", [("- [ ] **B**", "- [x] **B**\n- [ ] **D**"), ("- [x] **C** ✔ sex 16/10", "- [ ] **C**")])
def test_tick_with_a_new_open_line_and_untick_fail(target: str, text: str) -> None:       # UT-021
    out = apply_ops(FMT, DOC, [rep(target, text)])
    assert errors(out) == ["breaks the checkbox rule"] and out.text == DOC


def test_an_insert_with_a_ticked_line_fails_even_after_an_archive() -> None:               # UT-022
    assert errors(apply_ops(FMT, DOC, [ins("- [ ] **B**", "- [x] **D**")])) == ["breaks the checkbox rule"]
    out = apply_ops(FMT, DOC, [arc("- [ ] **B**"), ins("- [ ] **A** · sex 16/10 · [Daily 16/10][2026-10-16_09-30-11]", "- [x] **B**")])
    assert out.archived == ("- [ ] **B**",) and errors(out) == ["breaks the checkbox rule"] and "- [x] **B**" not in out.text


def test_move_is_byte_exact_and_changes_no_count() -> None:                               # UT-023
    ticked = apply_ops(FMT, DOC, [mv("- [x] **C** ✔ sex 16/10", "- [ ] **Bruno**: liberar o acesso")])
    assert ticked.failures == ()
    assert ticked.text == DOC.replace("- [x] **C** ✔ sex 16/10\n", "").replace(
        "- [ ] **Bruno**: liberar o acesso\n", "- [ ] **Bruno**: liberar o acesso\n- [x] **C** ✔ sex 16/10\n")
    assert (open_count(FMT, ticked.text), ticked_count(FMT, ticked.text)) == (open_count(FMT, DOC), ticked_count(FMT, DOC))
    sunk = apply_ops(FMT, DOC, [mv("- [ ] **A** · sex 16/10 · [Daily 16/10][2026-10-16_09-30-11]\n  - nota de A", "- [x] **C** ✔ sex 16/10")])
    assert sunk.failures == ()
    assert sunk.text.index("- [x] **C**") < sunk.text.index("- [ ] **A**") < sunk.text.index(FMT.heading_waiting)
    assert "  - nota de A\n- [ ] **B**" not in sunk.text and sunk.text.count("\n") == DOC.count("\n")
    as_replace = apply_ops(FMT, DOC, [rep("- [x] **C** ✔ sex 16/10", "")])
    assert errors(as_replace) == ["breaks the checkbox rule"]


def test_drop_b_and_add_c_fails_the_drop_only() -> None:                                  # UT-024
    out = apply_ops(FMT, DOC, [rep("- [ ] **B**", ""), ins("- [ ] **A** · sex 16/10 · [Daily 16/10][2026-10-16_09-30-11]\n  - nota de A", "- [ ] **C novo**")])
    assert [(f.index, f.error) for f in out.failures] == [(0, "breaks the checkbox rule")]
    assert "- [ ] **C novo**\n" in out.text and "- [ ] **B**\n" in out.text


def test_the_rule_is_evaluated_on_the_current_text() -> None:                             # UT-029
    out = apply_ops(FMT, DOC, [
        ins("- [ ] **B**", "- [ ] **D**"),
        rep("- [ ] **D**", "- [ ] **D** · ter 20/10"),
        rep("- [ ] **D** · ter 20/10", "- [x] **D**"),
    ])
    assert [(f.index, f.error) for f in out.failures] == [(2, "breaks the checkbox rule")]
    assert "- [ ] **D** · ter 20/10\n" in out.text


def test_replace_keeping_the_counts_may_change_identity() -> None:                        # UT-112
    doc = make(f"{FMT.heading_actions}\n\n- [ ] **A**\n- [ ] **B**\n")
    out = apply_ops(FMT, doc, [rep("- [ ] **A**\n- [ ] **B**", "- [ ] **A**\n- [ ] **C**")])
    assert out.failures == () and "- [ ] **C**\n" in out.text and "- [ ] **B**" not in out.text


def test_move_to_a_heading_and_ordering_with_inserts() -> None:                           # UT-113
    first = apply_ops(FMT, DOC, [mv("- [ ] **Bruno**: liberar o acesso", FMT.heading_actions)])
    assert first.failures == ()
    lines = first.text.split("\n")
    assert lines[lines.index(FMT.heading_actions) + 1] == "- [ ] **Bruno**: liberar o acesso"
    moved_then_insert = apply_ops(FMT, DOC, [
        mv("- [ ] **Bruno**: liberar o acesso", FMT.heading_actions),
        ins("- [ ] **Bruno**: liberar o acesso", "  - 💬 sugestão"),
    ])
    assert moved_then_insert.failures == () and "- [ ] **Bruno**: liberar o acesso\n  - 💬 sugestão\n" in moved_then_insert.text
    insert_then_move = apply_ops(FMT, DOC, [
        ins("- [ ] **B**", "  - 💬 sugestão"),
        mv("- [ ] **B**\n  - 💬 sugestão", "- [x] **C** ✔ sex 16/10"),
    ])
    assert insert_then_move.failures == ()
    assert "- [x] **C** ✔ sex 16/10\n- [ ] **B**\n  - 💬 sugestão\n" in insert_then_move.text
    assert body_text(FMT, first.text).replace("- [ ] **Bruno**: liberar o acesso\n", "") == body_text(FMT, DOC).replace("- [ ] **Bruno**: liberar o acesso\n", "")
    assert first.text.startswith(f"# Atividades\n\n{BOX}") and first.text.endswith(LINKS)


@pytest.mark.parametrize("target,anchor,error", [
    ("- [ ] **B**", "- [ ] **Z**", "anchor not found"),
    ("- [ ] **B**", "[2026-10-16_09-30-11]: ../recordings/2026-10-16_09-30-11/minutes.md", "targets the box or link block"),
    ("- [ ] **B**", "- [ ] **B**", "anchor inside the target"),
    ("- [ ] **B**", "> **Atualizado seg 19/10 10:12** · após Daily", "targets the box or link block"),
    ("- [ ] **Z**", FMT.heading_actions, "not found"),
])
def test_move_errors_change_nothing_and_later_ops_apply(target: str, anchor: str, error: str) -> None:   # UT-114
    out = apply_ops(FMT, DOC, [mv(target, anchor), rep("- [ ] **A** · sex 16/10 · [Daily 16/10][2026-10-16_09-30-11]", "- [ ] **A** x")])
    assert [(f.index, f.error) for f in out.failures] == [(0, error)]
    assert out.text == DOC.replace("- [ ] **A** · sex 16/10 · [Daily 16/10][2026-10-16_09-30-11]\n", "- [ ] **A** x\n")


def test_move_with_an_ambiguous_anchor() -> None:                                         # UT-114
    doc = make(f"{FMT.heading_actions}\n\n- [ ] **B**\n- x\n- x\n")
    out = apply_ops(FMT, doc, [mv("- [ ] **B**", "- x")])
    assert errors(out) == ["anchor found 2 times"] and out.text == doc


def test_a_replace_then_a_move_of_the_same_item() -> None:                                # UT-115
    out = apply_ops(FMT, DOC, [
        rep("- [x] **C** ✔ sex 16/10", "- [x] **C** ✔ sex 16/10 · fim"),
        mv("- [x] **C** ✔ sex 16/10 · fim", "- [ ] **Bruno**: liberar o acesso"),
    ])
    assert out.failures == ()
    assert out.text == DOC.replace("- [x] **C** ✔ sex 16/10\n", "").replace(
        "- [ ] **Bruno**: liberar o acesso\n", "- [ ] **Bruno**: liberar o acesso\n- [x] **C** ✔ sex 16/10 · fim\n")


def test_the_real_document_survives_edits_byte_for_byte() -> None:
    document = FIXTURE.read_text()
    target = "- [ ] Ligar para o suporte da VPN"
    out = apply_ops(FMT, document, [ins(target, "  - citado na [Daily 19/10][2026-10-19_09-30-11]")])
    assert out.failures == ()
    assert out.text == document.replace(target + "\n", target + "\n  - citado na [Daily 19/10][2026-10-19_09-30-11]\n")


def test_line_endings_and_a_last_line_without_newline() -> None:
    crlf = "# T\r\n\r\n" + BOX.replace("\n", "\r\n") + "\r\n## Minhas ações\r\n\r\n- [ ] A\r\n- [ ] B\r\n"
    out = apply_ops(FMT, crlf, [ins("- [ ] A", "  - nota\n  - outra"), rep("- [ ] B", "- [ ] B x")])
    assert out.failures == ()
    assert out.text.endswith("- [ ] A\r\n  - nota\r\n  - outra\r\n- [ ] B x\r\n")
    bare = "## Minhas ações\n\n- [ ] A"
    assert apply_ops(FMT, bare, [ins("- [ ] A", "  - nota")]).text == "## Minhas ações\n\n- [ ] A\n  - nota"
    assert apply_ops(FMT, bare, [rep("- [ ] A", "- [ ] A x")]).text == "## Minhas ações\n\n- [ ] A x"
    assert apply_ops(FMT, "x\n- [ ] A", [mv("- [ ] A", "x")]).text == "x\n- [ ] A"


def test_archive_returns_every_removed_line_with_its_reason() -> None:
    out = apply_ops(FMT, DOC, [arc("- [ ] **A** · sex 16/10 · [Daily 16/10][2026-10-16_09-30-11]\n  - nota de A", "data passou"), arc("- [x] **C** ✔ sex 16/10", "concluído")])
    assert out.archived == ("- [ ] **A** · sex 16/10 · [Daily 16/10][2026-10-16_09-30-11]\n  - nota de A", "- [x] **C** ✔ sex 16/10")
    assert out.reasons == ("data passou", "concluído") and open_count(FMT, out.text) == 2 and ticked_count(FMT, out.text) == 0


def test_a_blank_or_empty_target_matches_nothing() -> None:
    assert errors(apply_ops(FMT, DOC, [rep("", "x"), rep("\n", "x"), ins("   ", "x")])) == ["not found"] * 3

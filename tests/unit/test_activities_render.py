"""The document's box, user lines, link block, diff, calendar and working days (UT-010 to UT-015, UT-018, UT-026, UT-027, UT-116, UT-117)."""
from __future__ import annotations

import ast
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from teams_recorder.application.use_cases.activities import doc_format
from teams_recorder.constants import Activities, Files
from teams_recorder.domain import (
    DocFormat, body_span, body_text, box_stamp, calendar_strip, open_count, render_box, render_links, rescue_box_lines, ticked_count,
    unified_diff, working_days_ago,
)
from teams_recorder.domain.status import MINUTES
from teams_recorder.messages import ActivityDoc

FMT = doc_format()
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "activities" / "atividades.md"
NOW = datetime(2026, 10, 19, 10, 12)
STAMP = "20261019-101200"
SKELETON = f"# Atividades\n\n{FMT.box_start}\n{FMT.box_end_prefix} {FMT.skeleton_stamp}{FMT.box_end_suffix}\n\n{FMT.heading_actions}\n\n{FMT.links_start}\n{FMT.links_end}\n"
FOCUS = ["**Enviar cronograma** à Carla: venceu sex 16/10.", "**Estimar a integração**: vence seg 19/10.", "Cobrar o **Bruno** pelo acesso ao PRD."]
EXPECTED_BOX = (
    f"{FMT.box_start}\n"
    "> **Atualizado seg 19/10 10:12** · após Daily\n"
    ">\n"
    "> **Foco**\n"
    "> 1. **Enviar cronograma** à Carla: venceu sex 16/10.\n"
    "> 2. **Estimar a integração**: vence seg 19/10.\n"
    "> 3. Cobrar o **Bruno** pelo acesso ao PRD.\n"
    f"{FMT.box_end_prefix} {STAMP}{FMT.box_end_suffix}\n"
)


def test_render_box_writes_the_box_of_the_dx_with_the_stamp() -> None:                    # UT-010
    out, typed = render_box(FMT, SKELETON, FOCUS, ["Daily"], NOW, STAMP)
    assert typed == []
    assert out == f"# Atividades\n\n{EXPECTED_BOX}\n{FMT.heading_actions}\n\n{FMT.links_start}\n{FMT.links_end}\n"


def test_render_box_without_meetings_focus_or_stamp() -> None:
    out, _ = render_box(FMT, SKELETON, [], [], NOW, "")
    assert f"{FMT.box_start}\n> **Atualizado seg 19/10 10:12**\n{FMT.box_end_prefix}{FMT.box_end_suffix}\n" in out
    two, _ = render_box(FMT, SKELETON, ["a\nb  c"], ["Daily", "Acme"], NOW, STAMP)
    assert "· após Daily, Acme\n" in two and "> 1. a b c\n" in two


def test_render_box_returns_the_users_lines_and_drops_them_from_the_box() -> None:        # UT-011
    document = SKELETON.replace(f"{FMT.box_end_prefix}", f"- [ ] Ligar X\n  - nota\n> uma citação minha\n{FMT.box_end_prefix}")
    out, typed = render_box(FMT, document, FOCUS, ["Daily"], NOW, STAMP)
    assert typed == ["- [ ] Ligar X", "  - nota", "> uma citação minha"]
    assert "Ligar X" not in out and out.count(FMT.box_start) == 1
    again, typed_again = render_box(FMT, out, FOCUS, ["Daily"], NOW, STAMP)
    assert again == out and typed_again == []


def _with_typed(box: str, *lines: str) -> str:
    return box.replace(f"{FMT.box_end_prefix}", "".join(line + "\n" for line in lines) + FMT.box_end_prefix, 1)


def test_a_numbered_line_the_user_typed_in_the_box_is_returned_not_dropped() -> None:        # UT-011, review 006 issue 003
    first, _ = render_box(FMT, SKELETON, ["**Enviar** cronograma"], ["Daily"], NOW, STAMP)
    typed_by_hand = "> 2. Ligar para o João amanhã"
    document = _with_typed(first, typed_by_hand)                       # the next number of the focus list: the natural way to add an item

    out, typed = render_box(FMT, document, ["**Revisar** PR"], ["Daily"], NOW, STAMP, first)

    assert typed == [typed_by_hand] and "João" not in out
    assert "> 1. **Revisar** PR\n" in out and "Enviar" not in out      # the generated focus line is replaced, not returned


def test_only_the_focus_lines_the_last_pass_wrote_are_generated_and_each_matches_once() -> None:
    first, _ = render_box(FMT, SKELETON, ["a", "b"], ["Daily"], NOW, STAMP)
    document = _with_typed(first, "> 1. a", "> 3. c", "> 3. c")        # a copy of a written line, and a new line twice
    _, typed = render_box(FMT, document, [], [], NOW, STAMP, first)
    assert typed == ["> 1. a", "> 3. c", "> 3. c"]                    # the written "1. a" and "2. b" are matched by the originals
    _, edited = render_box(FMT, first.replace("> 2. b", "> 2. b (meu comentário)"), [], [], NOW, STAMP, first)
    assert edited == ["> 2. b (meu comentário)"]                       # a written line the user changed is theirs now


def test_without_a_base_every_numbered_line_is_generated_as_before() -> None:
    first, _ = render_box(FMT, SKELETON, ["a", "b"], ["Daily"], NOW, STAMP)
    _, typed = render_box(FMT, first, ["c"], ["Daily"], NOW, STAMP)
    assert typed == []
    _, with_base = render_box(FMT, first, ["c"], ["Daily"], NOW, STAMP, first)
    assert with_base == []


def test_render_box_replaces_the_old_generated_box_and_keeps_the_rest_byte_for_byte() -> None:
    document = FIXTURE.read_text()
    out, typed = render_box(FMT, document, FOCUS, ["Daily"], NOW, STAMP)
    assert typed == []
    first, last = body_span(FMT, document)
    assert out.startswith("# Atividades\n\n") and body_text(FMT, out) == document[first:last]
    assert out.endswith(document[last:])


def test_render_box_creates_a_box_when_there_is_none() -> None:
    out, typed = render_box(FMT, "# Atividades\n\n- [ ] A\n", FOCUS, [], NOW, STAMP)
    assert typed == [] and out.startswith(FMT.box_start) and out.endswith("\n- [ ] A\n") and box_stamp(FMT, out) == STAMP


def test_box_stamp_round_trip() -> None:                                                   # UT-117
    out, _ = render_box(FMT, SKELETON, FOCUS, ["Daily"], NOW, STAMP)
    assert box_stamp(FMT, SKELETON) == FMT.skeleton_stamp == Activities.SKELETON_STAMP
    assert box_stamp(FMT, out) == STAMP and box_stamp(FMT, FIXTURE.read_text()) == STAMP
    edited = out.replace(FMT.heading_actions, f"- [ ] nova linha\n{FMT.heading_actions}").replace("> 1.", "> 1. x")
    assert box_stamp(FMT, edited) == STAMP
    unstamped, _ = render_box(FMT, SKELETON, FOCUS, ["Daily"], NOW, "")
    assert box_stamp(FMT, unstamped) is None and body_text(FMT, unstamped) == body_text(FMT, out)
    assert box_stamp(FMT, out.replace(f"{FMT.box_end_prefix} {STAMP}", "<!-- fim")) is None
    assert box_stamp(FMT, "sem caixa\n") is None


def test_body_span_excludes_the_box_and_the_link_block() -> None:
    document = FIXTURE.read_text()
    body = body_text(FMT, document)
    assert body.startswith("\n## Minhas ações") and body.endswith("[Daily 16/10][2026-10-16_09-30-11]\n\n")
    assert FMT.links_start not in body and FMT.box_start not in body and "Atualizado" not in body
    assert body_span(FMT, "sem marcadores\n") == (0, 15)
    half = document.replace(FMT.links_end, "")
    assert body_span(FMT, half)[1] == len(half)
    assert body_span(FMT, document.replace(FMT.box_end_prefix, "<!-- x"))[0] == 0


def test_counts_use_the_formats_patterns() -> None:
    document = FIXTURE.read_text()
    assert (open_count(FMT, document), ticked_count(FMT, document)) == (10, 1)
    assert open_count(replace(FMT, open_re=r"^- \[x\] "), document) == 1
    assert open_count(FMT, "  * [ ] x\n+ [ ] y\n- [ ]\n- [X] z\n") == 2 and ticked_count(FMT, "- [X] z\n- [x] w\n") == 2


def test_render_links_lists_the_labels_in_use_sorted() -> None:                           # UT-012
    document = "x [Daily][2026-10-16_09-30-11] y [Acme][2026-10-15_16-30-02] [Daily 2][2026-10-16_09-30-11]\n"
    out = render_links(FMT, document, lambda _id: True)
    assert out == (document + f"\n{FMT.links_start}\n[2026-10-15_16-30-02]: ../recordings/2026-10-15_16-30-02/minutes.md\n"
                   f"[2026-10-16_09-30-11]: ../recordings/2026-10-16_09-30-11/minutes.md\n{FMT.links_end}\n")
    other = render_links(replace(FMT, link_target="../x/{id}/ata.md"), document, lambda _id: True)
    assert "[2026-10-15_16-30-02]: ../x/2026-10-15_16-30-02/ata.md\n" in other and "recordings" not in other


def test_render_links_is_idempotent_and_drops_unused_definitions() -> None:               # UT-013
    document = FIXTURE.read_text()
    assert render_links(FMT, document, lambda _id: True) == document
    stale = document.replace("[Daily 16/10][2026-10-16_09-30-11]", "[Daily 16/10]").replace("[2026-10-16_09-30-11]", "")
    out = render_links(FMT, stale, lambda _id: True)
    assert "[2026-10-16_09-30-11]: " not in out and "[2026-10-15_14-00-07]: " in out
    assert out.startswith(stale[: stale.index(FMT.links_start)])


def test_render_links_omits_a_meeting_that_no_longer_exists() -> None:                    # UT-014
    document = FIXTURE.read_text()
    out = render_links(FMT, document, lambda meeting_id: meeting_id != "2026-10-16_09-30-11")
    assert "[2026-10-16_09-30-11]: " not in out and "[2026-10-15_14-00-07]: " in out
    assert render_links(FMT, "- [ ] sem links\n", lambda _id: True).endswith(f"\n{FMT.links_start}\n{FMT.links_end}\n")


def test_rescue_box_lines_goes_to_the_top_of_my_actions() -> None:                        # UT-027
    document = FIXTURE.read_text()
    out = rescue_box_lines(FMT, document, ["- [ ] Ligar para o João", "  - nota", "- [ ] Ligar para o suporte da VPN", ""])
    expected = document.replace(f"{FMT.heading_actions}\n\n", f"{FMT.heading_actions}\n\n- [ ] Ligar para o João\n  - nota\n", 1)
    assert out == expected
    assert rescue_box_lines(FMT, document, ["- [ ] Ligar para o suporte da VPN"]) == document
    assert rescue_box_lines(FMT, document, []) == document


def test_rescue_box_lines_creates_the_heading_after_the_box_and_spaces_headings() -> None:
    no_heading = f"# Atividades\n\n{EXPECTED_BOX}\n- [ ] A\n"
    out = rescue_box_lines(FMT, no_heading, ["- [ ] Ligar X"])
    assert out == f"# Atividades\n\n{EXPECTED_BOX}{FMT.heading_actions}\n\n- [ ] Ligar X\n\n- [ ] A\n"
    empty = f"# Atividades\n\n{EXPECTED_BOX}\n{FMT.heading_actions}\n\n{FMT.heading_waiting}\n"
    assert rescue_box_lines(FMT, empty, ["- [ ] Ligar X"]).endswith(f"{FMT.heading_actions}\n\n- [ ] Ligar X\n\n{FMT.heading_waiting}\n")
    assert body_text(FMT, rescue_box_lines(FMT, SKELETON, ["- [ ] Ligar X"])).count("- [ ] Ligar X") == 1


def test_unified_diff() -> None:                                                           # UT-015
    assert unified_diff("a\nb\nc\n", "a\nb\nc\n") == ""
    diff = unified_diff("- [ ] **A** · sex 16/10\n- [ ] B\n", "- [ ] **A** · seg 19/10\n- [ ] B\n")
    assert diff.splitlines()[1:3] == ["-- [ ] **A** · sex 16/10", "+- [ ] **A** · seg 19/10"] and diff.startswith("@@")
    assert unified_diff("a\n", "a\r\n") == "" and unified_diff("a\n", "a\nb\n").splitlines()[-1] == "+b"


def test_calendar_strip() -> None:                                                         # UT-018
    strip = calendar_strip(FMT, date(2026, 10, 19))
    entries = strip.split(", ")
    assert len(entries) == 14 and entries[0] == "seg 19/10 (hoje)" and entries[1] == "ter 20/10"
    assert entries[5:7] == ["[sáb 24/10]", "[dom 25/10]"] and entries[-1] == "dom 01/11".join(["[", "]"])
    assert calendar_strip(FMT, date(2026, 10, 24), days=2) == "[sáb 24/10 (hoje)], [dom 25/10]"


@pytest.mark.parametrize("today,n,expected", [
    (date(2026, 10, 19), 2, date(2026, 10, 15)),
    (date(2026, 10, 21), 2, date(2026, 10, 19)),
    (date(2026, 10, 24), 2, date(2026, 10, 22)),
    (date(2026, 10, 25), 2, date(2026, 10, 22)),
    (date(2026, 10, 24), 0, date(2026, 10, 24)),
    (date(2026, 10, 19), 10, date(2026, 10, 5)),
    (date(2026, 10, 24), 1, date(2026, 10, 23)),
])
def test_working_days_ago(today: date, n: int, expected: date) -> None:                  # UT-026
    assert working_days_ago(today, n) == expected


def test_the_domain_module_imports_neither_messages_nor_constants_nor_the_folder_name() -> None:   # UT-116
    source = (ROOT / "src" / "teams_recorder" / "domain" / "activities.py").read_text()
    tree = ast.parse(source)
    imported = {
        (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in (getattr(node, "names", None) or [None])
    }
    assert not any(name.split(".")[-1] in ("messages", "constants") or "teams_recorder" in name for name in imported), imported
    assert not [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and Files.RECORDINGS_DIR in n.value]


def test_doc_format_is_built_from_the_real_constants_and_round_trips() -> None:           # UT-116
    assert isinstance(FMT, DocFormat)
    assert FMT.link_target == f"../{Files.RECORDINGS_DIR}/{{id}}/{MINUTES}"
    assert (FMT.box_start, FMT.links_start, FMT.heading_actions) == (ActivityDoc.BOX_START, ActivityDoc.LINKS_START, ActivityDoc.HEADING_ACTIONS)
    assert FMT.weekdays == ("seg", "ter", "qua", "qui", "sex", "sáb", "dom") and FMT.today_label == "(hoje)"
    assert FMT.skeleton_stamp == "00000000-000000"
    for stamp in (STAMP, ""):
        out, _ = render_box(FMT, SKELETON, FOCUS, ["Daily"], NOW, stamp)
        assert box_stamp(FMT, out) == (stamp or None) and body_text(FMT, out).startswith(f"\n{FMT.heading_actions}")
    other = replace(FMT, box_end_prefix="<!-- fim", box_end_suffix="-->")
    out, _ = render_box(other, SKELETON.replace(FMT.box_end_prefix, "<!-- fim").replace(FMT.box_end_suffix, "-->"), FOCUS, [], NOW, STAMP)
    assert box_stamp(other, out) == STAMP and "<!-- fim 20261019-101200-->" in out

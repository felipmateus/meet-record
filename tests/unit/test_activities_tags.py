"""Tagged items of the activities document: `tagged_blocks` and `replace_tag` (UT-016, UT-017), table-driven, no fakes."""
from __future__ import annotations

from teams_recorder.application.use_cases.activities import doc_format
from teams_recorder.domain import TaggedBlock, replace_tag, tagged_blocks
from teams_recorder.messages import ActivityDoc

FMT = doc_format()
TAG = ActivityDoc.STORY_TAG
BOX = f"{FMT.box_start}\n> **Atualizado seg 19/10 10:12** · após Daily\n{FMT.box_end_prefix} 20261019-101200{FMT.box_end_suffix}\n"
LINKS = f"{FMT.links_start}\n[2026-10-16_09-30-11]: ../recordings/2026-10-16_09-30-11/minutes.md\n{FMT.links_end}\n"
LINE = "- [ ] **Estimar a integração de estoque** · seg 19/10 · [Daily 16/10][2026-10-16_09-30-11] #história"


def make(body: str, box: str = BOX) -> str:
    return f"# Atividades\n\n{box}\n{body}\n{LINKS}"


def test_a_tagged_line_with_its_deeper_lines_is_one_block() -> None:             # UT-016
    body = (
        f"{FMT.heading_actions}\n\n"
        f"{LINE}\n"
        "  - falta só o módulo de reservas\n"
        "    - 💬 detalhe mais fundo [Daily 19/10][2026-10-19_09-30-11]\n"
        "- [ ] **Outra** sem a marca\n"
    )
    blocks = tagged_blocks(FMT, make(body), TAG)
    assert blocks == [TaggedBlock("b1", (LINE, "  - falta só o módulo de reservas", "    - 💬 detalhe mais fundo [Daily 19/10][2026-10-19_09-30-11]"),
                                  ("2026-10-16_09-30-11", "2026-10-19_09-30-11"))]
    assert len(blocks[0].lines) == 3


def test_blocks_are_numbered_in_order_and_a_blank_line_or_a_sibling_ends_one() -> None:
    body = (
        f"{FMT.heading_actions}\n"
        "- [ ] primeira #história\n"
        "  - nota\n"
        "\n"
        "  - depois da linha em branco\n"
        "- [ ] segunda #história  \n"
        f"{FMT.heading_waiting}\n"
        "- [ ] **Bruno**: algo #história"
    )
    blocks = tagged_blocks(FMT, make(body), TAG)
    assert [(b.ref, b.lines) for b in blocks] == [
        ("b1", ("- [ ] primeira #história", "  - nota")),
        ("b2", ("- [ ] segunda #história",)),          # trailing whitespace dropped
        ("b3", ("- [ ] **Bruno**: algo #história",)),
    ]
    assert all(b.labels == () for b in blocks)


def test_the_tag_is_a_whole_word_and_the_box_and_link_block_are_not_items() -> None:
    box = f"{FMT.box_start}\n> escreveram #história aqui\n{FMT.box_end_prefix} 20261019-101200{FMT.box_end_suffix}\n"
    links = f"{FMT.links_start}\n[x]: ../#história\n{FMT.links_end}\n"
    document = f"# Atividades\n\n{box}\n{FMT.heading_actions}\n- [ ] #históricas não são pedido\n- [ ] ok#história colado\n{links}"
    assert tagged_blocks(FMT, document, TAG) == []
    assert tagged_blocks(FMT, "", TAG) == []


def test_a_tag_inside_an_earlier_block_belongs_to_it_until_that_one_is_gone() -> None:
    body = f"{FMT.heading_actions}\n- [ ] pai #história\n  - filho #história\n"
    first = tagged_blocks(FMT, make(body), TAG)
    assert [b.lines for b in first] == [("- [ ] pai #história", "  - filho #história")]
    again = tagged_blocks(FMT, make(body.replace("pai #história", "pai")), TAG)
    assert [b.lines for b in again] == [("  - filho #história",)]


def test_replace_tag_swaps_the_tag_of_a_line_found_once_and_keeps_every_other_byte() -> None:   # UT-017
    document = make(f"{FMT.heading_actions}\n{LINE}\r\n  - nota\n- [ ] **B**\n")
    out = replace_tag(document, LINE, TAG, "história: [rascunho 19/10](../plans/2026-10-19.stories.md)")
    assert out == document.replace(" #história", " história: [rascunho 19/10](../plans/2026-10-19.stories.md)", 1)
    assert "\r\n" in (out or "")                                    # the line keeps its own ending
    assert replace_tag(document, LINE + "  ", TAG, "x") == out.replace("história: [rascunho 19/10](../plans/2026-10-19.stories.md)", "x")


def test_replace_tag_returns_none_when_the_line_is_not_found_exactly_once() -> None:             # UT-017
    document = make(f"{FMT.heading_actions}\n{LINE}\n")
    assert replace_tag(document, LINE.replace("Estimar", "Estimei"), TAG, "x") is None           # edited meanwhile
    assert replace_tag(make(f"{FMT.heading_actions}\n{LINE}\n{LINE}\n"), LINE, TAG, "x") is None   # ambiguous
    assert replace_tag(document, LINE.replace(" #história", ""), TAG, "x") is None               # no tag on the line
    assert replace_tag(document, LINE, TAG, "") is not None                                      # an empty replacement still counts


def test_trailing_whitespace_does_not_hide_the_line_and_a_second_tag_is_dropped() -> None:
    document = make(f"{FMT.heading_actions}\n- [ ] a #história b #história  \n")
    out = replace_tag(document, "- [ ] a #história b #história", TAG, "L")
    assert out is not None and "- [ ] a L b   \n" in out

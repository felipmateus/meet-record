"""prompts/curate_system.md: the sections the spec asks for, and a worked example that is machine-checked: the input it shows is
exactly what the message builder produces, and the answer it shows is a valid answer that applies to that document."""
from __future__ import annotations

import json
import re

import pytest

from teams_recorder.adapters.outbound.curator_claude import CuratorOut, build_user_message, to_output
from teams_recorder.adapters.outbound.llm_schema import load_prompt
from teams_recorder.application.use_cases.activities import doc_format
from teams_recorder.config import load_settings
from teams_recorder.constants import Files
from teams_recorder.domain import OpKind, apply_ops, open_count, ticked_count
from teams_recorder.messages import Prompt
from tests.fixtures.curator_example import ANSWER, DOCUMENT, example_input


@pytest.fixture(scope="module")
def prompt() -> str:
    return load_prompt(load_settings().prompts_dir / Files.CURATE_PROMPT)


def _fenced(prompt: str, lang: str) -> str:
    found = re.search(rf"```{lang}\n(.*?)\n```", prompt.split("## Worked example")[1], re.S)
    assert found, f"no ```{lang} block in the worked example"
    return found.group(1)


def test_the_prompt_has_the_role_the_edits_the_six_principles_the_example_and_the_checklist(prompt: str):
    headings = re.findall(r"^## (.+)$", re.sub(r"```.*?```", "", prompt, flags=re.S), re.M)
    assert [h for h in headings if h.startswith("Principle")] == [
        "Principle 1: the document is the truth, and the user's hand wins",
        "Principle 2: completion is the user's",
        "Principle 3: the same work in other words is one item",
        "Principle 4: never delete, and keep it short",
        "Principle 5: put each thing where the user looks",
        "Principle 6: the focus says what to do next",
    ]
    assert [h for h in headings if not h.startswith("Principle")] == ["What you receive", "Edits", "Line formats", "Worked example", "Checklist"]
    assert prompt.startswith("You keep one Markdown document for one user")
    assert 'Address the user as "você"' in prompt and 'Never write "usuário"' in prompt


def test_the_prompt_asks_for_brazilian_portuguese_and_is_written_in_english(prompt: str):
    assert "Brazilian Portuguese" in prompt
    assert "all content in Brazilian Portuguese" in prompt.split("## Checklist")[1]
    prose = prompt.split("## Worked example")[0]
    assert not re.search(r"\b(você deve|não escreva|sempre que|nunca)\b", prose)     # the instructions are English; Portuguese is only data and examples


def test_it_describes_the_message_parts_in_their_order_and_every_ref_letter(prompt: str):
    received = prompt.split("## What you receive")[1].split("## Edits")[0]
    tags = ["`<document>`", "`<meeting n id title when health>`", "`<excerpts>`", "`<calendar>`", "`<user_edits>`", "`<box_lines>`",
            "`<last_pass>`", "`<recent_archive>`", "`<task>`"]
    positions = [received.index(tag) for tag in tags]
    assert positions == sorted(positions)
    for ref in ("`n.a1`", "`n.o1`", "`n.u1`", "`n.p1`", "`n.n1`", "`n.d1`", "`n.q1`", "`n.r1`"):
        assert ref in received
    assert "⚠️ unconfirmed: <reason>" in received and "wrong_sample_rate" in received


def test_the_edits_section_covers_the_four_ops_the_rule_and_the_corrected_anchor_rule(prompt: str):
    edits = prompt.split("## Edits")[1].split("## Line formats")[0]
    for op in ("`replace`", "`insert_after`", "`move`", "`archive`"):
        assert op in edits
    assert "`anchor` is one whole line" in edits and "right after the anchor, byte for byte" in edits
    # the anchor rule after the review rounds: heading, one of yours with a meeting id, or the user's line for a sub-line; never a 💬 line
    assert "Anchor an `insert_after` on a section heading, or on a main line: one of yours that carries a meeting id, or the user's own line when you add a sub-line to it" in edits
    assert "Never anchor an `insert_after` on a 💬 line" in edits
    assert "A `move` anchors on a section heading (the item becomes the first of its section) or on the last line of the destination section" in edits
    assert "never a `replace` that re-emits lines it does not change" in edits
    assert "list a `move` after any edit of the same item" in edits
    assert "only `archive` removes a checkbox line, and no edit changes a box" in edits
    assert "an `insert_after` text has no `- [x]` line" in edits and "a `move` cannot break anything" in edits
    assert "Merge duplicates with `archive`, never with `replace`" in edits
    assert "one chance to fix the failed edits" in edits


def test_the_principles_carry_the_rules_the_code_cannot_check(prompt: str):
    p1, p2, p3, p4, p5, p6 = (prompt.split(f"## Principle {n}")[1].split("\n## ")[0] for n in range(1, 7))
    assert "Read `<user_edits>` first" in p1 and "Never rewrite the main text of any existing line" in p1
    assert "`user_removed`" in p1 and "voltou: parece que o editor sobrescreveu; apague de novo se não vale" in p1 and "`<box_lines>`" in p1
    assert "✔ <ddd dd/mm>" in p1 and "bottom of its section" in p1
    assert "Never tick, untick or archive an open item" in p2 and "Marque [x] se concluiu" in prompt and "`indefinido`" in p2
    assert "An intention" in p2 and "`in_progress` adds a sub-line only when it carries a concrete remainder" in p2
    assert "`<recent_archive>`" in p3 and "voltou: arquivado em dd/mm" in p3 and "this is a rerun" in p3 and "the user's line stays" in p3
    assert '"target": "- [ ] Ligar para o suporte da VPN"' in p3 and "citado na" in p3
    assert "Never archive an open item because of its age" in p4 and "💤 sem menção desde" in p4 and "never 💤, never sunk" in p4
    assert "about ten lines" in p4 and "`move` to the last line of its section" in p4
    for heading in ("Minhas ações", "Aguardando outros", "Agenda e prazos", "Contexto recente"):
        assert heading in p5
    assert "`ignored`" in p5 and "Every ref appears in the `refs` of some op or in `ignored`" in p5 and "`health`" in p5
    assert "3 to 5 lines" in p6 and "only next to an absolute date" in p6 and "only when it is overdue" in p6 and "`notify`" in p6


def test_the_checklist_repeats_the_seven_points_of_the_task_block(prompt: str):
    checklist = prompt.split("## Checklist")[1]
    for n in range(1, 8):
        assert f"({n})" in checklist
    for phrase in ("apply the user's edits and the box lines", "every ref is in `refs` or in `ignored`", "targets copied exactly, from the body only",
                   "(reorders are `move` ops)", "all content in Brazilian Portuguese"):
        assert phrase in checklist


def test_the_worked_example_input_is_what_the_message_builder_produces(prompt: str):
    shown = _fenced(prompt, "text")
    built = build_user_message(example_input())
    assert shown.split("\n<task>")[0] == built.split("<task>")[0].rstrip("\n")
    assert shown.endswith("<task>\n…\n</task>")
    assert "<document>" in shown and "<meeting n=\"1\"" in shown and "⚠️ unconfirmed" in shown


def test_the_worked_example_answer_is_the_tested_answer_and_applies_cleanly(prompt: str):
    shown = json.loads(_fenced(prompt, "json"))
    assert shown == ANSWER
    out = to_output(CuratorOut.model_validate(shown))
    fmt = doc_format()

    applied = apply_ops(fmt, DOCUMENT, out.ops)

    assert applied.failures == ()
    assert {op.kind for op in out.ops} == {OpKind.REPLACE, OpKind.INSERT_AFTER, OpKind.MOVE, OpKind.ARCHIVE}
    assert applied.archived == ("- [x] **Rever o contrato da Acme** ✔ qui 15/10 · [Cliente Acme 15/10][2026-10-15_16-30-02]",)
    assert open_count(fmt, applied.text) == open_count(fmt, DOCUMENT) + 2          # two new checkbox items, none removed
    assert ticked_count(fmt, applied.text) == ticked_count(fmt, DOCUMENT) - 1      # only the archived one left
    ata = "- [x] **Enviar a ata da reunião com a Acme** ✔ seg 19/10 · [Cliente Acme 15/10][2026-10-15_16-30-02]"
    section = applied.text.split("## Minhas ações")[1].split("## Aguardando outros")[0].rstrip().splitlines()
    assert section[-1] == ata and "- [ ] Ligar para o suporte da VPN" in section   # the ticked item moved to the bottom of its section


def test_the_worked_example_answer_accounts_for_every_ref_and_never_says_usuario(prompt: str):
    out = to_output(CuratorOut.model_validate(json.loads(_fenced(prompt, "json"))))
    refs = {line.split(" ")[0] for line in build_user_message(example_input()).split("<meeting")[1].split("</meeting>")[0].splitlines()[1:] if line}
    accounted = {ref for op in out.ops for ref in op.refs} | {i.ref for i in out.ignored}
    assert refs == accounted == {"1.a1", "1.o1", "1.o2", "1.u1", "1.u2", "1.d1"}
    assert 3 <= len(out.focus) <= 5 and out.summary and "\n" not in out.summary
    assert "usuário" not in json.dumps(ANSWER, ensure_ascii=False)
    insert_heads = [op.target for op in out.ops if op.kind is OpKind.INSERT_AFTER and op.target.startswith("## ")]
    assert insert_heads == ["## Minhas ações", "## Aguardando outros", "## Contexto recente"]


def test_the_prompt_and_the_task_let_a_quote_keep_the_language_it_was_said_in(prompt: str):
    """Language detection UT-053 (curator half): the curator gets no header line, so the exception is unconditional."""
    exception = "in the language they were said in"
    assert "except quotes" in Prompt.CURATE_TASK and exception in Prompt.CURATE_TASK
    assert Prompt.CURATE_TASK.splitlines()[-1].startswith("7. Write all content in Brazilian Portuguese, except quotes")
    lines = prompt.splitlines()
    assert "usually held in Brazilian Portuguese" in lines[0] and "held in Brazilian Portuguese. You" not in lines[0]
    sentences = [line for line in lines if re.search(r"(Everything in the document is|all content) in Brazilian Portuguese", line)]
    assert len(sentences) == 2   # the document rule (line 34) and the checklist (line 281)
    assert all("except quotes" in line and "language" in line for line in sentences)
    (format_line,) = [line for line in lines if line.startswith("- A 💬 sub-line")]   # line 43: the 💬 format
    assert "keeps the language it was said in" in format_line and "<citação literal>" in format_line

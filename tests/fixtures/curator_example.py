"""The worked example of prompts/curate_system.md as data: the document before the pass, the user's tick since the last
pass, one meeting, and the answer the prompt shows. `tests/unit/test_curator_prompt.py` checks that the prompt shows exactly
what the message builder produces for `example_input()`, and that `ANSWER` applies to `DOCUMENT` with no failure."""
from __future__ import annotations

from datetime import date, datetime
from teams_recorder.application.use_cases.activities import doc_format
from teams_recorder.domain import (
    Action, Analysis, CuratorInput, Decision, MeetingContext, StatusChange, StatusUpdate, Verification, VerificationStatus,
    body_text, calendar_strip, unified_diff,
)

DOCUMENT = """# Atividades

<!-- curador:início (reescrito a cada passada; escreva fora desta caixa) -->
> **Atualizado sex 16/10 17:40** · após Alinhamento Acme
>
> **Foco**
> 1. **Enviar cronograma revisado do go-live** à Carla: vence ter 20/10 e ela precisa dele para o aceite.
> 2. **Estimar a integração de estoque**: vence seg 19/10.
<!-- curador:fim 20261016-174000 -->

## Minhas ações

- [ ] **Enviar cronograma revisado do go-live** — p/ Carla · ter 20/10 · alta · [Revisão SAP 14/10][2026-10-14_10-00-03]
- [x] **Enviar a ata da reunião com a Acme** · [Cliente Acme 15/10][2026-10-15_16-30-02]
- [ ] **Estimar a integração de estoque** — p/ Rafael · seg 19/10 · [Planejamento 15/10][2026-10-15_14-00-07]
- [ ] **Subir o timesheet de outubro** · [1:1 Marina 13/10][2026-10-13_16-00-04]
- [ ] Ligar para o suporte da VPN
- [x] **Rever o contrato da Acme** ✔ qui 15/10 · [Cliente Acme 15/10][2026-10-15_16-30-02]

## Aguardando outros

- [ ] **Diego**: corrigir a conversão de unidade no relatório de estoque · [Daily 16/10][2026-10-16_09-30-11]

## Agenda e prazos

- seg 19/10 15:00 — Revisão de sprint · [Daily 16/10][2026-10-16_09-30-11]

## Contexto recente

- Pergunta: quem assina o aceite do piloto do lado da Acme? · [Cliente Acme 15/10][2026-10-15_16-30-02]

<!-- links:início (gerado automaticamente) -->
[2026-10-13_16-00-04]: ../recordings/2026-10-13_16-00-04/minutes.md
[2026-10-14_10-00-03]: ../recordings/2026-10-14_10-00-03/minutes.md
[2026-10-15_14-00-07]: ../recordings/2026-10-15_14-00-07/minutes.md
[2026-10-15_16-30-02]: ../recordings/2026-10-15_16-30-02/minutes.md
[2026-10-16_09-30-11]: ../recordings/2026-10-16_09-30-11/minutes.md
<!-- links:fim -->
"""

BASE = DOCUMENT.replace("- [x] **Enviar a ata", "- [ ] **Enviar a ata")   # the user ticked it after the last pass
MEETING_ID = "2026-10-19_09-30-11"
LINK = f"[Daily 19/10][{MEETING_ID}]"
EXCERPTS = (
    "[00:02:50] Marina: E o timesheet, Felipe?\n[00:02:55] Felipe: O timesheet eu já subi.\n[...]\n"
    "[00:05:00] Carla: Felipe, e o cronograma?\n[00:05:02] Felipe: O cronograma eu fecho hoje à tarde."
)
ARCHIVE_ENTRY = "### 16/10/2026 — data passou (qui 15/10)\n- qui 15/10 16:30 — Reunião com a Acme · [Revisão SAP 14/10][2026-10-14_10-00-03]"


def analysis() -> Analysis:
    return Analysis(
        meeting_id=MEETING_ID, summary="Daily.", title="Daily",
        my_actions=[Action("Validar a carga de materiais no QAS", "usuário", MEETING_ID, due=date(2026, 10, 20), at="00:07:30", for_whom="time de dados")],
        others_actions=[
            Action("Liberar o acesso do Felipe ao SAP PRD", "Bruno", MEETING_ID, due=date(2026, 10, 21), at="00:09:10",
                   verification=Verification(VerificationStatus.UNCONFIRMED, "não ficou claro que o Bruno assumiu o pedido")),
            Action("Atualizar o wiki de onboarding", "Rafael", MEETING_ID, at="00:11:25"),
        ],
        status_updates=[
            StatusUpdate("o cronograma do go-live", StatusChange.DUE_CHANGED, "usuário", "o cronograma eu fecho hoje à tarde", at="00:05:02", new_due=date(2026, 10, 19)),
            StatusUpdate("o timesheet de outubro", StatusChange.DONE, "usuário", "o timesheet eu já subi", at="00:02:55"),
        ],
        decisions=[Decision("A carga inicial usa a planilha de sexta, não o extrato do SAP.", "00:10:40")],
    )


def example_input() -> CuratorInput:
    fmt = doc_format()
    return CuratorInput(
        document=DOCUMENT,
        meetings=[MeetingContext(MEETING_ID, "Daily", analysis(), None, EXCERPTS)],
        calendar=calendar_strip(fmt, date(2026, 10, 19)),
        user_edits=unified_diff(body_text(fmt, BASE), body_text(fmt, DOCUMENT)),
        box_lines=[],
        recent_archive=[ARCHIVE_ENTRY],
        last_summary="2 ações novas, 1 aguardando",
        today=datetime(2026, 10, 19, 10, 12),
        user_name="Felipe",
    )


_CRONOGRAMA = "- [ ] **Enviar cronograma revisado do go-live** — p/ Carla · {due} · alta · [Revisão SAP 14/10][2026-10-14_10-00-03]"
_ATA = "- [x] **Enviar a ata da reunião com a Acme** {tick}· [Cliente Acme 15/10][2026-10-15_16-30-02]"
_ATA_TICKED = _ATA.format(tick="✔ seg 19/10 ")


def _op(op: str, target: str, text: str | None = None, reason: str | None = None, anchor: str | None = None, refs: list[str] | None = None) -> dict:
    return {"op": op, "target": target, "text": text, "reason": reason, "anchor": anchor, "refs": refs or []}


ANSWER = {
    "ops": [
        _op("replace", _CRONOGRAMA.format(due="ter 20/10"),
            _CRONOGRAMA.format(due="seg 19/10") + " " + LINK + "\n  - prazo mudou de ter 20/10 para seg 19/10 (Daily 19/10, 00:05:02)", refs=["1.u1"]),
        _op("insert_after", "- [ ] **Subir o timesheet de outubro** · [1:1 Marina 13/10][2026-10-13_16-00-04]",
            '  - 💬 Na Daily 19/10 (00:02:55) você disse: "o timesheet eu já subi". Marque [x] se concluiu.', refs=["1.u2"]),
        _op("archive", "- [x] **Rever o contrato da Acme** ✔ qui 15/10 · [Cliente Acme 15/10][2026-10-15_16-30-02]", reason="concluído"),
        _op("replace", _ATA.format(tick=""), _ATA_TICKED),
        _op("move", _ATA_TICKED, anchor="- [ ] Ligar para o suporte da VPN"),
        _op("insert_after", "## Minhas ações", "- [ ] **Validar a carga de materiais no QAS** — p/ time de dados · ter 20/10 · " + LINK, refs=["1.a1"]),
        _op("insert_after", "## Aguardando outros",
            "- [ ] **Bruno**: liberar o seu acesso ao SAP PRD · ter 21/10 · ⚠️ a confirmar: não ficou claro que o Bruno assumiu o pedido · " + LINK, refs=["1.o1"]),
        _op("insert_after", "## Contexto recente", "- Decisão: a carga inicial usa a planilha de sexta, não o extrato do SAP · " + LINK, refs=["1.d1"]),
    ],
    "user_removed": [],
    "focus": [
        "**Enviar cronograma revisado do go-live** à Carla: você disse que fecha hoje à tarde (seg 19/10) e ela precisa dele para o aceite.",
        "**Estimar a integração de estoque**: vence hoje, seg 19/10, e a Revisão de sprint é às 15:00.",
        "**Validar a carga de materiais no QAS**: vence amanhã, ter 20/10, e o time de dados espera o resultado.",
    ],
    "summary": "1 ação nova, 1 aguardando, 1 possível conclusão, prazo do cronograma mudou para seg 19/10",
    "notify": True,
    "ignored": [{"ref": "1.o2", "why": "o Rafael atualizar o wiki de onboarding não afeta o seu trabalho"}],
}

"""`ActivitiesSummary` (UT-110), the two document readers it stands on (`box_focus`, `section_counts`) and the pass planning of
`trec activities curate` (`passes_by_day`)."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from teams_recorder.application.use_cases.activities import ActivitiesSummary, passes_by_day
from teams_recorder.domain import PassKind, box_focus, section_counts
from teams_recorder.messages import ActivityDoc
from tests.fakes import FakeActivityCurator, InMemoryActivityStore, InMemoryMeetingRepository
from tests.fixtures.curation import FMT, answer, build, rec, seed

DOCUMENT = f"""# Atividades

{ActivityDoc.BOX_START}
> **Atualizado seg 19/10 10:12** · após Daily
>
> **Foco**
> 1. **Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10.
> 2. **Estimar a integração de estoque**: vence seg 19/10.
> uma linha digitada pelo usuário
- [ ] linha digitada fora do formato
{ActivityDoc.BOX_END_PREFIX} 20261019-101200{ActivityDoc.BOX_END_SUFFIX}

{ActivityDoc.HEADING_ACTIONS}

- [ ] **Enviar cronograma revisado do go-live** — p/ Carla
  - prazo mudou
- [ ] **Estimar a integração de estoque**
  - [ ] sub-item aberto
- [x] **Enviar a ata** ✔ sex 16/10
- [ ] Ligar para o suporte da VPN

{ActivityDoc.HEADING_WAITING}

- [ ] **Bruno**: liberar o acesso
- [x] **Carla**: aprovar o escopo

## Notas do usuário

- [ ] isto não conta

{ActivityDoc.HEADING_AGENDA}

- seg 19/10 15:00 — Revisão de sprint
  - sub-linha
- sex 30/10 — Go-live

{ActivityDoc.HEADING_CONTEXT}

- Decisão: a carga inicial usa a planilha
- Pergunta: quem assina o aceite?
- Risco: sem acesso ao PRD

{ActivityDoc.LINKS_START}
[2026-10-19_09-30-11]: ../recordings/2026-10-19_09-30-11/minutes.md
{ActivityDoc.LINKS_END}
"""


def test_the_focus_is_the_numbered_lines_of_the_box_as_stored() -> None:
    assert box_focus(FMT, DOCUMENT) == [
        "1. **Enviar cronograma revisado do go-live** à Carla: venceu sex 16/10.",
        "2. **Estimar a integração de estoque**: vence seg 19/10.",
    ]
    assert box_focus(FMT, "# Atividades\n\n## Minhas ações\n") == []          # no box


def test_the_counts_are_open_checkboxes_for_the_checkbox_sections_and_lines_for_the_other_two() -> None:
    assert section_counts(FMT, DOCUMENT) == {
        ActivityDoc.HEADING_ACTIONS: 4,      # the sub-item's own open box counts; the ticked one and the sub-line do not
        ActivityDoc.HEADING_WAITING: 1,
        ActivityDoc.HEADING_AGENDA: 2,       # the indented sub-line does not
        ActivityDoc.HEADING_CONTEXT: 3,
    }


def test_a_renamed_or_removed_heading_is_left_out_and_a_user_section_is_never_counted() -> None:
    renamed = DOCUMENT.replace(ActivityDoc.HEADING_WAITING, "## Esperando os outros").replace(ActivityDoc.HEADING_CONTEXT + "\n", "")
    counts = section_counts(FMT, renamed)
    assert ActivityDoc.HEADING_WAITING not in counts and ActivityDoc.HEADING_CONTEXT not in counts
    assert counts[ActivityDoc.HEADING_ACTIONS] == 4 and counts[ActivityDoc.HEADING_AGENDA] == 2 + 3   # the lines of the removed heading now sit under the one above
    assert section_counts(FMT, "") == {}


def test_the_box_and_the_link_block_are_never_counted() -> None:
    counts = section_counts(FMT, DOCUMENT)
    assert sum(counts.values()) == 4 + 1 + 2 + 3                                # the box's `- [ ]` line and the links are outside the body


# --- ActivitiesSummary (UT-110) -----------------------------------------------------------------------------------------

def _summary(document: str | None):
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore(document=document)
    use, _, _ = build(repo, store, FakeActivityCurator([answer()]), now=datetime(2026, 10, 19, 15, 0))
    return repo, store, ActivitiesSummary(repo, store, use)


def test_the_summary_reads_the_focus_the_counts_and_the_last_pass_record() -> None:       # UT-110
    repo, store, summary = _summary(DOCUMENT)
    first = seed(repo, datetime(2026, 10, 19, 9, 30), "Daily")
    second = seed(repo, datetime(2026, 10, 19, 14, 0), "Revisão de sprint")
    store.records += [
        rec(PassKind.MEETING, first, version="v1", summary="antiga", ts=datetime(2026, 10, 19, 9, 40)),
        rec(PassKind.MEETING, first, second, version="v2", summary="1 ação nova", ts=datetime(2026, 10, 19, 10, 12)),
        rec(PassKind.FAILED, second, version="v3", ts=datetime(2026, 10, 19, 11, 0)),
        rec(PassKind.SKIPPED_EMPTY, second, version="v4", ts=datetime(2026, 10, 19, 11, 5)),
    ]

    status = summary.execute()

    assert status.exists and status.path == store.path()
    assert status.updated == datetime(2026, 10, 19, 10, 12)                                  # failed and skipped passes are not updates
    assert status.titles == ("Daily", "Revisão de sprint")
    assert status.last_pass is not None and status.last_pass.summary == "1 ação nova"
    assert status.focus == tuple(box_focus(FMT, DOCUMENT)) and status.counts == section_counts(FMT, DOCUMENT)


def test_an_undo_pass_is_the_last_update_too() -> None:
    repo, store, summary = _summary(DOCUMENT)
    mid = seed(repo, datetime(2026, 10, 19, 9, 30), "Daily")
    store.records += [rec(PassKind.MEETING, mid, version="v1"), rec(PassKind.UNDO, mid, version="v2", ts=datetime(2026, 10, 19, 12, 0))]
    status = summary.execute()
    assert status.last_pass is not None and status.last_pass.kind is PassKind.UNDO and status.updated == datetime(2026, 10, 19, 12, 0)


def test_the_summary_lists_the_meetings_not_curated_and_a_removed_meeting_shows_its_id() -> None:
    repo, store, summary = _summary(DOCUMENT)
    missing = "2026-10-19_09-00-00"
    store.records.append(rec(PassKind.MEETING, missing, version="v1"))
    failed = seed(repo, datetime(2026, 10, 19, 14, 0), "Revisão de sprint")
    repo.curation_errors[failed] = "Activity curation failed: Claude Code timed out after 900 s"
    never = seed(repo, datetime(2026, 10, 16, 17, 30), "Alinhamento Acme")

    status = summary.execute()

    assert status.titles == (missing,)
    assert [(n.meeting_id, n.title, n.reason) for n in status.not_curated] == [
        (never, "Alinhamento Acme", None),
        (failed, "Revisão de sprint", "Activity curation failed: Claude Code timed out after 900 s"),
    ]


def test_without_a_document_the_summary_says_so_and_still_lists_what_is_not_curated() -> None:
    repo, _, summary = _summary(None)
    seed(repo, datetime(2026, 10, 19, 9, 30), "Daily")
    status = summary.execute()
    assert not status.exists and status.updated is None and status.focus == () and status.counts == {} and status.last_pass is None
    assert len(status.not_curated) == 1


def test_the_summary_never_takes_the_lock() -> None:
    _, store, summary = _summary(DOCUMENT)
    summary.execute()
    assert store.locks == []


# --- the passes of an explicit request ----------------------------------------------------------------------------------

@pytest.mark.parametrize(("days", "expected"), [
    ({}, []),
    ({"b": date(2026, 10, 6), "a": date(2026, 10, 5), "c": date(2026, 10, 5)}, [["a", "c"], ["b"]]),
    ({f"m{i}": date(2026, 10, 5) for i in range(5)}, [["m0", "m1", "m2", "m3"], ["m4"]]),
    ({"x": date(2026, 10, 7), "y": date(2026, 10, 5)}, [["y"], ["x"]]),
])
def test_a_pass_never_mixes_two_days_and_holds_at_most_four_meetings(days, expected) -> None:
    assert passes_by_day(days) == expected

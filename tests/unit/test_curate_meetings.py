"""`CurateMeetings` on fakes: the input the curator gets, how its edits are applied and repaired, what is committed, the failure
path, batching, recovery and the notification rules (UT-030 to UT-049, UT-100 to UT-102, UT-104 to UT-106, UT-123)."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from teams_recorder.application.ports import VersionFiles
from teams_recorder.application.use_cases.activities import (
    CurateMeetings, NotCurated, batches, free_version, has_content, next_batch, refs_of, skeleton,
)
from teams_recorder.domain import (
    AnalysisError, CommitIncomplete, CuratorBusy, IgnoredRef, Meeting, MeetingStatus, Op, OpError, PassKind, RemovedItem, TranscriptHealth, apply_ops, body_text,
    box_stamp, calendar_strip, derive_status, excerpt_window, render_box, render_links, unified_diff,
)
from teams_recorder.domain.status import CURATION_ERROR, ERROR, TRANSCRIPT_JSON
from teams_recorder.messages import ActivityDoc, Err, Notify, Prompt
from tests.fakes import FakeActivityCurator, InMemoryActivityStore, InMemoryMeetingRepository
from tests.fixtures.curation import (
    ACTIONS, FMT, NOW, SKELETON, WAITING, analysis, answer, archive, build, empty_analysis, insert, meeting_id, rec, replace, seed,
    with_updates,
)

DAILY = datetime(2026, 10, 19, 9, 30)
ITEM = "- [ ] **Enviar o cronograma** · [Daily 16/10][2026-10-16_09-30-11]"
OTHER = "- [ ] Ligar para o suporte da VPN"


def doc_with(*items: str) -> str:
    """The document of an earlier pass: the skeleton with `items` right under `## Minhas ações`, a stamped box."""
    text = SKELETON.replace(ACTIONS + "\n\n", ACTIONS + "\n" + "".join(item + "\n" for item in items) + "\n", 1)
    return render_box(FMT, text, ["foco"], ["Daily"], datetime(2026, 10, 16, 17, 40), "20261016-174000")[0]


def in_box(document: str, line: str) -> str:
    return document.replace(FMT.box_end_prefix, line + "\n" + FMT.box_end_prefix, 1)


def setup(document: str | None = None, base: str | None = None, outputs=None, **curator_options):
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore(document=document, base=base)
    curator = FakeActivityCurator(outputs if outputs is not None else [answer()], **curator_options)
    use, notifier, clock = build(repo, store, curator)
    return repo, store, curator, use, notifier


# --- the pass and its input -------------------------------------------------------------------------------------------

def test_a_pass_commits_the_edited_document_with_the_base_built_from_the_written_text() -> None:  # UT-030
    repo, store, curator, use, _ = setup(outputs=[answer([], summary="x")])
    mid = seed(repo, DAILY)
    ops = [insert(f"- [ ] **Enviar o cronograma** · [Daily 19/10][{mid}]"), insert(f"- [ ] **Estimar** · [Daily 19/10][{mid}]", refs=("1.a2",))]
    curator.outputs = [answer(ops, summary="2 ações novas", focus=["**Enviar o cronograma** hoje"])]
    result = use.execute([mid])
    assert result.curated == (mid,) and result.failed == () and result.edits == 2 and result.summary == "2 ações novas"
    assert len(store.commits) == 1
    before, after, archived, base, record = store.commits[0]
    written = apply_ops(FMT, SKELETON, ops).text
    version = "20261019-101200"
    expected = render_links(FMT, render_box(FMT, written, ["**Enviar o cronograma** hoje"], ["Daily"], NOW, version)[0], repo.exists)
    assert (before, base, after, archived) == (SKELETON, expected, expected, [])
    assert box_stamp(FMT, after) == version
    assert f"[{mid}]: ../recordings/{mid}/minutes.md" in after and "Atualizado seg 19/10 10:12" in after
    assert (record.kind, record.meetings, record.ops_applied, record.retried, record.version) == (PassKind.MEETING, (mid,), 2, False, version)
    assert record.summary == "2 ações novas" and record.error is None and record.doc_chars == len(after)
    assert record.unaccounted_refs == () and record.during_edits == "" and record.carried_edits == ""
    assert store.document == after and store.base == base


def test_the_first_pass_starts_from_the_skeleton() -> None:  # UT-031
    repo, store, curator, use, _ = setup()
    mid = seed(repo, DAILY)
    use.execute([mid])
    assert curator.inputs[0].document == SKELETON == skeleton(FMT)
    assert box_stamp(FMT, SKELETON) == FMT.skeleton_stamp
    assert all(part in SKELETON for part in (ActivityDoc.TITLE, ACTIONS, WAITING, FMT.heading_agenda, FMT.heading_context, FMT.links_start))
    assert store.commits[0][0] == SKELETON and curator.inputs[0].user_edits == ""


def test_an_empty_analysis_costs_no_call_and_leaves_the_document() -> None:  # UT-032
    document = doc_with(ITEM)
    repo, store, curator, use, notifier = setup(document, document)
    mid = seed(repo, DAILY, content=empty_analysis)
    assert not has_content(repo.load_analysis(mid))
    result = use.execute([mid])
    assert curator.inputs == [] and store.commits == [] and store.document == document and notifier.messages == []
    assert result.curated == (mid,) and result.failed == ()
    assert [(r.kind, r.meetings, r.error) for r in store.logged] == [(PassKind.SKIPPED_EMPTY, (mid,), None)]


def test_a_meeting_counts_as_empty_only_when_nothing_at_all_was_extracted() -> None:
    mid = "2026-10-19_09-30-11"
    assert not has_content(empty_analysis(mid))
    for field in ("decisions", "open_questions", "risks", "next_meetings"):
        assert has_content(analysis(mid, my_actions=[], **{field: ["x"] if field != "decisions" else [object()]}))
    assert has_content(with_updates(mid, "00:01:00"))


def test_a_batch_skips_the_empty_meeting_but_covers_it() -> None:
    repo, store, curator, use, _ = setup()
    empty = seed(repo, datetime(2026, 10, 19, 8, 0), content=empty_analysis)
    real = seed(repo, DAILY)
    result = use.execute([real, empty])
    assert [m.meeting_id for m in curator.inputs[0].meetings] == [real]
    assert result.curated == (empty, real)
    assert store.records[-1].meetings == (empty, real) and store.records[-1].kind == PassKind.MEETING


def test_the_box_lines_the_user_typed_reach_the_curator() -> None:  # UT-033
    typed = "- [ ] Ligar para o João"
    document = in_box(doc_with(ITEM), typed)
    repo, _, curator, use, _ = setup(document, doc_with(ITEM))
    use.execute([seed(repo, DAILY)])
    assert curator.inputs[0].box_lines == [typed]
    assert typed not in curator.inputs[0].user_edits     # a box line reaches the model once, as a box line


def test_a_numbered_line_typed_in_the_box_reaches_the_curator_and_is_rescued_not_deleted() -> None:  # UT-033, review 006 issue 003
    typed = "> 2. Ligar para o João amanhã"                      # the next number of the focus list, as the user would add an item
    base = doc_with(ITEM)
    repo, store, curator, use, _ = setup(in_box(base, typed), base)
    use.execute([seed(repo, DAILY)])
    _, after, _, written_base, record = store.commits[0]
    assert curator.inputs[0].box_lines == [typed] and record.box_rescued == 1
    assert typed in after and typed not in written_base                  # in the document (top of the actions), never in the base
    assert after.count(typed) == 1                                        # once: the new box does not carry it


def test_the_user_edits_are_the_last_during_edits_then_the_diff_of_the_bodies() -> None:  # UT-035
    base = doc_with(ITEM)
    document = base.replace(ITEM, ITEM + "\n- [ ] Escrita pelo usuário")
    repo, store, curator, use, _ = setup(document, base)
    store.records += [rec(PassKind.MEETING, "x", version="v0", during_edits="@@ before @@\n+do meio da chamada", summary="a passada anterior"),
                      rec(PassKind.FAILED, "y", version="v1", during_edits="not a pass that counts")]
    use.execute([seed(repo, DAILY)])
    data = curator.inputs[0]
    diff = unified_diff(body_text(FMT, base), body_text(FMT, document))
    assert "+- [ ] Escrita pelo usuário" in diff
    assert data.user_edits == "@@ before @@\n+do meio da chamada\n" + diff
    assert data.last_summary == "a passada anterior"
    assert store.commits[0][4].carried_edits == "@@ before @@\n+do meio da chamada"


def test_the_first_pass_has_no_user_edits_even_when_a_document_exists() -> None:  # UT-035
    repo, _, curator, use, _ = setup(doc_with(ITEM), None)
    use.execute([seed(repo, DAILY)])
    assert curator.inputs[0].user_edits == "" and curator.inputs[0].last_summary is None


def test_a_missing_document_starts_over_even_when_a_base_is_left() -> None:
    repo, _, curator, use, _ = setup(None, doc_with(ITEM))
    use.execute([seed(repo, DAILY)])
    assert curator.inputs[0].user_edits == ""


def test_the_curator_is_given_the_calendar_the_archive_the_name_and_the_time() -> None:
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore(doc_with(ITEM), doc_with(ITEM))
    store.archive = "### 16/10/2026 — concluído\n- [x] velho\n"
    curator = FakeActivityCurator([answer()])
    use, _, _ = build(repo, store, curator, user_name="Felipe")
    use.execute([seed(repo, DAILY)])
    data = curator.inputs[0]
    assert data.calendar == calendar_strip(FMT, date(2026, 10, 19)) and data.today == NOW and data.user_name == "Felipe"
    assert data.recent_archive == ["### 16/10/2026 — concluído\n- [x] velho"]


def test_the_excerpts_are_the_transcript_around_each_status_update() -> None:  # UT-053 (the CurateMeetings clause)
    health = TranscriptHealth(loop_share=0.4, covered_minutes=12, total_minutes=20, degraded=True)
    repo, _, curator, use, _ = setup()
    mid = seed(repo, DAILY, content=lambda m: with_updates(m, "00:05:00", "00:05:30", "sem hora"), health=health)
    use.execute([mid])
    context = curator.inputs[0].meetings[0]
    expected = excerpt_window(repo.load_transcript(mid), [300, 330], 60, Prompt.EXCERPT_GAP)
    assert context.excerpts == expected and context.health == health and context.title == "Daily"
    lines = expected.split("\n")
    assert lines[0].startswith("[00:04:00] Marina: Fala 240") and lines[-2].startswith("[00:06:30] Marina: Fala 390")
    assert lines[-1] == Prompt.EXCERPT_GAP and Prompt.EXCERPT_GAP not in lines[:-1]     # the two windows overlap: one excerpt
    assert "[00:03:50]" not in expected and "[00:06:40]" not in expected


def test_a_meeting_without_status_updates_has_no_excerpts() -> None:
    repo, _, curator, use, _ = setup()
    use.execute([seed(repo, DAILY)])
    assert curator.inputs[0].meetings[0].excerpts == "" and curator.inputs[0].meetings[0].health is None


# --- edits: apply, repair, fail ---------------------------------------------------------------------------------------

def tick(target: str) -> Op:
    return replace(target, target.replace("[ ]", "[x]", 1))


def test_a_rule_failure_after_the_repair_fails_the_pass_without_committing() -> None:  # UT-034
    document = doc_with(ITEM)
    bad = tick(ITEM)
    repo, store, curator, use, notifier = setup(document, document, [answer([bad])], repairs=[[bad]])
    mid = seed(repo, DAILY)
    result = use.execute([mid])
    assert store.commits == [] and store.document == document and result.curated == ()
    reason = Err.CURATION_BREAKS_RULE.format(target=ITEM[:60])
    assert result.failed == ((mid, reason),)
    assert [(r.kind, r.meetings, r.error, r.retried) for r in store.logged] == [(PassKind.FAILED, (mid,), reason, True)]
    assert repo.curation_errors == {mid: Err.CURATION_FAILED.format(reason=reason)}
    body = Notify.ACTIVITIES_FAILED_BODY.format(title="Daily", meeting_id=mid, error=reason)
    assert notifier.messages == [(Notify.ACTIVITIES_FAILED, body)]
    assert ERROR not in repo.files(mid) and derive_status(repo.files(mid)) == MeetingStatus.ANALYZED   # never error.txt


def test_edits_that_do_not_match_after_the_repair_fail_with_the_count_and_the_first_target() -> None:
    document = doc_with(ITEM)
    ops = [replace("- [ ] não existe 1", "x"), replace("- [ ] não existe 2", "y")]
    repo, store, _, use, _ = setup(document, document, [answer(ops)], repairs=[ops])
    result = use.execute([seed(repo, DAILY)])
    assert result.failed[0][1] == Err.CURATION_NO_MATCH.format(count=2, target="- [ ] não existe 1") and store.commits == []


def test_two_edits_that_do_not_match_get_one_repair_with_the_text_so_far_and_exactly_those_failures() -> None:  # UT-036
    document = doc_with(ITEM)
    good = insert("- [ ] Nova")
    bad = [replace("- [ ] não existe 1", "x"), replace("- [ ] não existe 2", "y")]
    fixed = insert("- [ ] Outra", refs=("1.a2",))
    repo, store, curator, use, _ = setup(document, document, [answer([good, *bad])], repairs=[[fixed]])
    result = use.execute([seed(repo, DAILY)])
    assert len(curator.repair_calls) == 1
    data, current, failures = curator.repair_calls[0]
    assert current == apply_ops(FMT, document, [good]).text and data is curator.inputs[0]
    assert [(f.index, f.op, f.error) for f in failures] == [(1, bad[0], OpError.NOT_FOUND), (2, bad[1], OpError.NOT_FOUND)]
    record = store.commits[0][4]
    assert record.retried and record.retried_by_kind == {"replace": 2} and record.ops_applied == 2 and result.failed == ()
    assert "- [ ] Nova" in store.document and "- [ ] Outra" in store.document


def test_a_transport_error_is_a_failed_pass_with_no_repair() -> None:  # UT-037
    repo, store, curator, use, notifier = setup(doc_with(ITEM), doc_with(ITEM), fail=AnalysisError("Claude Code timed out after 900 s"))
    mid = seed(repo, DAILY)
    result = use.execute([mid])
    assert curator.repair_calls == [] and store.commits == []
    assert result.failed == ((mid, "Claude Code timed out after 900 s"),)
    assert repo.curation_errors[mid] == "Activity curation failed: Claude Code timed out after 900 s"
    assert notifier.messages[0][0] == Notify.ACTIVITIES_FAILED and "Claude Code timed out after 900 s" in notifier.messages[0][1]
    assert [(r.kind, r.retried) for r in store.logged] == [(PassKind.FAILED, False)]


def test_a_rule_failure_goes_to_the_repair_as_that_edit_and_a_repair_that_archives_commits() -> None:  # UT-104
    document = doc_with(ITEM, OTHER)
    bad = replace(ITEM, "")                                    # drops a checkbox line without archiving it
    repo, store, curator, use, _ = setup(document, document, [answer([insert("- [ ] Nova"), bad])], repairs=[[archive(ITEM, "duplicado de: Cronograma")]])
    use.execute([seed(repo, DAILY)])
    (data, current, failures), = curator.repair_calls
    assert [(f.index, f.op, f.error) for f in failures] == [(1, bad, OpError.BREAKS_RULE)] and "target: 1 open" in failures[0].detail
    _, after, archived, _, record = store.commits[0]
    assert archived == [(ITEM, "duplicado de: Cronograma")] and ITEM not in after and "- [ ] Nova" in after and record.retried


def test_a_repair_edit_that_only_matches_the_text_so_far_commits_and_is_not_a_user_edit_next_time() -> None:  # UT-100
    document = doc_with(ITEM)
    first = insert("- [ ] Nova")
    bad = insert("  - sub", after="- [ ] não existe")
    repair = insert("  - sub", after="- [ ] Nova", refs=("1.a2",))     # "- [ ] Nova" exists only in the in-memory text
    repo, store, curator, use, _ = setup(document, document, [answer([first, bad]), answer()], repairs=[[repair]])
    use.execute([seed(repo, DAILY)])
    assert "- [ ] Nova\n  - sub\n" in store.document
    use.execute([seed(repo, datetime(2026, 10, 19, 9, 45), "Outra")])
    assert curator.inputs[1].user_edits == ""


def test_the_refs_no_edit_and_no_ignore_accounts_for_are_recorded() -> None:
    repo, store, _, use, _ = setup(outputs=[answer([insert("- [ ] A", refs=("1.a1",))], ignored=[IgnoredRef("1.o1", "não afeta você")])])
    mid = seed(repo, DAILY, content=lambda m: analysis(m, others_actions=[analysis(m).my_actions[0], analysis(m).my_actions[0]]))
    use.execute([mid])
    assert refs_of(1, repo.load_analysis(mid)) == ["1.a1", "1.o1", "1.o2"]
    assert store.commits[0][4].unaccounted_refs == ("1.o2",) and store.commits[0][4].ignored == 1


# --- archive entries ----------------------------------------------------------------------------------------------------

def test_an_archive_edit_hands_the_removed_text_and_its_reason_to_the_store() -> None:  # UT-040
    agenda = "- qui 15/10 16:30 — Reunião com a Acme · [Revisão SAP 14/10][2026-10-14_10-00-03]"
    document = doc_with(ITEM).replace(FMT.heading_agenda + "\n", FMT.heading_agenda + "\n" + agenda + "\n", 1)
    repo, store, _, use, _ = setup(document, document, [answer([archive(agenda, "data passou (qui 15/10)")])])
    use.execute([seed(repo, DAILY)])
    _, after, archived, _, _ = store.commits[0]
    assert archived == [(agenda, "data passou (qui 15/10)")] and agenda not in after
    assert store.archive.startswith("### data passou (qui 15/10)\n- qui 15/10 16:30")


def test_the_items_the_user_deleted_are_archived_as_removed_by_you() -> None:  # UT-041
    document = doc_with(ITEM)
    gone = "- [ ] **Atualizar o wiki** · [Daily 12/10][2026-10-12_09-30-11]"
    repo, store, _, use, _ = setup(document, document, [answer([], user_removed=[RemovedItem(gone, "apagado por você"), RemovedItem("  ", "vazio")])])
    use.execute([seed(repo, DAILY)])
    assert store.commits[0][2] == [(gone, ActivityDoc.REMOVED_BY_USER)] and store.commits[0][4].user_removed == 2


# --- edits during the call ----------------------------------------------------------------------------------------------

def test_a_line_the_user_deleted_during_the_call_stays_deleted_and_the_edit_that_targeted_it_is_dropped() -> None:  # UT-046
    document = doc_with(ITEM, OTHER)
    holder: dict[str, InMemoryActivityStore] = {}
    curator = FakeActivityCurator([answer([replace(ITEM, ITEM + " (novo prazo)", refs=("1.u1",)), insert("- [ ] Nova")])], repairs=[[]],
                                  during_call=lambda: setattr(holder["s"], "document", holder["s"].document.replace(ITEM + "\n", "")))
    repo = InMemoryMeetingRepository()
    store = holder["s"] = InMemoryActivityStore(document, document)
    use, _, _ = build(repo, store, curator)
    use.execute([seed(repo, DAILY)])
    (_, _, failures), = curator.repair_calls
    assert [f.error for f in failures] == [OpError.NOT_FOUND]
    after = store.document
    assert ITEM not in after and "(novo prazo)" not in after and OTHER in after and "- [ ] Nova" in after
    assert store.commits[0][4].during_edits.count("-" + ITEM) == 1


class Typist:
    """Types a line in the box, once, while the curator is thinking."""

    def __init__(self, store: InMemoryActivityStore, line: str) -> None:
        self.store, self.line, self.done = store, line, False

    def __call__(self) -> None:
        if not self.done:
            self.done = True
            self.store.document = in_box(self.store.document, self.line)


class Rewording:
    """Rewords a line of the document, once, while the curator is thinking."""

    def __init__(self, store: InMemoryActivityStore, old: str, new: str) -> None:
        self.store, self.old, self.new, self.done = store, old, new, False

    def __call__(self) -> None:
        if not self.done:
            self.done = True
            self.store.document = self.store.document.replace(self.old, self.new)


def top_of_actions(document: str) -> str:
    lines = body_text(FMT, document).split("\n")
    return lines[lines.index(ACTIONS) + 1]


def test_a_line_typed_in_the_box_during_the_call_is_put_at_the_top_of_my_actions() -> None:  # UT-047
    typed = "- [ ] Ligar para o João"
    document = doc_with(ITEM)
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore(document, document)
    curator = FakeActivityCurator([answer()])
    curator.during_call = Typist(store, typed)
    use, _, _ = build(repo, store, curator)
    use.execute([seed(repo, DAILY)])
    _, after, _, base, record = store.commits[0]
    assert curator.inputs[0].box_lines == [] and top_of_actions(after) == typed and record.box_rescued == 1
    assert typed not in base and typed not in record.during_edits
    assert typed not in "\n".join(line for line in after.split("\n") if line.startswith(">"))     # the new box is clean


def test_a_box_line_the_curator_moved_is_not_duplicated_and_the_one_it_left_is_rescued() -> None:  # UT-048
    moved, left = "- [ ] Primeira linha", "- [ ] Segunda linha"
    document = in_box(in_box(doc_with(ITEM), moved), left)
    repo, store, curator, use, _ = setup(document, doc_with(ITEM), [answer([insert(moved, refs=())]), answer()])
    use.execute([seed(repo, DAILY)])
    after = store.document
    assert after.count(moved) == 1 and after.count(left) == 1 and store.commits[0][4].box_rescued == 1
    assert top_of_actions(after) == left
    use.execute([seed(repo, datetime(2026, 10, 19, 9, 45), "Outra")])
    edits = curator.inputs[1].user_edits
    assert edits.count("+" + left) == 1 and "+" + moved not in edits


def test_what_the_user_edits_in_the_body_during_the_call_is_the_next_passes_edit_exactly_once() -> None:  # UT-049
    document = doc_with(ITEM, OTHER)
    reworded = OTHER + " e confirmar o chamado"
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore(document, document)
    curator = FakeActivityCurator([answer([insert("- [ ] Nova")]), answer()])
    curator.during_call = Rewording(store, OTHER, reworded)
    use, _, _ = build(repo, store, curator)
    use.execute([seed(repo, DAILY)])
    _, after, _, base, record = store.commits[0]
    assert record.during_edits == unified_diff(body_text(FMT, document), body_text(FMT, document.replace(OTHER, reworded)))
    assert "-" + OTHER in record.during_edits and "+" + reworded in record.during_edits
    assert reworded in base and reworded in after                      # the base is built from the re-read document
    assert "Atualizado" not in record.during_edits and FMT.links_start not in record.during_edits
    use.execute([seed(repo, datetime(2026, 10, 19, 9, 45), "Outra")])
    second = curator.inputs[1].user_edits
    assert second == record.during_edits and second.count("+" + reworded) == 1 and "- [ ] Nova" not in second


def test_a_line_typed_in_the_box_during_the_call_reaches_the_next_pass_once_as_a_body_line() -> None:  # UT-123
    typed = "- [ ] Ligar para o João"
    document = doc_with(ITEM)
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore(document, document)
    curator = FakeActivityCurator([answer(), answer()])
    curator.during_call = Typist(store, typed)
    use, _, _ = build(repo, store, curator)
    use.execute([seed(repo, DAILY)])
    assert store.commits[0][4].during_edits == ""
    use.execute([seed(repo, datetime(2026, 10, 19, 9, 45), "Outra")])
    second = curator.inputs[1]
    assert second.user_edits.count(typed) == 1 and "+" + typed in second.user_edits and second.box_lines == []


# --- failure path and success path -----------------------------------------------------------------------------------

def test_a_successful_pass_clears_the_curation_error_of_its_meetings() -> None:  # UT-039
    repo, store, _, use, _ = setup()
    mid = seed(repo, DAILY)
    repo.mark_curation_failed(mid, "old failure")
    assert CURATION_ERROR in repo.files(mid)
    use.execute([mid])
    assert repo.curation_error(mid) is None and CURATION_ERROR not in repo.files(mid)


def test_a_failure_that_cannot_be_recorded_is_still_the_result_not_an_exception() -> None:
    repo, store, _, use, notifier = setup(fail=AnalysisError("down"))
    store.fail_log = OSError("disk full")
    mid = seed(repo, DAILY)
    result = use.execute([mid])
    assert result.failed == ((mid, "down"),) and notifier.messages and repo.curation_errors


def test_a_poison_meeting_is_isolated_before_it_costs_its_batch_mate_an_attempt() -> None:  # UT-102
    class Poison(FakeActivityCurator):
        def curate(self, data):
            self.fail = AnalysisError("poison") if any(m.meeting_id == poison for m in data.meetings) else None
            return super().curate(data)

    repo = InMemoryMeetingRepository()
    healthy = seed(repo, datetime(2026, 10, 19, 8, 0), "Saudável")
    poison = seed(repo, DAILY, "Veneno")
    store = InMemoryActivityStore()
    curator = Poison([answer([insert("- [ ] Nova")])])
    use, notifier, _ = build(repo, store, curator)
    result = use.execute([poison, healthy])
    assert [(r.kind, r.meetings) for r in result.records] == [
        (PassKind.FAILED, (healthy, poison)), (PassKind.MEETING, (healthy,)), (PassKind.FAILED, (poison,))]
    assert result.curated == (healthy,) and [m for m, _ in result.failed] == [poison]
    assert set(repo.curation_errors) == {poison} and len(notifier.messages) == 1
    assert poison in notifier.messages[0][1] and healthy not in notifier.messages[0][1]
    assert use.pending() == [poison]                                  # one counted failure: still retried
    use.execute([poison])
    assert use.pending() == []                                        # two: no longer added automatically
    assert not any(r.meetings == (healthy,) and r.kind == PassKind.FAILED for r in store.records)


def test_a_commit_left_unfinished_is_neither_a_failed_pass_nor_isolated() -> None:      # review 006, issue 001
    repo = InMemoryMeetingRepository()
    first, second = seed(repo, DAILY), seed(repo, datetime(2026, 10, 19, 9, 45), "Outra")
    store = InMemoryActivityStore()
    store.fail_commit = CommitIncomplete("the activities pass 20261019-101200 replaced the document but could not finish")
    curator = FakeActivityCurator([answer([insert("- [ ] Nova")], notify=True)])
    use, notifier, _ = build(repo, store, curator)
    repo.mark_curation_failed(first, "an earlier failure")

    result = use.execute([first, second])

    assert result.unfinished == str(store.fail_commit) and result.failed == () and result.curated == (first, second)
    assert len(curator.inputs) == 1 and len(result.records) == 1                    # the batch is not re-run meeting by meeting
    assert store.logged == [] and store.records == []                               # no `failed` record: it would hide the set
    assert repo.curation_error(first) is None                                       # its edits are in the document
    assert Notify.ACTIVITIES_FAILED not in [title for title, _ in notifier.messages]


def test_a_new_pass_never_takes_the_name_of_a_version_set_that_is_on_disk() -> None:    # review 006, issue 001
    repo, store, _, use, _ = setup()
    store.versions["20261019-101200"] = VersionFiles("before", "after", None, None)    # an unfinished set: files, no log line yet
    store.versions["20261019-101201"] = VersionFiles("before", "after", None, None)
    use.execute([seed(repo, DAILY)])
    assert store.commits[0][4].version == "20261019-101202"
    assert free_version(store, NOW) == "20261019-101203"


def test_uncurated_keeps_the_ids_with_no_successful_pass_in_the_order_given() -> None:    # review 006, issue 002
    repo, store, _, use, _ = setup()
    done, skipped, failed, never = "2026-10-19_09-10-00", "2026-10-19_09-20-00", "2026-10-19_09-30-00", "2026-10-19_09-40-00"
    store.records += [rec(PassKind.MEETING, done), rec(PassKind.SKIPPED_EMPTY, skipped), rec(PassKind.FAILED, failed)]
    assert use.uncurated([never, done, failed, skipped]) == [never, failed]           # a failed attempt is not a pass; the window is not applied
    assert use.uncurated([]) == []


# --- notifications --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("curator_says", "setting", "sent"), [(True, True, True), (False, True, False), (True, False, False)])
def test_the_curator_notifies_only_when_it_says_so_and_the_setting_allows(curator_says: bool, setting: bool, sent: bool) -> None:  # UT-043, UT-044
    repo = InMemoryMeetingRepository()
    use, notifier, _ = build(repo, InMemoryActivityStore(), FakeActivityCurator([answer(summary="1 ação nova", notify=curator_says)]), notify=setting)
    use.execute([seed(repo, DAILY)])
    assert notifier.messages == ([(Notify.ACTIVITIES_UPDATED, "1 ação nova")] if sent else [])


def test_a_failure_notifies_even_when_notifications_are_off() -> None:  # UT-044
    repo = InMemoryMeetingRepository()
    use, notifier, _ = build(repo, InMemoryActivityStore(), FakeActivityCurator(fail=AnalysisError("down")), notify=False)
    use.execute([seed(repo, DAILY)])
    assert [title for title, _ in notifier.messages] == [Notify.ACTIVITIES_FAILED]


# --- batching and the lock --------------------------------------------------------------------------------------------------

def test_one_pass_takes_the_four_oldest_meetings() -> None:  # UT-042
    repo, store, curator, use, _ = setup()
    ids = [seed(repo, datetime(2026, 10, 19, 8 + n, 0), f"R{n}") for n in range(6)]
    result = use.execute(list(reversed(ids)))
    assert [m.meeting_id for m in curator.inputs[0].meetings] == ids[:4] and len(curator.inputs) == 1
    assert result.curated == tuple(ids[:4]) and store.commits[0][4].meetings == tuple(ids[:4])
    assert batches(list(reversed(ids))) == [ids[:4], ids[4:]] == batches(ids + ids) and next_batch(ids) == ids[:4] and next_batch([]) == []
    use.execute(ids[4:])
    assert store.records[-1].meetings == tuple(ids[4:])


def test_nothing_to_curate_takes_no_lock() -> None:
    _, store, _, use, _ = setup()
    assert use.execute([]).records == () and store.locks == []


def test_a_busy_curator_is_waited_for_once_and_a_free_one_is_not() -> None:  # UT-105
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore(busy=True)
    use, _, _ = build(repo, store, FakeActivityCurator([answer()]))
    mid = seed(repo, DAILY)
    waits: list[str] = []
    result = use.execute([mid], wait=True, on_wait=lambda: waits.append("waiting"))
    assert waits == ["waiting"] and store.locks == [False, True] and result.curated == (mid,)
    store.busy = False
    other = seed(repo, datetime(2026, 10, 19, 9, 45), "Outra")
    use.execute([other], on_wait=lambda: waits.append("again"))
    assert waits == ["waiting"] and store.locks[2:] == [False]


def test_a_busy_curator_without_wait_raises_busy() -> None:
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore(busy=True)
    use, _, _ = build(repo, store, FakeActivityCurator([answer()]))
    with pytest.raises(CuratorBusy):
        use.execute([seed(repo, DAILY)], wait=False)
    assert store.commits == []


def test_versions_are_unique_when_two_passes_share_a_second() -> None:
    repo, store, _, use, _ = setup(outputs=[answer([insert("- [ ] A")]), answer([insert("- [ ] B")])])
    use.execute([seed(repo, DAILY)])
    use.execute([seed(repo, datetime(2026, 10, 19, 9, 45), "Outra")])
    assert [r.version for r in store.records] == ["20261019-101200", "20261019-101201"]
    assert box_stamp(FMT, store.document) == "20261019-101201"


# --- which meetings still need a pass ---------------------------------------------------------------------------------------------

def seeded_week(repo: InMemoryMeetingRepository) -> dict[str, str]:
    ids = {
        "wed": seed(repo, datetime(2026, 10, 14, 10, 0), "Quarta"),
        "thu": seed(repo, datetime(2026, 10, 15, 10, 0), "Quinta"),
        "fri": seed(repo, datetime(2026, 10, 16, 17, 0), "Sexta"),
        "mon_early": seed(repo, datetime(2026, 10, 19, 8, 0), "Segunda cedo"),
        "mon": seed(repo, datetime(2026, 10, 19, 9, 30), "Segunda"),
    }
    transcribed = Meeting.start(datetime(2026, 10, 19, 9, 0), title="Sem análise")      # not analyzed yet: never listed
    repo.seed(transcribed, {TRANSCRIPT_JSON})
    ids["transcribed"] = transcribed.id
    return ids


def test_pending_lists_recent_analyzed_meetings_without_a_pass_and_under_two_attempts() -> None:  # UT-038
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore()
    use, _, _ = build(repo, store, FakeActivityCurator())
    ids = seeded_week(repo)
    store.records += [
        rec(PassKind.MEETING, ids["fri"], version="a"),                                             # curated: out
        rec(PassKind.FAILED, ids["thu"], version="b"), rec(PassKind.FAILED, ids["thu"], version="c"),   # two attempts alone: out
        rec(PassKind.FAILED, ids["mon_early"], ids["mon"], version="d"),                            # a failed batch is no attempt
        rec(PassKind.FAILED, ids["mon"], version="e"),                                              # one attempt: still in
    ]
    assert use.pending() == [ids["mon_early"], ids["mon"]]
    store.records.append(rec(PassKind.SKIPPED_EMPTY, ids["mon"], version="f"))
    assert use.pending() == [ids["mon_early"]]                                                      # skipped_empty is a success


def test_the_window_is_decided_by_the_meetings_own_date_on_a_monday() -> None:  # UT-101
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore()
    use, _, _ = build(repo, store, FakeActivityCurator())                                           # Monday 19/10, day 0
    ids = seeded_week(repo)
    assert use.pending() == [ids["thu"], ids["fri"], ids["mon_early"], ids["mon"]]                  # Thursday 00:00 on; Wednesday out
    assert use.pending(working_days=0) == [ids["mon_early"], ids["mon"]]
    assert [n.meeting_id for n in use.not_curated()] == [ids["wed"], *use.pending()]                # 10 working days reach Wednesday


def test_on_a_saturday_the_window_starts_the_thursday_before() -> None:  # UT-101
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore()
    use, _, _ = build(repo, store, FakeActivityCurator(), now=datetime(2026, 10, 24, 12, 0))
    ids = {n: seed(repo, datetime(2026, 10, d, 9, 0), n) for n, d in (("wed", 21), ("thu", 22), ("fri", 23))}
    assert use.pending() == [ids["thu"], ids["fri"]]


def test_not_curated_gives_the_error_text_or_none_and_leaves_out_the_curated_and_the_old() -> None:  # UT-106
    repo = InMemoryMeetingRepository()
    store = InMemoryActivityStore()
    use, _, _ = build(repo, store, FakeActivityCurator())
    old = seed(repo, datetime(2026, 10, 2, 10, 0), "Velha")                                         # 12 working days back
    edge = seed(repo, datetime(2026, 10, 5, 10, 0), "No limite")                                    # exactly 10
    curated = seed(repo, datetime(2026, 10, 14, 10, 0), "Curada")
    failed = seed(repo, datetime(2026, 10, 15, 10, 0), "Falhou")
    never = seed(repo, datetime(2026, 10, 16, 10, 0), "Nunca")
    store.records.append(rec(PassKind.MEETING, curated))
    repo.mark_curation_failed(failed, "Activity curation failed: Claude Code timed out after 900 s")
    assert old not in {n.meeting_id for n in use.not_curated()}
    assert use.not_curated() == [NotCurated(edge, "No limite", None), NotCurated(failed, "Falhou", "Activity curation failed: Claude Code timed out after 900 s"),
                                 NotCurated(never, "Nunca", None)]

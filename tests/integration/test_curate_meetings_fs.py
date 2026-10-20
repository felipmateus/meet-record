"""`CurateMeetings` on the file-backed store and repository: a rerun, a rejected tick, edits during the call, concurrent passes, a
hard stop reconciled by the box stamp and seen through the next pass (IT-003, IT-004, IT-005, IT-010, IT-013, IT-016, IT-019)."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import pytest

from teams_recorder.adapters.outbound.activities_fs import FsActivityStore
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.application.use_cases.activities import CurateMeetings
from teams_recorder.constants import Activities
from teams_recorder.domain import PassKind, body_text, render_box, unified_diff
from teams_recorder.domain.status import CURATION_ERROR, ERROR
from teams_recorder.messages import Notify
from tests.fakes import FakeActivityCurator, FakeClock, FakeNotifier
from tests.fixtures.curation import ACTIONS, FMT, NOW, SKELETON, answer, archive, insert, rec, replace, seed
from tests.integration.test_activities_store import Faults, HardStop, make_store

DAILY = datetime(2026, 10, 19, 9, 30)
LATER = datetime(2026, 10, 19, 9, 45)
ITEM = "- [ ] **Enviar o cronograma** · [Daily 16/10][2026-10-16_09-30-11]"
OTHER = "- [ ] Ligar para o suporte da VPN"
AGENDA = "- qui 15/10 16:30 — Reunião com a Acme · [Revisão SAP 14/10][2026-10-14_10-00-03]"
PRIMED = "20261016-174000"


def document(*items: str, agenda: str | None = None) -> str:
    text = SKELETON.replace(ACTIONS + "\n\n", ACTIONS + "\n" + "".join(item + "\n" for item in items) + "\n", 1)
    if agenda:
        text = text.replace(FMT.heading_agenda + "\n", FMT.heading_agenda + "\n" + agenda + "\n", 1)
    return render_box(FMT, text, ["foco"], ["Daily"], datetime(2026, 10, 16, 17, 40), PRIMED)[0]


def prime(store: FsActivityStore, text: str) -> None:
    """An earlier committed pass: the document, and the base the next pass will diff against."""
    store.commit(SKELETON, text, [], text, rec(PassKind.MEETING, "2026-10-16_09-30-11", version=PRIMED, ts=datetime(2026, 10, 16, 17, 40)))


class World:
    def __init__(self, tmp_path: Path, store: FsActivityStore | None = None) -> None:
        self.data = tmp_path / "data"
        self.repo = FsMeetingRepository(self.data)
        self.store = store or FsActivityStore(self.data, FMT)
        self.notifier = FakeNotifier()
        self.clock = FakeClock(NOW)

    def use(self, curator: FakeActivityCurator, store: FsActivityStore | None = None) -> CurateMeetings:
        return CurateMeetings(self.repo, store or self.store, curator, self.notifier, self.clock)

    def edit(self, change: Callable[[str], str]) -> None:
        """What the user does in the editor: rewrite the document file."""
        self.store.path().write_text(change(self.store.read_document() or ""), encoding="utf-8")

    def versions(self) -> list[str]:
        return sorted(p.name for p in self.store.versions_dir.glob("*")) if self.store.versions_dir.is_dir() else []


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


class Once:
    """Runs `action` the first time the curator is called, which is while it thinks: the user edits the file then."""

    def __init__(self, action: Callable[[], None]) -> None:
        self.action, self.done = action, False

    def __call__(self) -> None:
        if not self.done:
            self.done = True
            self.action()


def test_curating_a_meeting_again_changes_nothing_but_the_box(world: World) -> None:  # IT-003
    mid = seed(world.repo, DAILY)
    first = answer([insert(f"- [ ] **Enviar o cronograma** · [Daily 19/10][{mid}]")], focus=["**Enviar o cronograma** hoje"])
    world.use(FakeActivityCurator([first, answer(focus=["**Enviar o cronograma** hoje"])])).execute([mid])
    one = world.store.read_document()
    assert one is not None and f"[{mid}]: ../recordings/{mid}/minutes.md" in one and "[2026-10-16_09-30-11]" not in one
    world.clock.advance(minutes=5)
    result = world.use(FakeActivityCurator([answer(focus=["**Enviar o cronograma** hoje"])])).execute([mid])
    two = world.store.read_document()
    assert result.curated == (mid,) and result.edits == 0
    assert two == render_box(FMT, one, ["**Enviar o cronograma** hoje"], ["Daily"], world.clock.now(), "20261019-101700")[0]
    assert body_text(FMT, two) == body_text(FMT, one)
    assert [r.ops_applied for r in world.store.passes()] == [1, 0]


def test_a_tick_the_curator_makes_is_rejected_and_nothing_is_written(world: World) -> None:  # IT-004
    text = document(ITEM, OTHER)
    prime(world.store, text)
    before = world.versions()
    bad = replace(ITEM, ITEM.replace("[ ]", "[x]", 1))
    mid = seed(world.repo, DAILY)
    result = world.use(FakeActivityCurator([answer([insert("- [ ] Nova"), bad])], repairs=[[bad]])).execute([mid])
    assert [m for m, _ in result.failed] == [mid]
    assert world.store.read_document() == text and world.versions() == before and world.store.read_base() == text
    assert [r.kind for r in world.store.passes()] == [PassKind.MEETING, PassKind.FAILED]
    assert world.repo.path(mid, CURATION_ERROR).read_text().startswith("Activity curation failed:")
    assert ERROR not in world.repo.files(mid) and not (world.store.archive_dir.exists() and list(world.store.archive_dir.iterdir()))


def test_an_edit_the_user_makes_while_the_model_thinks_is_kept_and_seen_once_by_the_next_pass(world: World) -> None:  # IT-005
    text = document(ITEM, OTHER)
    prime(world.store, text)
    reworded = OTHER + " e confirmar o chamado"
    curator = FakeActivityCurator([answer([insert("- [ ] Nova")]), answer()])
    curator.during_call = Once(lambda: world.edit(lambda t: t.replace(OTHER, reworded)))
    use = world.use(curator)
    use.execute([seed(world.repo, DAILY)])
    after = world.store.read_document() or ""
    assert reworded in after and "- [ ] Nova" in after and OTHER + "\n" not in after
    record = world.store.passes()[-1]
    assert "+" + reworded in record.during_edits
    use.execute([seed(world.repo, LATER, "Outra")])
    assert curator.inputs[1].user_edits == record.during_edits and curator.inputs[1].user_edits.count("+" + reworded) == 1


def test_a_deleted_line_and_a_box_line_during_the_call(world: World) -> None:  # IT-016
    text = document(ITEM, OTHER)
    prime(world.store, text)
    typed = "- [ ] Ligar para o João"
    curator = FakeActivityCurator([answer([replace(ITEM, ITEM + " (prazo novo)"), insert("- [ ] Nova")]), answer()], repairs=[[]])

    def meanwhile() -> None:
        world.edit(lambda t: t.replace(ITEM + "\n", "").replace(FMT.box_end_prefix, typed + "\n" + FMT.box_end_prefix, 1))

    curator.during_call = Once(meanwhile)
    use = world.use(curator)
    use.execute([seed(world.repo, DAILY)])
    after = world.store.read_document() or ""
    lines = body_text(FMT, after).split("\n")
    assert ITEM not in after and "(prazo novo)" not in after and "- [ ] Nova" in after
    assert lines[lines.index(ACTIONS) + 1] == typed and after.count(typed) == 1       # at the top of Minhas ações, nowhere else
    assert world.store.passes()[-1].box_rescued == 1
    use.execute([seed(world.repo, LATER, "Outra")])
    edits = curator.inputs[1].user_edits
    assert edits.count("-" + ITEM) == 1 and edits.count("+" + typed) == 1 and curator.inputs[1].box_lines == []


def test_the_archive_entry_is_rendered_by_the_store_with_links_one_level_up(world: World) -> None:  # UT-040
    prime(world.store, document(ITEM, agenda=AGENDA))
    mid = seed(world.repo, DAILY)
    world.use(FakeActivityCurator([answer([archive(AGENDA, "data passou (qui 15/10)")])])).execute([mid])
    entry = (world.store.archive_dir / "2026-10.md").read_text()
    assert entry == ("### 19/10/2026 — data passou (qui 15/10)\n" + AGENDA + "\n"
                     "[2026-10-14_10-00-03]: ../../recordings/2026-10-14_10-00-03/minutes.md\n\n")
    assert AGENDA not in (world.store.read_document() or "")
    record = world.store.passes()[-1]
    assert record.archive_file == "arquivo/2026-10.md" and record.archive_bytes_before == 0 and record.archive_bytes_after == len(entry.encode())


def test_two_passes_started_together_are_serialised_and_both_land(world: World) -> None:  # IT-010
    first, second = seed(world.repo, DAILY, "Daily"), seed(world.repo, LATER, "Revisão")
    running, peak, started = [0], [0], threading.Event()
    guard = threading.Lock()

    def watching() -> None:
        with guard:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        started.set()
        time.sleep(0.2)
        with guard:
            running[0] -= 1

    ones = FakeActivityCurator([answer([insert("- [ ] Primeira")], summary="primeira")], during_call=watching)
    twos = FakeActivityCurator([answer([insert("- [ ] Segunda", refs=("1.a1",))], summary="segunda")], during_call=watching)
    results: dict[str, object] = {}
    waits: list[str] = []

    def run(name: str, curator: FakeActivityCurator, meeting: str, on_wait: Callable[[], None] | None = None) -> None:
        results[name] = world.use(curator).execute([meeting], on_wait=on_wait)

    t1 = threading.Thread(target=run, args=("one", ones, first))
    t1.start()
    assert started.wait(10)
    t2 = threading.Thread(target=run, args=("two", twos, second, lambda: waits.append("waited")))
    t2.start()
    t1.join(30)
    t2.join(30)
    assert peak[0] == 1 and waits == ["waited"]
    after = world.store.read_document() or ""
    assert "- [ ] Primeira" in after and "- [ ] Segunda" in after
    records = world.store.passes()
    assert [r.meetings for r in records] == [(first,), (second,)] and len({r.version for r in records}) == 2
    assert twos.inputs[0].document.count("- [ ] Primeira") == 1                     # the second pass started from the first's result


# --- a hard stop, reconciled by the next lock ---------------------------------------------------------------------------------

def stopped_pass(world: World, tmp_path: Path, step: str, ops: list, text: str) -> str:
    """Runs a pass whose commit is killed at `step`; returns the meeting's id."""
    prime(world.store, text)
    store = make_store(tmp_path, Faults(fail_at=step, error=HardStop()))
    mid = seed(world.repo, DAILY)
    with pytest.raises(HardStop):
        world.use(FakeActivityCurator([answer(ops, summary="a passada interrompida")]), store).execute([mid])
    return mid


def test_a_pass_killed_after_the_document_replace_is_completed_by_the_next_pass(tmp_path: Path) -> None:  # IT-013
    world = World(tmp_path)
    text = document(ITEM, agenda=AGENDA)
    mid = stopped_pass(world, tmp_path, "base", [insert("- [ ] Nova"), archive(AGENDA, "data passou")], text)
    replaced = world.store.read_document() or ""
    assert "- [ ] Nova" in replaced and world.store.read_base() == text and [r.meetings for r in world.store.passes()] == [("2026-10-16_09-30-11",)]
    curator = FakeActivityCurator([answer()])
    world.use(curator).execute([seed(world.repo, LATER, "Outra")])
    assert curator.inputs[0].user_edits == ""                       # completed: the pass's own lines are not the user's edits
    assert [r.meetings for r in world.store.passes()][1:] == [(mid,), (curator.inputs[0].meetings[0].meeting_id,)]
    assert (world.store.archive_dir / "2026-10.md").exists() and "Nova" in (world.store.read_base() or "")
    assert world.use(FakeActivityCurator()).pending() == []


def test_a_pass_killed_after_the_replace_and_a_user_edit_after_it_is_still_rolled_forward(tmp_path: Path) -> None:  # IT-019
    world = World(tmp_path)
    mid = stopped_pass(world, tmp_path, "base", [insert("- [ ] Nova"), archive(AGENDA, "data passou")], document(ITEM, agenda=AGENDA))
    world.edit(lambda t: t.replace(ITEM, ITEM + " (editado)"))
    curator = FakeActivityCurator([answer()])
    world.use(curator).execute([seed(world.repo, LATER, "Outra")])
    assert (world.store.archive_dir / "2026-10.md").read_text().startswith("### 19/10/2026 — data passou")       # archive entries kept
    edits = curator.inputs[0].user_edits
    assert "+" + ITEM + " (editado)" in edits and "Nova" not in [line[1:] for line in edits.split("\n") if line[:1] in "+-"]
    assert mid in {m for r in world.store.passes() for m in r.meetings}


def test_a_pass_killed_before_the_replace_is_rolled_back_even_when_the_user_edited_the_file(tmp_path: Path) -> None:  # IT-019
    world = World(tmp_path)
    text = document(ITEM, agenda=AGENDA)
    mid = stopped_pass(world, tmp_path, "document", [insert("- [ ] Nova"), archive(AGENDA, "data passou")], text)
    killed = next(p for p in world.store.versions_dir.glob("*_pass.json"))
    assert killed.exists() and (world.store.archive_dir / "2026-10.md").exists()      # what the stop left behind
    edited = text.replace(ITEM, ITEM + " (editado)")
    world.edit(lambda t: t.replace(ITEM, ITEM + " (editado)"))       # neither the old document nor the pass's `_after`
    curator = FakeActivityCurator([answer()])
    use = world.use(curator)
    with world.store.lock():                                           # the next lock reconciles the stop
        assert not killed.exists() and not (world.store.archive_dir / "2026-10.md").exists()   # rolled back: files and archive entry gone
    assert use.pending() == [mid]                                      # no successful record: the meeting is still to do
    use.execute(use.pending())
    assert curator.inputs[0].user_edits == unified_diff(body_text(FMT, text), body_text(FMT, edited))
    assert AGENDA in curator.inputs[0].document and "Nova" not in curator.inputs[0].user_edits     # never the pass's own lines as edits
    assert use.pending() == [] and [r.meetings for r in world.store.passes()][1:] == [(mid,)]


# --- a commit that fails after the document replace is not a failed pass (review 006, issue 001) --------------------------------

@pytest.mark.parametrize("step", ["base", "log"])
def test_a_persistent_failure_after_the_replace_is_unfinished_not_failed_and_the_next_pass_completes_it(tmp_path: Path, step: str) -> None:
    world = World(tmp_path)
    text = document(ITEM, agenda=AGENDA)
    prime(world.store, text)
    stuck = make_store(tmp_path, Faults(fail_at=step, times=Activities.COMMIT_ATTEMPTS))   # e.g. ENOSPC right after the replace
    mid = seed(world.repo, DAILY)
    ops = [insert("- [ ] Nova do curador"), archive(AGENDA, "data passou")]

    result = world.use(FakeActivityCurator([answer(ops, summary="a passada")]), stuck).execute([mid])

    assert result.failed == () and result.curated == (mid,) and result.unfinished is not None
    assert "Nova do curador" in (world.store.read_document() or "")          # the edits are in the document
    assert PassKind.FAILED not in {r.kind for r in world.store.passes()}      # no `failed` record: it would take the set's version
    assert world.repo.curation_error(mid) is None and Notify.ACTIVITIES_FAILED not in [title for title, _ in world.notifier.messages]
    assert world.versions() and len({name.partition("_")[0] for name in world.versions()}) == 2   # the primed set and the unfinished one

    curator = FakeActivityCurator([answer()])
    other = seed(world.repo, LATER, "Outra")
    world.use(curator).execute([other])

    assert curator.inputs[0].user_edits == ""                                 # completed: the curator's own lines are not the user's
    assert [(r.kind, r.meetings) for r in world.store.passes()] == [
        (PassKind.MEETING, ("2026-10-16_09-30-11",)), (PassKind.MEETING, (mid,)), (PassKind.MEETING, (other,))]
    assert "Nova do curador" in (world.store.read_base() or "") and world.use(FakeActivityCurator()).pending() == []
    assert "data passou" in (world.store.archive_dir / "2026-10.md").read_text()


def test_an_unfinished_pass_of_several_meetings_is_not_rerun_one_meeting_at_a_time(tmp_path: Path) -> None:
    world = World(tmp_path)
    prime(world.store, document(ITEM, agenda=AGENDA))
    stuck = make_store(tmp_path, Faults(fail_at="base", times=Activities.COMMIT_ATTEMPTS))
    first, second = seed(world.repo, DAILY), seed(world.repo, LATER, "Outra")
    curator = FakeActivityCurator([answer([insert("- [ ] Nova do curador"), archive(AGENDA, "data passou")])])

    result = world.use(curator, stuck).execute([first, second])

    assert len(curator.inputs) == 1 and len(result.records) == 1 and result.failed == ()   # no isolation on top of the unfinished set
    with world.store.lock():
        pass
    assert [r.meetings for r in world.store.passes()][1:] == [(first, second)]
    archived = (world.store.archive_dir / "2026-10.md").read_text()
    assert archived.count("data passou") == 1 and AGENDA in archived          # the entry stays: nothing truncated it
    assert AGENDA not in (world.store.read_document() or "")


class FirstCallFails(FakeActivityCurator):
    """The batch call of a pass of several meetings fails, so the use case isolates; the later calls answer as scripted."""

    def curate(self, data):  # type: ignore[no-untyped-def]
        if not self.inputs:
            self.inputs.append(data)
            raise RuntimeError("batch call failed")
        return super().curate(data)


def test_an_isolated_rerun_left_unfinished_stops_the_round_and_the_next_lock_loses_nothing(tmp_path: Path) -> None:
    world = World(tmp_path)
    prime(world.store, document(ITEM, agenda=AGENDA))
    stuck = make_store(tmp_path, Faults(fail_at="base", times=Activities.COMMIT_ATTEMPTS))
    first, second = seed(world.repo, DAILY), seed(world.repo, LATER, "Outra")
    curator = FirstCallFails([answer([insert("- [ ] Nova do curador A"), archive(AGENDA, "data passou")], summary="A"),
                              answer([archive(ITEM, "concluido B")], summary="B")])

    result = world.use(curator, stuck).execute([first, second])

    assert len(curator.inputs) == 2                                       # the failed batch and meeting A alone; B waits for the next lock
    assert [(r.kind, r.meetings) for r in result.records] == [(PassKind.FAILED, (first, second)), (PassKind.MEETING, (first,))]
    assert result.unfinished is not None and result.curated == (first,) and result.failed == () and result.deferred == (second,)
    assert world.repo.curation_error(first) is None and world.repo.curation_error(second) is None

    with world.store.lock():                                              # reconciles: rolls A's set forward
        pass
    archived = (world.store.archive_dir / "2026-10.md").read_text()
    document_now = world.store.read_document() or ""
    assert "Nova do curador A" in document_now and AGENDA not in document_now and archived.count("data passou") == 1
    assert world.use(FakeActivityCurator()).pending() == [second]         # A has its record; only B is still to do

    after = FakeActivityCurator([answer([archive(ITEM, "concluido B")], summary="B")])
    world.use(after).execute([second])

    assert after.inputs[0].user_edits == ""                               # A's lines are not the user's
    final = (world.store.archive_dir / "2026-10.md").read_text()
    assert AGENDA in final and ITEM in final and final.count("data passou") == 1 and final.count("concluido B") == 1
    assert ITEM not in (world.store.read_document() or "") and world.use(FakeActivityCurator()).pending() == []
    assert [r.meetings for r in world.store.passes() if r.kind == PassKind.MEETING][1:] == [(first,), (second,)]   # each curated once

"""Task 4.0 of the fidelity guard: unconfirmed claims are marked (never dropped) in the minutes, kept out of story
sources, published marked on task cards, and degraded source transcripts are announced in the drafts."""
import json
from datetime import date, datetime
from pathlib import Path

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.minutes_markdown import MarkdownMinutesRenderer
from teams_recorder.adapters.outbound.planner_claude import build_user_message
from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.application.use_cases import DraftUserStories, PublishUserStories
from teams_recorder.config import load_settings
from teams_recorder.constants import Files
from teams_recorder.domain import (
    Action,
    ActionKind,
    Analysis,
    DailyPlan,
    Deadline,
    Decision,
    Meeting,
    Segment,
    StoryDrafts,
    Transcript,
    TranscriptHealth,
    UserStory,
    Verification,
    VerificationStatus,
    task_card,
)
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Minutes, StoryDoc
from tests.fakes import FakeStoryPublisher, FakeStoryRenderer, FakeStoryWriter

YES = Verification(VerificationStatus.CONFIRMED, "dito em 00:01:10")
NO = Verification(VerificationStatus.UNCONFIRMED, "a transcrição não diz quem fará")
DEGRADED = TranscriptHealth(0.668, 28, 86, True, ((0, 14), (15, 59)))


def _meeting() -> Meeting:
    m = Meeting.start(datetime(2026, 10, 14, 9, 0, 0))
    m.ended_at = datetime(2026, 10, 14, 9, 30, 0)
    return m


def _analysis(verified: bool) -> Analysis:
    v = (lambda x: x) if verified else (lambda x: None)
    return Analysis(
        meeting_id="m", summary="s", participants=["Felipe", "Marcos"],
        decisions=[Decision("Usar o Mapbox", "00:01:10", v(YES)), Decision("Cancelar o piloto", None, v(NO))],
        my_actions=[Action("Enviar o cronograma", "usuário", "m", verification=v(NO))],
        deadlines=[Deadline("Piloto", date(2026, 10, 30), "Ana", v(Verification(VerificationStatus.UNCONFIRMED, "data | não dita")))],
        participant_checks={"Marcos": NO} if verified else {},
    )


# --- minutes ------------------------------------------------------------------------------------
def test_unconfirmed_claims_are_marked_with_their_reason_and_kept():
    md = MarkdownMinutesRenderer("Felipe").render(_meeting(), _analysis(verified=True))
    assert Minutes.UNCONFIRMED_LEGEND in md
    assert "- Usar o Mapbox `[00:01:10]`\n" in md                                             # confirmed: unchanged
    assert "- Cancelar o piloto ⚠️ _a confirmar: a transcrição não diz quem fará_" in md
    assert "| 1 | Enviar o cronograma ⚠️ _a confirmar: a transcrição não diz quem fará_ | Felipe (você) |" in md
    assert "- Piloto — 30/10/2026 · Ana ⚠️ _a confirmar: data | não dita_" in md               # outside the table, pipes are fine
    assert "👥 **Participantes:** Felipe, Marcos ⚠️ _a confirmar: a transcrição não diz quem fará_" in md


def test_a_reason_in_the_action_table_cannot_break_it():
    a = _analysis(verified=True)
    a.my_actions[0].verification = Verification(VerificationStatus.UNCONFIRMED, "dono | data")
    assert "Enviar o cronograma ⚠️ _a confirmar: dono / data_ |" in MarkdownMinutesRenderer().render(_meeting(), a)


def test_unverified_minutes_are_exactly_as_before():
    unverified = MarkdownMinutesRenderer("Felipe").render(_meeting(), _analysis(verified=False))
    assert "⚠️ _a confirmar" not in unverified and Minutes.UNCONFIRMED_LEGEND not in unverified
    only_confirmed = _analysis(verified=False)
    only_confirmed.decisions[0] = Decision("Usar o Mapbox", "00:01:10", YES)
    assert MarkdownMinutesRenderer("Felipe").render(_meeting(), only_confirmed) == unverified


# --- planner ------------------------------------------------------------------------------------
def test_the_planner_receives_the_marks_and_is_told_what_they_mean():
    unconfirmed = Action("Enviar o cronograma", "usuário", "m", verification=NO)
    message = build_user_message(date(2026, 10, 14), [_analysis(verified=True)], None, [], [unconfirmed], [])
    assert '"status": "unconfirmed"' in message and "a transcrição não diz quem fará" in message
    prompt = (load_settings().prompts_dir / Files.PLAN_PROMPT).read_text(encoding="utf-8")
    assert "`verification.status` is `unconfirmed`" in prompt and '"(a confirmar)"' in prompt and "never drop it" in prompt


# --- stories ------------------------------------------------------------------------------------
def test_an_unconfirmed_action_is_never_a_story_source_but_a_task_card_keeps_its_mark(repo, notifier, clock):
    day = clock.now().date()
    actions = [
        Action("Exportar horas", "usuário", "m0", id="f1", kind=ActionKind.FEATURE, verification=YES),
        Action("Corrigir o login", "usuário", "m0", id="b1", kind=ActionKind.BUG, verification=NO),
        Action("Mapa offline", "usuário", "m0", id="u1", kind=ActionKind.FEATURE),   # never verified: as before
        Action("Estimar o mapa", "usuário", "m0", id="t1", kind=ActionKind.TECHNICAL, verification=NO),
    ]
    repo.save_plan(DailyPlan(day, "# plan", new_actions=actions))
    writer = FakeStoryWriter()

    drafts = DraftUserStories(repo, writer, FakeStoryRenderer(), notifier).execute(day)

    assert [a.id for a in writer.calls[0][1]] == ["f1", "u1"]   # the unconfirmed bug never reaches the writer
    skipped = {k.action_id: k.reason for k in drafts.skipped}
    assert skipped == {"b1": StoryDoc.NOT_CONFIRMED.format(reason="a transcrição não diz quem fará")}
    card = next(s for s in drafts.stories if s.is_task_card)
    assert card.source_action_ids == ["t1"] and card.verification == NO   # PRD decision 10: published marked


def test_a_reason_less_unconfirmed_action_is_still_left_out(repo, notifier, clock):
    day = clock.now().date()
    bare = Action("Corrigir o login", "usuário", "m0", id="b1", kind=ActionKind.BUG,
                  verification=Verification(VerificationStatus.UNCONFIRMED))
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[bare]))
    drafts = DraftUserStories(repo, FakeStoryWriter(), FakeStoryRenderer(), notifier).execute(day)
    assert [(k.action_id, k.reason) for k in drafts.skipped] == [("b1", StoryDoc.NOT_CONFIRMED_NO_REASON)]


def test_degraded_source_meetings_reach_the_renderer_when_drafting_and_publishing(repo, notifier, clock, meeting):
    day = clock.now().date()
    healthy = Meeting.start(datetime(2026, 10, 6, 15, 0, 0))
    repo.seed(meeting, {AUDIO, TRANSCRIPT_JSON}, transcript=Transcript([Segment(0, 1, "A CIDADE NO BRASIL")], health=DEGRADED))
    repo.seed(healthy, {AUDIO, TRANSCRIPT_JSON}, transcript=Transcript([Segment(0, 1, "oi")], health=TranscriptHealth(0.0, 1, 1, False)))
    actions = [Action("Exportar horas", "usuário", meeting.id, id="f1"), Action("Mapa", "usuário", healthy.id, id="f2"),
               Action("De uma reunião apagada", "usuário", "gone", id="f3")]
    repo.save_plan(DailyPlan(day, "# plan", new_actions=actions))
    renderer = FakeStoryRenderer()

    DraftUserStories(repo, FakeStoryWriter(), renderer, notifier).execute(day)
    PublishUserStories(repo, [FakeStoryPublisher()], renderer, notifier, clock).execute(day)

    assert renderer.degraded[0] == {meeting.id: DEGRADED} and renderer.degraded[-1] == {meeting.id: DEGRADED}


def test_the_drafts_document_shows_the_banner_and_the_card_mark():
    card = task_card(Action("Estimar o mapa", "usuário", "m0", id="t1", kind=ActionKind.TECHNICAL, verification=NO))
    drafts = StoryDrafts(date(2026, 10, 14), [card])
    md = MarkdownStoryRenderer().render(drafts, [], [], {"2026-10-08_10-30-52": DEGRADED})
    assert StoryDoc.DEGRADED.format(meeting="2026-10-08_10-30-52", loop=0.668,
                                    gaps=Minutes.DEGRADED_GAPS.format(ranges="00:00:00–00:14:00, 00:15:00–00:59:00")) in md
    assert StoryDoc.UNCONFIRMED.format(reason="a transcrição não diz quem fará") in md
    plain = MarkdownStoryRenderer().render(StoryDrafts(date(2026, 10, 14), [task_card(Action("Estimar", "usuário", "m0", id="t2"))]), [], [])
    assert "⚠️" not in plain


def test_a_marked_card_carries_the_mark_into_the_board_description(tmp_path: Path):
    publisher = BacklogMdPublisher(tmp_path, "Triagem", ("teams-recorder",))
    card = task_card(Action("Estimar o mapa", "usuário", "m0", id="t1", kind=ActionKind.TECHNICAL, verification=NO))
    body = publisher.body(card, date(2026, 10, 14))
    assert body.startswith(StoryDoc.UNCONFIRMED.format(reason="a transcrição não diz quem fará") + "\n\n")
    assert "⚠️" not in publisher.body(task_card(Action("Estimar", "usuário", "m0", id="t2")), date(2026, 10, 14))


def test_a_card_mark_survives_saving_and_unmarked_stories_are_written_as_before():
    card = task_card(Action("Estimar o mapa", "usuário", "m0", id="t1", kind=ActionKind.TECHNICAL, verification=NO))
    assert codec.story_from_dict(json.loads(json.dumps(codec.story_to_dict(card)))) == card
    assert "verification" not in codec.story_to_dict(UserStory("s", "n"))



# --- review fixes -----------------------------------------------------------------------------
def test_a_reason_with_line_breaks_or_markdown_stays_on_one_line_and_in_italics():
    a = Analysis(meeting_id="m", summary="s", my_actions=[
        Action("Enviar", "Ana", "m", verification=Verification(VerificationStatus.UNCONFIRMED, "dono errado:\nquem disse foi a_ana *x*")),
        Action("Outra", "Bruno", "m"),
    ])
    rows = [line for line in MarkdownMinutesRenderer().render(_meeting(), a).splitlines() if line.startswith("| ")]
    assert rows[1] == "| 1 | Enviar ⚠️ _a confirmar: dono errado: quem disse foi a\\_ana \\*x\\*_ | Ana | — | — | — |"
    assert rows[2].startswith("| 2 | Outra |") and len(rows) == 3   # the table is intact


def test_the_verifier_hands_back_one_line_reasons():
    from teams_recorder.adapters.outbound.verifier_claude import Claim, VerdictOut, to_verification
    from teams_recorder.domain import ClaimKind, ClaimRef
    claim = Claim("c1", ClaimRef(ClaimKind.DECISION, "0"), "Usar o Mapbox")
    verdict = VerdictOut(id="c1", support="unsupported", owner_evident=None, date_said=None, tentative=False, sensitive=False,
                         reason="  ninguém disse\n  isso  ")
    assert to_verification(claim, verdict).reason == "ninguém disse isso"


def test_without_a_reason_the_card_mark_does_not_repeat_itself(tmp_path: Path):
    bare = task_card(Action("Estimar", "usuário", "m0", id="t1", kind=ActionKind.TECHNICAL,
                            verification=Verification(VerificationStatus.UNCONFIRMED)))
    body = BacklogMdPublisher(tmp_path, "Triagem", ()).body(bare, date(2026, 10, 14))
    assert body.startswith(StoryDoc.UNCONFIRMED_NO_REASON)
    assert StoryDoc.UNCONFIRMED_NO_REASON in MarkdownStoryRenderer().render(StoryDrafts(date(2026, 10, 14), [bare]), [], [])


def test_the_drafts_banner_lists_every_gap_like_the_minutes():
    health = TranscriptHealth(0.5, 10, 30, True, ((0, 2), (4, 6), (8, 10), (12, 14), (20, 25)))
    md = MarkdownStoryRenderer().render(StoryDrafts(date(2026, 10, 14)), [], [], {"m": health})
    assert "00:20:00–00:25:00. O que veio dela" in md and " and " not in md   # no English, no cut-off list


def test_an_unconfirmed_plan_only_action_is_marked_in_the_drafts(repo, notifier, clock):
    day = clock.now().date()
    email = Action("Mandar o e-mail", "usuário", "m0", id="c1", kind=ActionKind.COMMUNICATION, verification=NO)
    report = Action("Atualizar o relatório", "usuário", "m0", id="g1", kind=ActionKind.MANAGEMENT)
    repo.save_plan(DailyPlan(day, "# plan", new_actions=[email, report]))
    drafts = DraftUserStories(repo, FakeStoryWriter(), FakeStoryRenderer(), notifier).execute(day)
    reasons = {k.action_id: k.reason for k in drafts.skipped}
    assert reasons["c1"] == (StoryDoc.PLAN_ONLY.format(kind=StoryDoc.KIND_LABELS["communication"])
                             + StoryDoc.UNCONFIRMED_SUFFIX.format(reason="a transcrição não diz quem fará"))
    assert reasons["g1"] == StoryDoc.PLAN_ONLY.format(kind=StoryDoc.KIND_LABELS["management"])   # unverified: as before

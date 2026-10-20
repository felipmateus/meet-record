"""Task 4.0 of the fidelity guard: unconfirmed claims are marked (never dropped) in the minutes, published marked on stored task
cards, and degraded source transcripts are announced in the drafts."""
import json
from datetime import date, datetime
from pathlib import Path

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.minutes_markdown import MarkdownMinutesRenderer
from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.domain import (
    Action,
    ActionKind,
    Analysis,
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
)
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Minutes, StoryDoc

YES = Verification(VerificationStatus.CONFIRMED, "dito em 00:01:10")
NO = Verification(VerificationStatus.UNCONFIRMED, "a transcrição não diz quem fará")
DEGRADED = TranscriptHealth(0.668, 28, 86, True, ((0, 14), (15, 59)))


def stored_card(title: str, verification: Verification | None = None) -> UserStory:
    """A task card as the planner stored it: its action's verification travels with it."""
    return UserStory(title, "", source_action_ids=["t1"], source_meetings=["m0"], kind=ActionKind.TECHNICAL, verification=verification)


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


# --- stories ------------------------------------------------------------------------------------
def test_the_drafts_document_shows_the_banner_and_the_card_mark():
    card = stored_card("Estimar o mapa", NO)
    drafts = StoryDrafts(date(2026, 10, 14), [card])
    md = MarkdownStoryRenderer().render(drafts, [], {"2026-10-08_10-30-52": DEGRADED})
    assert StoryDoc.DEGRADED.format(meeting="2026-10-08_10-30-52", loop=0.668,
                                    gaps=Minutes.DEGRADED_GAPS.format(ranges="00:00:00–00:14:00, 00:15:00–00:59:00")) in md
    assert StoryDoc.UNCONFIRMED.format(reason="a transcrição não diz quem fará") in md
    assert md.count(StoryDoc.NOT_VERIFIED.format(meeting="2026-10-08_10-30-52")) == 1   # verification skipped it (task 7.0)
    plain = MarkdownStoryRenderer().render(StoryDrafts(date(2026, 10, 14), [stored_card("Estimar")]), [])
    assert "⚠️" not in plain


def test_a_marked_card_carries_the_mark_into_the_board_description(tmp_path: Path):
    publisher = BacklogMdPublisher(tmp_path, "Triagem", ("teams-recorder",))
    card = stored_card("Estimar o mapa", NO)
    body = publisher.body(card, date(2026, 10, 14))
    assert body.startswith(StoryDoc.UNCONFIRMED.format(reason="a transcrição não diz quem fará") + "\n\n")
    assert "⚠️" not in publisher.body(stored_card("Estimar"), date(2026, 10, 14))


def test_a_card_mark_survives_saving_and_unmarked_stories_are_written_as_before():
    card = stored_card("Estimar o mapa", NO)
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
    bare = stored_card("Estimar", Verification(VerificationStatus.UNCONFIRMED))
    body = BacklogMdPublisher(tmp_path, "Triagem", ()).body(bare, date(2026, 10, 14))
    assert body.startswith(StoryDoc.UNCONFIRMED_NO_REASON)
    assert StoryDoc.UNCONFIRMED_NO_REASON in MarkdownStoryRenderer().render(StoryDrafts(date(2026, 10, 14), [bare]), [])


def test_the_drafts_banner_lists_every_gap_like_the_minutes():
    health = TranscriptHealth(0.5, 10, 30, True, ((0, 2), (4, 6), (8, 10), (12, 14), (20, 25)))
    md = MarkdownStoryRenderer().render(StoryDrafts(date(2026, 10, 14)), [], {"m": health})
    assert "00:20:00–00:25:00. O que veio dela" in md and " and " not in md   # no English, no cut-off list


def test_a_source_meeting_recorded_at_the_wrong_rate_gets_its_own_banner_in_the_drafts(clock, meeting):
    day = clock.now().date()
    wrong_rate = TranscriptHealth(0.0, 12, 12, False, rate_mismatch=True, short_padding_share=0.669)
    md = MarkdownStoryRenderer().render(StoryDrafts(day), [], {meeting.id: wrong_rate})
    assert StoryDoc.RATE_MISMATCH.format(meeting=meeting.id, share=0.669) in md
    assert md.index(StoryDoc.RATE_MISMATCH.split("{meeting}")[0]) < md.index(StoryDoc.NOT_VERIFIED.format(meeting=meeting.id))
    assert StoryDoc.DEGRADED.split("{meeting}")[0] not in md   # only the banner that applies

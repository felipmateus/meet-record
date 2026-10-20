from datetime import date, datetime, timedelta

from teams_recorder.domain import (
    Action,
    ActionKind,
    Meeting,
    Publication,
    Segment,
    StoryDrafts,
    Transcript,
    UserStory,
    meeting_id_for,
)


def test_meeting_id_format():
    assert meeting_id_for(datetime(2026, 10, 6, 14, 5, 9)) == "2026-10-06_14-05-09"


def test_meeting_start_and_duration():
    start = datetime(2026, 10, 6, 14, 0, 0)
    m = Meeting.start(start, pid=7)
    assert m.id == "2026-10-06_14-00-00"
    assert m.day == date(2026, 10, 6)
    assert m.duration_seconds is None
    m.ended_at = start + timedelta(minutes=45)
    assert m.duration_seconds == 2700


def test_transcript_text_and_timestamps():
    t = Transcript(segments=[Segment(0.0, 2.0, " Olá "), Segment(2.0, 65.5, "tudo bem?"), Segment(65.5, 66.0, "  ")])  # Portuguese speech is data
    assert t.text == "Olá\ntudo bem?"
    assert t.duration_seconds == 66.0
    lines = t.as_timestamped_text().splitlines()
    assert lines[0] == "[00:00:00] Olá"
    assert lines[1] == "[00:00:02] tudo bem?"


def test_empty_transcript():
    assert Transcript().text == ""
    assert Transcript().duration_seconds == 0.0


def test_action_ids_are_unique():
    assert Action("a", "me", "m").id != Action("a", "me", "m").id


def test_story_publication_lookup_and_drafts_state():
    published = Publication("backlog-md", "TASK-7", datetime(2026, 10, 10, 18, 5))
    story = UserStory("Exportar horas", "Como gestor, quero exportar", publications=[published])
    draft = UserStory("Outra", "Como analista, quero algo")

    assert story.publication("backlog-md") is published
    assert story.publication("github") is None
    assert not StoryDrafts(date(2026, 10, 9)).has_publications
    assert not StoryDrafts(date(2026, 10, 9), [draft]).has_publications
    assert StoryDrafts(date(2026, 10, 9), [draft, story]).has_publications


def test_a_task_card_is_decided_by_the_stored_kind():
    assert {k: UserStory("s", "", kind=k).is_task_card for k in ActionKind} == {
        ActionKind.FEATURE: False, ActionKind.BUG: False, ActionKind.TECHNICAL: True, ActionKind.OPERATION: True,
        ActionKind.MANAGEMENT: False, ActionKind.COMMUNICATION: False}
    assert not UserStory("s", "").is_task_card


def test_claims_are_not_verified_until_a_check_says_so():
    from teams_recorder.domain import Analysis, Deadline, Decision, Verification, VerificationStatus
    assert Decision("Usar o Mapbox").verification is None
    assert Deadline("Relatório", None, "Ana").verification is None
    assert Action("Enviar o relatório", "me", "m1").verification is None
    assert Analysis(meeting_id="m1", summary="s").participant_checks == {}
    unconfirmed = Verification(VerificationStatus.UNCONFIRMED, "a transcrição não diz quem fará")
    assert Verification(VerificationStatus.CONFIRMED).reason == ""
    assert Decision("Usar o Mapbox", "00:01:02", unconfirmed) != Decision("Usar o Mapbox", "00:01:02")   # part of the claim's value
    assert VerificationStatus("unconfirmed") is VerificationStatus.UNCONFIRMED

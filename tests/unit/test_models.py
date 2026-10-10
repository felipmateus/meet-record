from datetime import date, datetime, timedelta

from teams_recorder.domain import (
    Action,
    ActionKind,
    ActionRoute,
    ActionStatus,
    DailyPlan,
    Meeting,
    Priority,
    Publication,
    Segment,
    StoryDrafts,
    Transcript,
    UserStory,
    earliest_due,
    meeting_id_for,
    merge_open_actions,
    route_of,
    story_kind,
    strongest_priority,
    task_card,
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


def test_action_overdue():
    a = Action("x", "me", "m1", due=date(2026, 10, 5))
    assert a.is_overdue_on(date(2026, 10, 6))
    assert not a.is_overdue_on(date(2026, 10, 5))
    a.status = ActionStatus.DONE
    assert not a.is_overdue_on(date(2026, 10, 6))
    assert not Action("y", "me", "m1").is_overdue_on(date(2026, 10, 6))


def test_action_ids_are_unique():
    assert Action("a", "me", "m").id != Action("a", "me", "m").id


def test_merge_open_actions():
    keep = Action("keep", "me", "m1", id="keep")
    done = Action("done", "me", "m1", id="done")
    late = Action("late", "me", "m1", id="late", due=date(2026, 10, 1))
    new = Action("new", "me", "m2", id="new")
    dup = Action("duplicate", "me", "m2", id="keep")
    plan = DailyPlan(date(2026, 10, 6), "", new_actions=[new, dup], completed_action_ids=["done"], overdue_action_ids=["late"])

    result = merge_open_actions([keep, done, late], plan)

    ids = [a.id for a in result]
    assert ids == ["keep", "late", "new"]
    assert late.status == ActionStatus.OVERDUE
    assert keep.status == ActionStatus.OPEN


def test_story_priority_and_due_come_from_the_actions():
    low = Action("a", "me", "m", priority=Priority.LOW, due=date(2026, 10, 20))
    high = Action("b", "me", "m", priority=Priority.HIGH)
    unstated = Action("c", "me", "m", due=date(2026, 10, 12))
    assert strongest_priority([low, high, unstated]) == Priority.HIGH
    assert strongest_priority([unstated]) is None
    assert earliest_due([low, high, unstated]) == date(2026, 10, 12)
    assert earliest_due([high]) is None


def test_story_publication_lookup_and_drafts_state():
    published = Publication("backlog-md", "TASK-7", datetime(2026, 10, 10, 18, 5))
    story = UserStory("Exportar horas", "Como gestor, quero exportar", publications=[published])
    draft = UserStory("Outra", "Como analista, quero algo")

    assert story.publication("backlog-md") is published
    assert story.publication("github") is None
    assert not StoryDrafts(date(2026, 10, 9)).has_publications
    assert not StoryDrafts(date(2026, 10, 9), [draft]).has_publications
    assert StoryDrafts(date(2026, 10, 9), [draft, story]).has_publications


def test_action_kinds_route_and_shape_story_cards():
    assert {k: k.route for k in ActionKind} == {
        ActionKind.FEATURE: ActionRoute.STORY, ActionKind.BUG: ActionRoute.STORY,
        ActionKind.TECHNICAL: ActionRoute.TASK, ActionKind.OPERATION: ActionRoute.TASK,
        ActionKind.MANAGEMENT: ActionRoute.PLAN, ActionKind.COMMUNICATION: ActionRoute.PLAN,
    }
    assert route_of(None) is ActionRoute.STORY and Action("x", "me", "m").route is ActionRoute.STORY   # unclassified: as before
    feature = Action("a", "me", "m", kind=ActionKind.FEATURE)
    bug = Action("b", "me", "m", kind=ActionKind.BUG)
    assert story_kind([feature, bug]) == ActionKind.BUG and story_kind([feature]) == ActionKind.FEATURE
    assert story_kind([Action("c", "me", "m")]) is None
    estimate = Action("Estimar horas da nova tela", "me", "m1", id="t1", priority=Priority.HIGH, due=date(2026, 10, 9), kind=ActionKind.TECHNICAL)
    card = task_card(estimate)
    assert (card.title, card.narrative, card.kind) == ("Estimar horas da nova tela", "", ActionKind.TECHNICAL)
    assert card.is_task_card and not UserStory("s", "n", kind=ActionKind.FEATURE).is_task_card
    assert card.source_action_ids == ["t1"] and card.source_meetings == ["m1"] and card.priority == Priority.HIGH and card.due == date(2026, 10, 9)

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.domain import (
    Action,
    DailyPlan,
    Meeting,
    MeetingNotFound,
    MeetingStatus,
    Priority,
    Publication,
    RepositoryError,
    SkippedAction,
    StoryDrafts,
    UserStory,
    derive_status,
)
from teams_recorder.domain.status import ANALYSIS, AUDIO, ERROR, LOCK, META, TRANSCRIPT_JSON, TRANSCRIPT_TXT

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def fs(tmp_path: Path) -> FsMeetingRepository:
    return FsMeetingRepository(tmp_path / "data")


def test_create_and_meta_roundtrip(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0), pid=9, title="Daily")
    fs.create(m)
    assert fs.exists(m.id)
    assert fs.files(m.id) == {META}
    assert derive_status(fs.files(m.id)) == MeetingStatus.RECORDING

    m.ended_at = m.started_at + timedelta(minutes=10)
    fs.save_meta(m)
    loaded = fs.load_meta(m.id)
    assert loaded == m
    assert fs.list_meetings() == [m]


def test_create_twice_fails(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0))
    fs.create(m)
    with pytest.raises(RepositoryError):
        fs.create(m)


def test_unknown_meeting(fs: FsMeetingRepository):
    with pytest.raises(MeetingNotFound):
        fs.load_meta("nada")
    assert not fs.exists("nada")


def test_transcript_roundtrip_from_fixture(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    transcript = codec.transcript_from_dict(json.loads((FIXTURES / "sample_transcript.json").read_text()))

    fs.save_transcript(m.id, transcript)

    assert {TRANSCRIPT_JSON, TRANSCRIPT_TXT} <= fs.files(m.id)
    assert fs.load_transcript(m.id) == transcript
    txt = fs.path(m.id, TRANSCRIPT_TXT).read_text()
    assert txt.startswith("[00:00:00] Bom dia")
    assert "[00:00:09] Combinado." in txt


def test_analysis_roundtrip_from_fixture(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    analysis = codec.analysis_from_dict(json.loads((FIXTURES / "sample_analysis.json").read_text()))

    fs.save_analysis(m.id, analysis)

    loaded = fs.load_analysis(m.id)
    assert loaded == analysis
    assert loaded.my_actions[0].due == date(2026, 10, 7)
    assert loaded.deadlines[0].who == "Felipe"
    assert derive_status(fs.files(m.id)) == MeetingStatus.ANALYZED


def test_lock_is_exclusive_and_released(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    with fs.lock(m.id):
        assert LOCK in fs.files(m.id)
        with pytest.raises(RepositoryError):
            with fs.lock(m.id):
                pass
    assert LOCK not in fs.files(m.id)


def test_failed_marks_and_clears(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    fs.mark_failed(m.id, "transcription: whisper failed")
    assert fs.path(m.id, ERROR).read_text() == "transcription: whisper failed\n"
    assert derive_status(fs.files(m.id)) == MeetingStatus.FAILED
    fs.clear_failed(m.id)
    assert ERROR not in fs.files(m.id)


def test_delete_file_and_meeting(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    fs.path(m.id, AUDIO).write_bytes(b"\x00")
    fs.delete_file(m.id, AUDIO)
    fs.delete_file(m.id, AUDIO)  # idempotent
    assert AUDIO not in fs.files(m.id)
    fs.delete_meeting(m.id)
    assert not fs.exists(m.id)


def test_tmp_files_are_hidden_from_listing(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    fs.path(m.id, "analysis.json.tmp").write_text("{")
    assert ANALYSIS not in fs.files(m.id) and "analysis.json.tmp" not in fs.files(m.id)


def test_plans_and_open_actions(fs: FsMeetingRepository):
    d1, d2, d3 = date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)
    a = Action("x", "me", "m1", id="abc", due=d2)
    fs.save_plan(DailyPlan(d1, "# day 1\n", new_actions=[a]))
    fs.save_plan(DailyPlan(d3, "# day 3\n"))

    assert fs.load_plan(d1).new_actions == [a]
    assert fs.load_plan(d2) is None
    assert fs.latest_plan_before(d3).day == d1
    assert fs.latest_plan_before(d1) is None
    assert (fs.plans / "2026-10-06.md").read_text() == "# day 1\n"

    assert fs.load_open_actions() == []
    fs.save_open_actions([a])
    assert fs.load_open_actions() == [a]


def test_corrupt_json_raises_repository_error(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    fs.path(m.id, META).write_text("{nope")
    with pytest.raises(RepositoryError):
        fs.load_meta(m.id)


def test_analysis_v2_roundtrip_and_old_format_compat(fs: FsMeetingRepository):
    from teams_recorder.domain import MeetingType, Priority
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    v2 = codec.analysis_from_dict(json.loads((FIXTURES / "sample_analysis_v2.json").read_text()))
    fs.save_analysis(m.id, v2)
    loaded = fs.load_analysis(m.id)
    assert loaded == v2 and loaded.meeting_type is MeetingType.PROJECT_REVIEW
    assert loaded.my_actions[0].priority is Priority.HIGH and loaded.decisions[0].at == "00:00:03"
    # analyses written before the new fields still load, with defaults
    old = codec.analysis_from_dict(json.loads((FIXTURES / "sample_analysis.json").read_text()))
    assert old.title == "" and old.meeting_type is MeetingType.OTHER and old.decisions[0].at is None


def test_save_minutes(fs: FsMeetingRepository):
    from teams_recorder.domain.status import MINUTES
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    fs.save_minutes(m.id, "# Ata\n")
    assert fs.path(m.id, MINUTES).read_text() == "# Ata\n"
    assert derive_status(fs.files(m.id)) == MeetingStatus.RECORDING  # minutes do not change status


def test_story_drafts_round_trip_next_to_the_plan(fs: FsMeetingRepository):
    day = date(2026, 10, 6)
    story = UserStory("Exportar horas", "Como gestor, quero exportar", acceptance_criteria=["Dado x"], details="**Contexto:** y",
                      open_questions=["Qual formato?"], source_action_ids=["a1"], source_meetings=["m1"],
                      priority=Priority.HIGH, due=date(2026, 10, 9), id="s1")
    drafts = StoryDrafts(day, [story], [SkippedAction("a2", "e-mail")])
    fs.save_plan(DailyPlan(day, "# day\n"))

    fs.save_story_drafts(drafts, "# Rascunhos\n")

    assert fs.load_story_drafts(day) == drafts
    assert fs.load_story_drafts(date(2026, 10, 7)) is None
    assert (fs.plans / "2026-10-06.stories.md").read_text() == "# Rascunhos\n"
    assert fs.latest_plan_before(date(2026, 10, 7)).day == day   # the drafts file is not taken for a plan


def test_story_drafts_keep_publications_and_duplicates(fs: FsMeetingRepository):
    day = date(2026, 10, 6)
    published = UserStory("Exportar horas", "Como gestor, quero exportar", source_action_ids=["a1"], id="s1",
                          publications=[Publication("backlog-md", "TASK-7", datetime(2026, 10, 6, 18, 5, 30))])
    drafts = StoryDrafts(day, [published], [SkippedAction("a2", "já coberta", duplicate_of="s0")])

    fs.save_story_drafts(drafts, "# Rascunhos\n")

    loaded = fs.load_story_drafts(day)
    assert loaded == drafts and loaded.has_publications
    assert loaded.stories[0].publication("backlog-md").ref == "TASK-7"


def test_story_drafts_written_before_publishing_still_load(fs: FsMeetingRepository):
    legacy = {
        "day": "2026-10-06",
        "stories": [{"id": "s1", "title": "Exportar horas", "narrative": "Como gestor", "acceptance_criteria": [],
                     "details": "", "open_questions": [], "source_action_ids": ["a1"], "source_meetings": ["m1"],
                     "priority": None, "due": None}],
        "skipped": [{"action_id": "a2", "reason": "e-mail"}],
    }
    (fs.plans / "2026-10-06.stories.json").write_text(json.dumps(legacy))

    loaded = fs.load_story_drafts(date(2026, 10, 6))

    assert loaded.stories[0].publications == [] and not loaded.has_publications
    assert loaded.skipped == [SkippedAction("a2", "e-mail")] and loaded.skipped[0].duplicate_of is None


def test_recent_story_drafts_window(fs: FsMeetingRepository):
    before = date(2026, 10, 10)
    for day in (date(2026, 10, 9), before, date(2026, 9, 9), date(2026, 10, 11), date(2026, 9, 10)):  # saved out of order
        fs.save_story_drafts(StoryDrafts(day, [UserStory(f"story {day}", "n")]), "# x\n")
    (fs.plans / "2026-13-45.stories.json").write_text("{}")   # matches the glob but is not a day: ignored
    fs.save_plan(DailyPlan(date(2026, 10, 8), "# plan\n"))

    recent = fs.recent_story_drafts(before, 30)

    assert [d.day for d in recent] == [date(2026, 9, 10), date(2026, 10, 9)]   # first day in, `before` and older out
    assert fs.recent_story_drafts(before, 0) == []
    assert fs.latest_plan_before(before).day == date(2026, 10, 8)            # drafts files are not plans


def test_story_drafts_with_the_wrong_shape_raise_repository_error(fs: FsMeetingRepository):
    (fs.plans / "2026-10-06.stories.json").write_text('{"stories": []}')   # valid JSON, no "day"
    with pytest.raises(RepositoryError, match="2026-10-06.stories.json"):
        fs.recent_story_drafts(date(2026, 10, 10), 30)
    with pytest.raises(RepositoryError):
        fs.load_story_drafts(date(2026, 10, 6))

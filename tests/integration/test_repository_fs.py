import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.constants import Files
from teams_recorder.domain import (
    Criterion,
    Action,
    ActionKind,
    ActionStatus,
    Analysis,
    CaptureStats,
    Meeting,
    MeetingNotFound,
    MeetingStatus,
    Priority,
    Publication,
    RepositoryError,
    Segment,
    SkippedAction,
    StoryDrafts,
    Transcript,
    TranscriptHealth,
    UserStory,
    derive_status,
)
from teams_recorder.domain.status import ANALYSIS, AUDIO, CURATION_ERROR, ERROR, LOCK, META, TAP_STATS, TRANSCRIPT_JSON, TRANSCRIPT_TXT

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


def test_curation_error_round_trips_without_the_meeting_lock_and_leaves_the_status_alone(fs: FsMeetingRepository):   # UT-109
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    fs.path(m.id, ANALYSIS).write_text("{}")
    status = derive_status(fs.files(m.id))
    assert CURATION_ERROR == "curation_error.txt" and fs.curation_error(m.id) is None
    with fs.lock(m.id):   # a step holding the meeting lock does not block the error file, and the file never takes the lock
        fs.mark_curation_failed(m.id, "the curator timed out")
        assert fs.curation_error(m.id) == "the curator timed out"
    assert fs.path(m.id, CURATION_ERROR).read_text() == "the curator timed out\n"
    assert LOCK not in fs.files(m.id) and CURATION_ERROR in fs.files(m.id)
    assert derive_status(fs.files(m.id)) == status
    fs.mark_curation_failed(m.id, "second attempt")
    assert fs.curation_error(m.id) == "second attempt"
    fs.clear_curation_failed(m.id)
    fs.clear_curation_failed(m.id)   # clearing twice is harmless
    assert fs.curation_error(m.id) is None and CURATION_ERROR not in fs.files(m.id)
    assert not [name for name in fs.files(m.id) if name.endswith(Files.TMP_SUFFIX)]
    assert derive_status(fs.files(m.id)) == status


def test_curation_error_of_an_unknown_meeting_is_meeting_not_found(fs: FsMeetingRepository):
    with pytest.raises(MeetingNotFound):
        fs.mark_curation_failed("nope", "x")
    with pytest.raises(MeetingNotFound):
        fs.curation_error("nope")


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
    story = UserStory("Exportar horas", "Como gestor, quero exportar", acceptance_criteria=[Criterion("Dado x")], details="**Contexto:** y",
                      open_questions=["Qual formato?"], source_action_ids=["a1"], source_meetings=["m1"],
                      priority=Priority.HIGH, due=date(2026, 10, 9), id="s1")
    drafts = StoryDrafts(day, [story], [SkippedAction("a2", "e-mail")])
    fs.save_story_drafts(drafts, "# Rascunhos\n")

    assert fs.load_story_drafts(day) == drafts
    assert fs.load_story_drafts(date(2026, 10, 7)) is None
    assert (fs.plans / "2026-10-06.stories.md").read_text() == "# Rascunhos\n"


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

    recent = fs.recent_story_drafts(before, 30)

    assert [d.day for d in recent] == [date(2026, 9, 10), date(2026, 10, 9)]   # first day in, `before` and older out
    assert fs.recent_story_drafts(before, 0) == []


def test_story_drafts_with_the_wrong_shape_raise_repository_error(fs: FsMeetingRepository):
    (fs.plans / "2026-10-06.stories.json").write_text('{"stories": []}')   # valid JSON, no "day"
    with pytest.raises(RepositoryError, match="2026-10-06.stories.json"):
        fs.recent_story_drafts(date(2026, 10, 10), 30)
    with pytest.raises(RepositoryError):
        fs.load_story_drafts(date(2026, 10, 6))


def test_action_kind_round_trip_and_actions_from_before_classification(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    classified = Action("Estimar horas", "usuário", m.id, id="k1", kind=ActionKind.TECHNICAL)
    fs.save_analysis(m.id, Analysis(meeting_id=m.id, summary="s", my_actions=[classified]))
    assert fs.load_analysis(m.id).my_actions == [classified]
    assert codec.action_from_dict({"id": "o1", "description": "x", "owner": "usuário", "source_meeting": "m"}).kind is None


def test_an_old_analysis_with_an_overdue_action_still_loads(fs: FsMeetingRepository):    # UT-056
    """`ActionStatus.OVERDUE` survives only to decode what the removed planner stored: read, never written by the code."""
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0)); fs.create(m)
    fs.save_analysis(m.id, Analysis(meeting_id=m.id, summary="s", my_actions=[Action("Enviar", "usuário", m.id, id="late")]))
    path = fs.path(m.id, ANALYSIS)
    data = json.loads(path.read_text())
    data["my_actions"][0]["status"] = "overdue"
    path.write_text(json.dumps(data))

    loaded = fs.load_analysis(m.id)

    assert loaded.my_actions[0].status == ActionStatus.OVERDUE and loaded.my_actions[0].id == "late"
    assert codec.action_from_dict({"id": "x", "description": "d", "owner": "o", "source_meeting": "m", "status": "overdue"}).status == "overdue"


def test_transcript_health_roundtrip_and_old_files_without_it(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 8, 10, 30, 52)); fs.create(m)
    health = TranscriptHealth(0.668, 28, 86, True, ((0, 14), (15, 59)), retried=True, rate_mismatch=True, short_padding_share=0.669)
    transcript = Transcript([Segment(0.0, 5.0, "A CIDADE NO BRASIL")], "pt", health)

    fs.save_transcript(m.id, transcript)

    assert fs.load_transcript(m.id) == transcript
    assert json.loads(fs.path(m.id, TRANSCRIPT_JSON).read_text())["health"]["uncovered"] == [[0, 14], [15, 59]]
    assert fs.path(m.id, TRANSCRIPT_TXT).read_text() == "[00:00:00] A CIDADE NO BRASIL\n"   # the text file is unchanged
    old = json.loads((FIXTURES / "sample_transcript.json").read_text())   # written before the health check
    assert "health" not in old and codec.transcript_from_dict(old).health is None


def test_a_transcript_of_the_wrong_shape_is_a_repository_error(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 8, 10, 30, 52)); fs.create(m)
    fs.save_transcript(m.id, Transcript([Segment(0.0, 5.0, "oi")], "pt", TranscriptHealth(0.5, 1, 2, True)))
    data = json.loads(fs.path(m.id, TRANSCRIPT_JSON).read_text())
    del data["health"]["covered_minutes"]   # truncated or edited by hand
    fs.path(m.id, TRANSCRIPT_JSON).write_text(json.dumps(data))

    with pytest.raises(RepositoryError, match="covered_minutes"):
        fs.load_transcript(m.id)


def _verified_analysis(meeting_id: str):
    from teams_recorder.domain import Analysis, Deadline, Decision, Verification, VerificationStatus
    yes = Verification(VerificationStatus.CONFIRMED, "dito em 00:01:10")
    no = Verification(VerificationStatus.UNCONFIRMED, "a transcrição não diz quem fará")
    return Analysis(
        meeting_id=meeting_id, summary="s",
        decisions=[Decision("Usar o Mapbox", "00:01:10", yes), Decision("Adiar o piloto")],
        my_actions=[Action("Enviar o cronograma", "me", meeting_id, verification=no)],
        others_actions=[Action("Revisar o mapa", "Ana", meeting_id)],
        deadlines=[Deadline("Cronograma", date(2026, 10, 15), "me", no), Deadline("Mapa", None, "Ana")],
        participants=["Felipe", "Ana", "Marcos"],
        participant_checks={"Ana": yes, "Marcos": Verification(VerificationStatus.UNCONFIRMED, "só mencionado")},
    )


def test_verification_roundtrips_through_the_analysis(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 12, 9, 0, 0)); fs.create(m)
    analysis = _verified_analysis(m.id)

    fs.save_analysis(m.id, analysis)

    assert fs.load_analysis(m.id) == analysis


def test_unverified_claims_are_written_exactly_as_before():
    # files, and the JSON the story writer and the curator receive, only change once a claim is verified
    old = json.loads((FIXTURES / "sample_analysis_v2.json").read_text())
    analysis = codec.analysis_from_dict(old)
    assert all(a.verification is None for a in analysis.all_actions) and analysis.participant_checks == {}
    written = codec.analysis_to_dict(analysis)
    assert "participant_checks" not in written
    assert not any("verification" in x for key in ("decisions", "my_actions", "others_actions", "deadlines") for x in written[key])
    assert codec.analysis_from_dict(written) == analysis


@pytest.mark.parametrize("damage", [
    lambda d: d["my_actions"][0]["verification"].update(status="maybe"),       # unknown status
    lambda d: d["deadlines"][0]["verification"].pop("status"),                # missing key
    lambda d: d["participant_checks"].update(Ana="confirmed"),                # a check that is not an object
    lambda d: d.update(participant_checks=["Ana"]),                           # the whole field as a list
    lambda d: d.update(participant_checks="Ana"),                             # ...or as text
    lambda d: d["decisions"][0]["verification"].update(reason=None),          # a reason that is not text
    lambda d: d["my_actions"][0]["verification"].update(reason=5),
    lambda d: d.update(participant_checks=[]),                                # falsy values that are not objects
    lambda d: d.update(participant_checks=False),
    lambda d: d["decisions"][0].update(verification=[]),
    lambda d: d["decisions"][0].update(verification=False),
    lambda d: d["decisions"][0].update(verification=""),
    lambda d: d["decisions"][0].update(verification="confirmed"),
], ids=["status", "missing-status", "check-type", "checks-list", "checks-text", "reason-null", "reason-number",
        "checks-empty-list", "checks-false", "verification-empty-list", "verification-false", "verification-empty-text",
        "verification-text"])
def test_a_damaged_verification_is_a_repository_error(fs: FsMeetingRepository, damage):
    m = Meeting.start(datetime(2026, 10, 12, 9, 0, 0)); fs.create(m)
    fs.save_analysis(m.id, _verified_analysis(m.id))
    path = fs.path(m.id, ANALYSIS)
    data = json.loads(path.read_text()); damage(data); path.write_text(json.dumps(data))

    with pytest.raises(RepositoryError, match="invalid JSON in"):
        fs.load_analysis(m.id)


@pytest.mark.parametrize("empty", [None, {}])
def test_a_null_or_empty_verification_means_not_verified(empty):
    analysis = codec.analysis_from_dict({"meeting_id": "m", "summary": "s", "participant_checks": empty,
                                         "decisions": [{"text": "Usar o Mapbox", "at": None, "verification": empty}]})
    assert analysis.decisions[0].verification is None and analysis.participant_checks == {}


def test_a_damaged_meta_is_a_repository_error(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 12, 9, 0, 0)); fs.create(m)
    fs.path(m.id, META).write_text('{"id": "%s"}' % m.id)   # no started_at
    with pytest.raises(RepositoryError, match="meta.json"):
        fs.list_meetings()


@pytest.mark.parametrize("handles", [
    '"process_handle": {"pid": 1, "out": "a"}, "mic_handle": {"pid": 2, "out": "b"}',
    '"process_handle": null, "mic_handle": {}',   # damaged handles: still an orphan, still cleared
    '"process_handle": {"pid": 1, "out": "a"}',     # a handle missing
], ids=["intact", "damaged-handles", "missing-handle"])
def test_an_orphan_recording_pointer_is_cleared_whatever_its_handles_hold(fs: FsMeetingRepository, handles: str):
    # the daemon's start-up recovery reads the pointer outside any handler: an orphan must never raise
    pointer = fs.data_dir / Files.ACTIVE_RECORDING
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text('{"meeting_id": "gone", %s}' % handles)
    assert fs.load_active() is None and not pointer.exists()


@pytest.mark.parametrize("content", [
    '{"meeting_id": "%s"}',                                                        # no handles
    '{"meeting_id": "%s", "process_handle": {"pid": "x", "out": "a"}, "mic_handle": {"pid": 2, "out": "b"}}',
    '{"process_handle": {"pid": 1, "out": "a"}}',                                 # no meeting id
], ids=["no-handles", "bad-pid", "no-meeting-id"])
def test_a_damaged_pointer_to_an_existing_meeting_is_a_repository_error(fs: FsMeetingRepository, content: str):
    m = Meeting.start(datetime(2026, 10, 12, 9, 0, 0)); fs.create(m)
    pointer = fs.data_dir / Files.ACTIVE_RECORDING
    pointer.write_text(content % m.id if "%s" in content else content)
    with pytest.raises(RepositoryError, match=Files.ACTIVE_RECORDING):
        fs.load_active()
    assert pointer.exists()   # a live recording's pointer is never deleted on a read error


def test_capture_stats_as_teams_tap_writes_them(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 14, 15, 38, 49)); fs.create(m)
    assert fs.load_capture_stats(m.id) is None                       # Windows, or recorded before 2026-10-14
    fs.path(m.id, TAP_STATS).write_text(json.dumps({
        "written_seconds": 709.9, "padded_seconds": 474.9, "short_padded_seconds": 474.9, "gaps": 0,
        "file_rate": 48000, "device_rates": [48000, 16000], "rate_changes": 1,
    }))
    assert fs.load_capture_stats(m.id) == CaptureStats(709.9, 474.9, 474.9, 0, (48000.0, 16000.0))
    assert derive_status(fs.files(m.id)) is MeetingStatus.RECORDING   # not a status file
    fs.path(m.id, TAP_STATS).write_text(json.dumps({"written_seconds": 60.0, "short_padded_seconds": 1.0}))
    assert fs.load_capture_stats(m.id) == CaptureStats(60.0, 0.0, 1.0, 0)   # the counters the check does not use are optional
    for bad, match in (({"written_seconds": 1.0}, "short_padded_seconds"), ([1, 2], "invalid JSON")):
        fs.path(m.id, TAP_STATS).write_text(json.dumps(bad))
        with pytest.raises(RepositoryError, match=match):
            fs.load_capture_stats(m.id)
    fs.path(m.id, TAP_STATS).write_text("{")
    with pytest.raises(RepositoryError, match="invalid JSON"):
        fs.load_capture_stats(m.id)


def test_capture_stats_that_cannot_be_read_are_a_repository_error(fs: FsMeetingRepository):
    m = Meeting.start(datetime(2026, 10, 14, 15, 38, 49)); fs.create(m)
    fs.path(m.id, TAP_STATS).mkdir()   # IsADirectoryError, an OSError that is not "missing"
    with pytest.raises(RepositoryError, match="cannot read"):
        fs.load_capture_stats(m.id)


def test_health_from_before_the_rate_check_loads_unflagged():
    old = {"loop_share": 0.0, "covered_minutes": 3, "total_minutes": 3, "degraded": False, "uncovered": []}
    health = codec.health_from_dict(old)
    assert not health.rate_mismatch and health.short_padding_share == 0.0


def test_it001_the_dx_events_and_energy_label_a_transcript_through_the_file_repository(fs: FsMeetingRepository):
    from teams_recorder.application.use_cases import TranscribeMeeting
    from teams_recorder.domain import EnergyTimeline
    from teams_recorder.domain.status import MIC_TRACK, TAP_TRACK
    from tests.fakes import FakeTranscriber
    from tests.unit.test_speakers_codec import DX_EXAMPLE, FELIPE, LUCAS

    m = Meeting.start(datetime(2026, 10, 17, 9, 30, 12), pid=4242); fs.create(m)
    fs.path(m.id, AUDIO).write_bytes(b"audio")
    fs.path(m.id, "speakers.jsonl").write_text("\n".join(json.dumps(r) for r in DX_EXAMPLE) + "\n")
    mic = [-70.0] * 2200
    mic[2000:2050] = [-30.0] * 50   # the user speaks 200.0-205.0 s, the Teams track silent then
    fs.save_energy(m.id, {TAP_TRACK: EnergyTimeline(0.1, tuple([-60.0] * 2200)), MIC_TRACK: EnergyTimeline(0.1, tuple(mic))})
    fake = FakeTranscriber(Transcript(segments=[
        Segment(192.0, 199.5, "então eu subo o ambiente de homologação até quarta"),   # inside Lucas's turn (191.1-199.6)
        Segment(200.0, 205.0, "pode deixar comigo o relatório"),                       # outside every turn, the microphone loud
        Segment(210.0, 215.0, "a gente combina o resto depois"),                       # neither
    ]))

    TranscribeMeeting(fs, fake, "pt", user_name="Felipe").execute(m.id)

    saved = json.loads(fs.path(m.id, TRANSCRIPT_JSON).read_text())
    assert [s.get("speaker") for s in saved["segments"]] == [LUCAS, "Felipe", None]
    assert saved["speakers"] == {"roster": [FELIPE, LUCAS], "user_label": "Felipe", "labelled": 2, "eligible": 3, "reason": None}
    assert fs.path(m.id, TRANSCRIPT_TXT).read_text().splitlines() == [
        f"[00:03:12] {LUCAS}: então eu subo o ambiente de homologação até quarta",
        "[00:03:20] Felipe: pode deixar comigo o relatório",
        "[00:03:30] a gente combina o resto depois",
    ]

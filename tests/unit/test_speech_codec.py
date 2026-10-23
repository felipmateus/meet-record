"""`speech` in transcript.json: docs/tasks/speech-check/_tests.md UT-020 to UT-023."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.domain import Meeting, RepositoryError, Segment, SpeechCheck, Transcript, TranscriptHealth
from teams_recorder.domain.status import TRANSCRIPT_JSON

NO_SPEECH = SpeechCheck(found=False, speech_seconds=0.0, audio_seconds=309.6, segments=0)
SPEECH = SpeechCheck(found=True, speech_seconds=2676.4, audio_seconds=3138.0, segments=612)


def _repo_with_meeting(tmp_path: Path) -> tuple[FsMeetingRepository, Meeting]:
    repo = FsMeetingRepository(tmp_path)
    meeting = Meeting.start(datetime(2026, 10, 23, 10, 0, 0))
    repo.create(meeting)
    return repo, meeting


@pytest.mark.parametrize("record", [NO_SPEECH, SPEECH])
def test_ut020_a_speech_record_round_trips_under_the_documented_keys(record: SpeechCheck):
    transcript = Transcript(segments=[Segment(0.0, 2.0, "Hello")], language="en", speech=record)
    data = codec.transcript_to_dict(transcript)
    assert data["speech"] == {"found": record.found, "speech_seconds": record.speech_seconds, "audio_seconds": record.audio_seconds,
                              "segments": record.segments}
    assert codec.transcript_from_dict(json.loads(json.dumps(data))) == transcript


def test_ut020_the_no_speech_example_of_the_spec_is_the_written_shape():
    data = codec.transcript_to_dict(Transcript(language="pt", speech=NO_SPEECH))
    assert data == {"language": "pt", "health": None, "segments": [],
                    "speech": {"found": False, "speech_seconds": 0.0, "audio_seconds": 309.6, "segments": 0}}


def test_ut021_a_transcript_without_a_record_is_written_without_the_key():
    assert "speech" not in codec.transcript_to_dict(Transcript(segments=[Segment(0.0, 2.0, "Olá")]))


def test_ut022_a_transcript_written_before_the_feature_loads_unchanged_and_keeps_its_health():
    health = {"loop_share": 0.104, "covered_minutes": 31, "total_minutes": 37, "degraded": True, "uncovered": [[3, 5]],
              "retried": True, "rate_mismatch": False, "short_padding_share": 0.0}
    old = {"language": "pt", "health": health, "segments": [{"start": 0.0, "end": 2.0, "text": "Olá"}]}
    loaded = codec.transcript_from_dict(old)
    assert loaded.speech is None
    assert loaded.health == TranscriptHealth(0.104, 31, 37, True, ((3, 5),), True, False, 0.0)   # stored health: the old rule's verdict, not recomputed
    assert codec.transcript_to_dict(loaded) == old


def test_ut022_a_transcript_written_before_the_feature_loads_through_the_file_repository(tmp_path: Path):
    repo, meeting = _repo_with_meeting(tmp_path)
    path = tmp_path / "recordings" / meeting.id / TRANSCRIPT_JSON
    path.write_text(json.dumps({"language": "pt", "health": None, "segments": [{"start": 0.0, "end": 2.0, "text": "Olá"}]}))
    assert repo.load_transcript(meeting.id).speech is None


def test_ut022_a_null_record_is_the_same_as_none():
    assert codec.transcript_from_dict({"language": "pt", "segments": [], "speech": None}).speech is None


def test_a_record_survives_the_file_repository(tmp_path: Path):
    repo, meeting = _repo_with_meeting(tmp_path)
    transcript = Transcript(segments=[Segment(0.0, 2.0, "Hello")], language="en", speech=SPEECH)
    repo.save_transcript(meeting.id, transcript)
    assert repo.load_transcript(meeting.id) == transcript


def test_a_no_speech_transcript_is_saved_with_no_segments_and_a_text_file_of_one_newline(tmp_path: Path):
    repo, meeting = _repo_with_meeting(tmp_path)
    repo.save_transcript(meeting.id, Transcript(language="pt", speech=NO_SPEECH))
    folder = tmp_path / "recordings" / meeting.id
    stored = json.loads((folder / TRANSCRIPT_JSON).read_text())
    assert stored["segments"] == [] and stored["health"] is None and stored["speech"]["found"] is False
    assert "language_detection" not in stored and "speakers" not in stored
    assert repo.load_transcript(meeting.id) == Transcript(language="pt", speech=NO_SPEECH)


GOOD = {"found": False, "speech_seconds": 1.5, "audio_seconds": 12.0, "segments": 2}


def _damaged(**changes: object) -> dict[str, object]:
    return {**GOOD, **changes}


@pytest.mark.parametrize("damaged", [
    "found",                                              # a string
    ["found", True],                                      # a list
    _damaged(found="false"),                              # a string for a bool: not coerced
    _damaged(found=0),                                    # a number for a bool
    _damaged(speech_seconds="1.5"),                       # a string for seconds: not coerced
    _damaged(segments=2.7),                               # a float for a count
    _damaged(segments=True),                              # a bool is not a count
    _damaged(audio_seconds=float("nan")),                 # NaN is written by json.dumps and read back by json.loads
    _damaged(audio_seconds=float("inf")),
    _damaged(speech_seconds=True),                        # a bool is not seconds
    _damaged(speech_seconds=None),
    {key: value for key, value in GOOD.items() if key != "found"},            # a missing field
    {key: value for key, value in GOOD.items() if key != "segments"},
    {key: value for key, value in GOOD.items() if key != "audio_seconds"},
    False,                                                # a falsy value that is not null is still a damaged record
    "",
])
def test_ut023_a_damaged_record_is_a_repository_error_naming_the_file(tmp_path: Path, damaged: object):
    repo, meeting = _repo_with_meeting(tmp_path)
    repo.save_transcript(meeting.id, Transcript(segments=[Segment(0.0, 2.0, "Hello")], language="en"))
    path = tmp_path / "recordings" / meeting.id / TRANSCRIPT_JSON
    data = json.loads(path.read_text())
    data["speech"] = damaged
    path.write_text(json.dumps(data))   # NaN and Infinity are written as the tokens json.loads accepts
    with pytest.raises(RepositoryError, match=TRANSCRIPT_JSON):
        repo.load_transcript(meeting.id)


def test_ut023_whole_numbers_are_numbers_and_nothing_else_is_rejected():
    loaded = codec.transcript_from_dict({"language": "pt", "segments": [], "speech": _damaged(speech_seconds=0, audio_seconds=12)})
    assert loaded.speech == SpeechCheck(found=False, speech_seconds=0.0, audio_seconds=12.0, segments=2)

"""`language_detection` in transcript.json: docs/tasks/language-detection/_tests.md UT-041 to UT-043."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.domain import LanguageDetection, LanguageReason, LanguageSample, Meeting, RepositoryError, Segment, Transcript
from teams_recorder.domain.status import TRANSCRIPT_JSON

SAMPLES = (
    LanguageSample(134.7, "en", 0.993), LanguageSample(404.1, "is", 0.965), LanguageSample(673.4, "is", 0.9), LanguageSample(942.8, "en", 0.997),
    LanguageSample(1212.2, "en", 0.987), LanguageSample(1481.6, "is", 0.946), LanguageSample(1750.9, "is", 0.979), LanguageSample(2020.3, None, 0.0),
)


def _repo_with_meeting(tmp_path: Path) -> tuple[FsMeetingRepository, Meeting]:
    repo = FsMeetingRepository(tmp_path)
    meeting = Meeting.start(datetime(2026, 10, 21, 10, 0, 0))
    repo.create(meeting)
    return repo, meeting


def test_ut041_a_detection_record_round_trips_with_its_unanswered_samples():
    transcript = Transcript(segments=[Segment(0.0, 2.0, "Hello")], language="en",
                            language_detection=LanguageDetection("en", LanguageReason.MAJORITY, 3, 3, SAMPLES))
    data = codec.transcript_to_dict(transcript)
    assert data["language_detection"]["samples"][-1] == {"at": 2020.3, "language": None, "p": 0.0}
    assert data["language_detection"]["reason"] == "majority"
    loaded = codec.transcript_from_dict(json.loads(json.dumps(data)))
    assert loaded == transcript and len(loaded.language_detection.samples) == 8   # type: ignore[union-attr]


def test_ut042_a_transcript_without_a_record_loads_unchanged_and_is_written_without_the_key():
    old = {"language": "pt", "health": None, "segments": [{"start": 0.0, "end": 2.0, "text": "Olá"}]}
    loaded = codec.transcript_from_dict(old)
    assert loaded.language_detection is None
    assert codec.transcript_to_dict(loaded) == old


@pytest.mark.parametrize("damaged", [
    "en",                                                                                          # not an object
    {"language": "en", "reason": "bogus", "counted": 1, "votes": 1, "samples": []},                  # unknown reason
    {"language": "en", "reason": "majority", "counted": 1, "votes": 1, "samples": ["en"]},           # a sample that is not an object
    {"language": "en", "reason": "majority", "counted": 1, "votes": 1, "samples": {"at": 1.0}},      # samples that are not a list
])
def test_ut043_a_damaged_record_is_a_repository_error_naming_the_file(tmp_path: Path, damaged: object):
    repo, meeting = _repo_with_meeting(tmp_path)
    repo.save_transcript(meeting.id, Transcript(segments=[Segment(0.0, 2.0, "Hello")], language="en"))
    path = tmp_path / "recordings" / meeting.id / TRANSCRIPT_JSON
    data = json.loads(path.read_text())
    data["language_detection"] = damaged
    path.write_text(json.dumps(data))
    with pytest.raises(RepositoryError, match=TRANSCRIPT_JSON):
        repo.load_transcript(meeting.id)


def test_a_record_survives_the_file_repository(tmp_path: Path):
    repo, meeting = _repo_with_meeting(tmp_path)
    transcript = Transcript(segments=[Segment(0.0, 2.0, "Hello")], language="en",
                            language_detection=LanguageDetection("en", LanguageReason.MAJORITY, 3, 3, SAMPLES))
    repo.save_transcript(meeting.id, transcript)
    assert repo.load_transcript(meeting.id) == transcript

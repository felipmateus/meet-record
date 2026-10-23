"""The FakeSpeechDetector the use-case tests (task 3) and the CLI scenarios (task 5) lean on."""
from pathlib import Path

import pytest

from teams_recorder.application.ports import SpeechDetector
from teams_recorder.domain import SpeechActivity, TranscriptionError
from tests.fakes import FakeSpeechDetector

A, B = Path("a/audio.m4a"), Path("b/audio.m4a")
SILENT, SPOKEN = SpeechActivity(309.6, ()), SpeechActivity(60.0, ((0.0, 4.19), (4.58, 7.2)))


def test_it_is_a_speech_detector():
    assert isinstance(FakeSpeechDetector(), SpeechDetector)


def test_one_scripted_activity_answers_every_audio_and_the_paths_are_recorded():
    fake = FakeSpeechDetector(SILENT)

    assert fake.activity(A) == SILENT and fake.activity(B) == SILENT
    assert fake.calls == [A, B]


def test_a_mapping_gives_each_audio_its_own_activity():
    fake = FakeSpeechDetector({A: SILENT, B: SPOKEN})

    assert fake.activity(B) == SPOKEN and fake.activity(A) == SILENT


def test_an_error_is_raised_after_the_call_is_recorded():
    fake = FakeSpeechDetector(error=TranscriptionError("whisper-vad-speech-segments failed"))

    with pytest.raises(TranscriptionError):
        fake.activity(A)

    assert fake.calls == [A]


def test_any_exception_can_be_scripted():
    with pytest.raises(RuntimeError):
        FakeSpeechDetector(error=RuntimeError("boom")).activity(A)


def test_the_default_is_speech_all_through_twenty_minutes():
    activity = FakeSpeechDetector().activity(A)

    assert activity.audio_seconds == 1200.0 and activity.speech_seconds == 1200.0

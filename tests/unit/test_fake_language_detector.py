"""The FakeLanguageDetector the use-case tests (task 3) and the CLI scenarios (task 5) lean on."""
from pathlib import Path

import pytest

from teams_recorder.application.ports import LanguageDetector
from teams_recorder.domain import LanguageSample, TranscriptionError
from tests.fakes import FakeLanguageDetector

A, B = Path("a/audio.m4a"), Path("b/audio.m4a")


def test_it_is_a_language_detector():
    assert isinstance(FakeLanguageDetector(), LanguageDetector)


def test_a_single_answer_repeats_on_every_offset_and_the_call_is_recorded():
    fake = FakeLanguageDetector(["en"])

    assert fake.detect(A, [0.0, 10.0, 20.0], 30.0) == [LanguageSample(at, "en", 0.99) for at in (0.0, 10.0, 20.0)]
    assert fake.calls == [(A, (0.0, 10.0, 20.0), 30.0)]


def test_answers_are_codes_pairs_or_none_in_offset_order():
    fake = FakeLanguageDetector(["en", ("is", 0.9), None])

    assert fake.detect(A, [1.0, 2.0, 3.0], 30.0) == [LanguageSample(1.0, "en", 0.99), LanguageSample(2.0, "is", 0.9), LanguageSample(3.0, None, 0.0)]


def test_a_mapping_gives_each_audio_its_own_answers():
    fake = FakeLanguageDetector({A: ["en"], B: ["pt"]})

    assert [s.language for s in fake.detect(A, [0.0], 30.0)] == ["en"]
    assert [s.language for s in fake.detect(B, [0.0], 30.0)] == ["pt"]


def test_an_error_is_raised_after_the_call_is_recorded():
    fake = FakeLanguageDetector(error=TranscriptionError("whisper-cli failed"))

    with pytest.raises(TranscriptionError):
        fake.detect(A, [0.0], 30.0)

    assert len(fake.calls) == 1

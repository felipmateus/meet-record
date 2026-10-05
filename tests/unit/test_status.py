import pytest

from teams_recorder.domain import MeetingStatus, derive_status, next_step
from teams_recorder.domain.status import ANALYSIS, AUDIO, ERROR, META, MIC_TRACK, TAP_TRACK, TRANSCRIPT_JSON


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({META}, MeetingStatus.RECORDING),
        ({META, TAP_TRACK, MIC_TRACK}, MeetingStatus.RECORDING),
        ({META, AUDIO}, MeetingStatus.RECORDED),
        ({META, AUDIO, TRANSCRIPT_JSON}, MeetingStatus.TRANSCRIBED),
        ({META, AUDIO, TRANSCRIPT_JSON, ANALYSIS}, MeetingStatus.ANALYZED),
        ({META, TRANSCRIPT_JSON, ANALYSIS}, MeetingStatus.ANALYZED),  # audio purged
        ({META, TRANSCRIPT_JSON}, MeetingStatus.TRANSCRIBED),  # audio purged before analysis
        ({META, AUDIO, ERROR}, MeetingStatus.FAILED),
        ({META, AUDIO, TRANSCRIPT_JSON, ANALYSIS, ERROR}, MeetingStatus.FAILED),
    ],
)
def test_derive_status(files, expected):
    assert derive_status(files) == expected


def test_next_step():
    assert next_step(MeetingStatus.RECORDING) == "stop"
    assert next_step(MeetingStatus.RECORDED) == "transcribe"
    assert next_step(MeetingStatus.TRANSCRIBED) == "analyze"
    assert next_step(MeetingStatus.ANALYZED) is None
    assert next_step(MeetingStatus.FAILED) is None

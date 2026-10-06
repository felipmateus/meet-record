"""Keep-recording dialog: script and answer parsing, without showing anything."""
import subprocess
from types import SimpleNamespace

import pytest

from teams_recorder.adapters.outbound.confirm_macos import DialogRecordingConfirmation, parse_answer
from teams_recorder.application.ports import ConfirmAnswer
from teams_recorder.domain import Meeting
from teams_recorder.messages import Ask


@pytest.mark.parametrize("output, expected", [
    (f"button returned:{Ask.KEEP}, gave up:false\n", ConfirmAnswer.KEEP),
    (f"button returned:{Ask.DISCARD}, gave up:false\n", ConfirmAnswer.DISCARD),
    ("button returned:, gave up:true\n", ConfirmAnswer.NO_ANSWER),
    ("", ConfirmAnswer.NO_ANSWER),
    ("button returned:Something else, gave up:false", ConfirmAnswer.NO_ANSWER),
])
def test_parse_answer(output, expected):
    assert parse_answer(output) == expected


def _meeting(clock):
    return Meeting.start(clock.now(), pid=1)


def test_ask_runs_osascript_with_the_dialog(clock):
    calls = []

    def runner(cmd, **kw):
        calls.append((cmd, kw))
        return SimpleNamespace(stdout=f"button returned:{Ask.DISCARD}, gave up:false\n")

    confirm = DialogRecordingConfirmation(timeout_seconds=12, runner=runner)
    assert confirm.ask(_meeting(clock)) is ConfirmAnswer.DISCARD
    cmd, kw = calls[0]
    assert cmd[:2] == ["osascript", "-e"]
    script = cmd[2]
    assert "display dialog" in script and "giving up after 12" in script
    assert f'default button "{Ask.KEEP}"' in script and f'"{Ask.DISCARD}"' in script
    assert kw["timeout"] > 12


@pytest.mark.parametrize("error", [OSError("no osascript"), subprocess.TimeoutExpired("osascript", 1)])
def test_ask_failures_mean_no_answer(clock, error):
    def runner(*a, **kw):
        raise error

    assert DialogRecordingConfirmation(runner=runner).ask(_meeting(clock)) is ConfirmAnswer.NO_ANSWER

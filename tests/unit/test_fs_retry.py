import errno

import pytest

from teams_recorder.adapters.outbound.fs_retry import retry_io


def test_retries_transient_errors_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError(errno.EDEADLK, "Resource deadlock avoided")
        return "ok"

    assert retry_io(flaky, "x", sleep=lambda s: None) == "ok" and calls["n"] == 3


def test_gives_up_after_attempts():
    def always():
        raise OSError(errno.EDEADLK, "Resource deadlock avoided")

    with pytest.raises(OSError):
        retry_io(always, "x", attempts=3, sleep=lambda s: None)


def test_permanent_errors_are_not_retried():
    calls = {"n": 0}

    def missing():
        calls["n"] += 1
        raise FileNotFoundError(errno.ENOENT, "nope")

    with pytest.raises(FileNotFoundError):
        retry_io(missing, "x", sleep=lambda s: None)
    assert calls["n"] == 1

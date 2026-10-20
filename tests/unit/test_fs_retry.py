import errno
import os
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import fs_retry
from teams_recorder.adapters.outbound.fs_retry import atomic_write, retry_io


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


def test_atomic_write_creates_folders_replaces_and_keeps_newlines(tmp_path: Path):
    target = tmp_path / "a" / "b" / "doc.md"
    atomic_write(target, "one\r\ntwo\n")
    assert target.read_bytes() == b"one\r\ntwo\n"
    atomic_write(target, "çã\n")
    assert target.read_bytes() == "çã\n".encode()
    assert [p.name for p in target.parent.iterdir()] == ["doc.md"]


def test_atomic_write_that_fails_leaves_the_file_and_no_temporary_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "doc.md"
    target.write_text("old")

    def broken(src, dst):
        raise OSError(errno.EIO, "disk")

    monkeypatch.setattr(fs_retry.os, "replace", broken)
    with pytest.raises(OSError):
        atomic_write(target, "new")
    assert target.read_text() == "old" and [p.name for p in tmp_path.iterdir()] == ["doc.md"]
    assert os.replace is broken   # the patch is on the shared module: undone by monkeypatch after the test

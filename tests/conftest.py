from __future__ import annotations

import os
from datetime import datetime

import pytest

# pytest-cov injects coverage measurement into every Python subprocess through the
# COV_CORE_* variables. The children spawned by these tests are scripted recorders, not
# package code, and on this machine importing coverage in the child takes tens of seconds.
for _var in list(os.environ):
    if _var.startswith("COV_CORE_"):
        os.environ.pop(_var, None)

from teams_recorder.domain import Meeting
from tests.fakes import FakeClock, FakeNotifier, InMemoryMeetingRepository


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 10, 6, 14, 0, 0))


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def repo() -> InMemoryMeetingRepository:
    return InMemoryMeetingRepository()


@pytest.fixture
def meeting(clock: FakeClock) -> Meeting:
    return Meeting.start(clock.now(), pid=4242, title="Planejamento Sprint")

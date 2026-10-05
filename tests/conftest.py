from __future__ import annotations

from datetime import datetime

import pytest

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

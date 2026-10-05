from __future__ import annotations

import os
from datetime import datetime

import pytest

# O pytest-cov injeta medição de cobertura em todo subprocesso Python via variáveis
# COV_CORE_*. Os filhos destes testes são gravadores simulados, não código do pacote,
# e neste ambiente a importação do coverage no filho leva dezenas de segundos.
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

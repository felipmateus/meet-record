"""Planning and maintenance use cases."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from teams_recorder.application.ports import Clock, MeetingRepository, Notifier, Planner
from teams_recorder.domain import DailyPlan, MeetingStatus, derive_status, merge_open_actions
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON


@dataclass
class BuildDailyPlan:
    repo: MeetingRepository
    planner: Planner
    notifier: Notifier

    def execute(self, day: date) -> DailyPlan:
        analyses = [
            self.repo.load_analysis(m.id)
            for m in self.repo.list_meetings()
            if m.day == day and derive_status(self.repo.files(m.id)) == MeetingStatus.ANALYZED
        ]
        previous = self.repo.latest_plan_before(day)
        open_actions = self.repo.load_open_actions()
        plan = self.planner.plan(day, analyses, previous, open_actions)
        plan.day = day
        self.repo.save_plan(plan)
        self.repo.save_open_actions(merge_open_actions(open_actions, plan))
        self.notifier.notify("Daily plan ready", f"{len(analyses)} meeting(s), {len(plan.new_actions)} new action(s)")
        return plan


@dataclass
class PurgeOldAudio:
    repo: MeetingRepository
    clock: Clock
    retention_days: int = 30

    def execute(self) -> list[str]:
        cutoff = self.clock.now() - timedelta(days=self.retention_days)
        purged: list[str] = []
        for meeting in self.repo.list_meetings():
            files = self.repo.files(meeting.id)
            if AUDIO in files and TRANSCRIPT_JSON in files and meeting.started_at < cutoff:
                self.repo.delete_file(meeting.id, AUDIO)
                purged.append(meeting.id)
        return purged

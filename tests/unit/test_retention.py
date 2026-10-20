"""`PurgeOldAudio` (audio retention): what it deletes, its default age and where it lives."""
from dataclasses import fields
from datetime import timedelta

from teams_recorder.application.use_cases import PurgeOldAudio
from teams_recorder.application.use_cases import retention
from teams_recorder.constants import Audio
from teams_recorder.domain import Meeting
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON


def test_purge_old_audio_respects_retention_and_transcript(repo, clock):
    now = clock.now()
    old_done = Meeting.start(now - timedelta(days=31)); repo.seed(old_done, {AUDIO, TRANSCRIPT_JSON})
    old_untranscribed = Meeting.start(now - timedelta(days=40)); repo.seed(old_untranscribed, {AUDIO})
    recent = Meeting.start(now - timedelta(days=5)); repo.seed(recent, {AUDIO, TRANSCRIPT_JSON})
    purged_already = Meeting.start(now - timedelta(days=60)); repo.seed(purged_already, {TRANSCRIPT_JSON})

    purged = PurgeOldAudio(repo, clock, retention_days=30).execute()

    assert purged == [old_done.id]
    assert AUDIO not in repo.files(old_done.id)
    assert AUDIO in repo.files(old_untranscribed.id)
    assert AUDIO in repo.files(recent.id)


def test_purge_old_audio_lives_in_retention_and_defaults_to_the_audio_constant(repo, clock):    # UT-097
    assert PurgeOldAudio is retention.PurgeOldAudio and PurgeOldAudio.__module__ == "teams_recorder.application.use_cases.retention"
    assert {f.name: f.default for f in fields(PurgeOldAudio)}["retention_days"] == Audio.RETENTION_DAYS == 30
    old = Meeting.start(clock.now() - timedelta(days=31)); repo.seed(old, {AUDIO, TRANSCRIPT_JSON})
    young = Meeting.start(clock.now() - timedelta(days=29)); repo.seed(young, {AUDIO, TRANSCRIPT_JSON})

    assert PurgeOldAudio(repo, clock).execute() == [old.id]

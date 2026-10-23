"""Speech check rules (docs/tasks/speech-check/_spec.md): whether a recording has speech at all, and how much of it falls
inside a window. Pure: no I/O, no process, no model. The adapter that runs Silero VAD and returns the segments is
`adapters/outbound/speech_whispercpp.py`."""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

_PRECISION = 6   # decimals kept in a sum of seconds: the tool reports centiseconds, and float noise must not move a verdict across a threshold


@dataclass(frozen=True)
class SpeechRules:
    """Thresholds of the speech check; fixed constants (changing one is a code change, measured in the spec's Evidence)."""

    min_speech_seconds: float = 2.0          # under this much speech in the whole audio: no speech
    min_sample_speech_seconds: float = 3.0   # a language sample needs this much speech inside its window
    notify_min_audio_seconds: float = 60.0   # a no-speech recording at least this long notifies


@dataclass(frozen=True)
class SpeechActivity:
    """What VAD found: the audio's length and its speech segments, (start, end) in seconds, sorted and non-overlapping."""

    audio_seconds: float
    segments: tuple[tuple[float, float], ...] = ()

    @property
    def speech_seconds(self) -> float:
        return round(math.fsum(end - start for start, end in self.segments), _PRECISION)

    def speech_between(self, start: float, end: float) -> float:
        """Seconds of speech inside [start, end): a segment that straddles an edge counts only its overlap."""
        return round(math.fsum(max(0.0, min(seg_end, end) - max(seg_start, start)) for seg_start, seg_end in self.segments), _PRECISION)


@dataclass(frozen=True)
class SpeechCheck:
    """The record saved with the transcript (transcript.json `speech`)."""

    found: bool
    speech_seconds: float    # rounded to 0.1
    audio_seconds: float     # rounded to 0.1
    segments: int


def check_speech(activity: SpeechActivity, rules: SpeechRules = SpeechRules()) -> SpeechCheck:
    """The verdict on a whole recording: `found` when the speech reaches `rules.min_speech_seconds`, judged on the measured
    value before it is rounded to 0.1 for the record (1.99 s is no speech, whatever it prints as)."""
    speech = activity.speech_seconds
    return SpeechCheck(
        found=speech >= rules.min_speech_seconds,
        speech_seconds=round(speech, 1),
        audio_seconds=round(activity.audio_seconds, 1),
        segments=len(activity.segments),
    )


def samples_with_speech(offsets: Sequence[float], activity: SpeechActivity, window_seconds: float,
                        rules: SpeechRules = SpeechRules()) -> list[float]:
    """The offsets whose window [offset, offset + window_seconds) holds at least `rules.min_sample_speech_seconds` of speech,
    in the order given."""
    return [at for at in offsets if activity.speech_between(at, at + window_seconds) >= rules.min_sample_speech_seconds]

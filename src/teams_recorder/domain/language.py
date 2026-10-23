"""Language detection rules (docs/tasks/language-detection/_spec.md): where the audio samples sit and how their answers
become one language for the meeting. Pure: no I/O, no process, no model. The adapter that asks whisper for the answers is
`adapters/outbound/language_whispercpp.py`."""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class LanguageRules:
    """Thresholds of the language detection; fixed constants in this delivery (changing one is a code change)."""

    window_seconds: float = 30.0     # one sample = whisper's identification window
    every_seconds: float = 300.0     # one sample per 5 minutes of meeting
    min_samples: int = 3
    max_samples: int = 12
    min_probability: float = 0.5     # a sample under this does not count
    min_votes: int = 2               # the winner needs this many counted samples (1 when only one sample was planned)


@dataclass(frozen=True)
class LanguageSample:
    at: float                        # start of the sample, seconds into the audio
    language: str | None             # whisper's answer; None: no answer for this sample
    probability: float = 0.0


class LanguageReason(StrEnum):
    MAJORITY = "majority"                    # more than half of the counted samples, and at least min_votes
    NO_USABLE_SAMPLE = "no-usable-sample"    # no sample heard an allowed language confidently
    TOO_FEW_VOTES = "too-few-votes"          # one sample counted, in a meeting with more than one sample planned
    NO_MAJORITY = "no-majority"
    DETECTION_FAILED = "detection-failed"    # the detector raised (it could not run, or whisper printed no answer); the samples are empty


@dataclass(frozen=True)
class LanguageDetection:
    language: str                            # the language the transcript was made in
    reason: LanguageReason
    counted: int = 0                         # samples that heard an allowed language with p >= min_probability
    votes: int = 0                           # counted samples that heard `language` (0 whenever the reason is not MAJORITY)
    samples: tuple[LanguageSample, ...] = ()

    @property
    def detected(self) -> bool:
        return self.reason is LanguageReason.MAJORITY


def sample_offsets(duration: float | None, rules: LanguageRules = LanguageRules()) -> list[float]:
    """Start of each sample, seconds into the audio, rounded to 0.1 s.

    One sample per `every_seconds` of meeting, rounded up, between `min_samples` and `max_samples`, and never more than the
    whole windows the meeting holds (at least 1). Sample i of n starts at (duration - window) * (i + 1/2) / n, so none sits at
    the very first or very last second. A meeting no longer than one window, or of unknown length, gets one sample at 0.
    """
    if duration is None or duration <= rules.window_seconds:
        return [0.0]
    wanted = min(max(math.ceil(duration / rules.every_seconds), rules.min_samples), rules.max_samples)
    count = max(1, min(wanted, int(duration // rules.window_seconds)))
    span = duration - rules.window_seconds
    return [round(span * (i + 0.5) / count, 1) for i in range(count)]


def _counts(samples: Sequence[LanguageSample], allowed: Sequence[str], rules: LanguageRules) -> dict[str, int]:
    """Counted samples per allowed language, in `allowed` order: a sample counts when it heard an allowed language with
    a probability of at least `min_probability`."""
    tally = dict.fromkeys(allowed, 0)
    for sample in samples:
        if sample.language in tally and sample.probability >= rules.min_probability:
            tally[sample.language] += 1
    return tally


def choose_language(samples: Sequence[LanguageSample], allowed: Sequence[str], fallback: str,
                    rules: LanguageRules = LanguageRules(), planned: int | None = None) -> LanguageDetection:
    """The meeting's language from its samples: the allowed language that more than half of the counted samples heard, and
    at least `min_votes` of them (1 when a single sample was planned). Otherwise `fallback`, with the reason why.

    `planned` is how many samples the meeting was planned with, which can exceed `len(samples)` when some were not sent (the
    speech check drops the ones without speech): a lone sample decides only in a meeting planned with one, so one survivor of
    several cannot decide a long meeting alone. None means every planned sample is in `samples`."""
    kept = tuple(samples)
    tally = _counts(kept, allowed, rules)
    counted = sum(tally.values())
    if counted == 0:
        return LanguageDetection(fallback, LanguageReason.NO_USABLE_SAMPLE, 0, 0, kept)
    winner, votes = max(tally.items(), key=lambda item: item[1])   # ties go to the first allowed language; none can pass the majority below
    needed = 1 if (len(kept) if planned is None else planned) == 1 else rules.min_votes
    if votes * 2 > counted and votes >= needed:
        return LanguageDetection(winner, LanguageReason.MAJORITY, counted, votes, kept)
    reason = LanguageReason.TOO_FEW_VOTES if counted == 1 else LanguageReason.NO_MAJORITY
    return LanguageDetection(fallback, reason, counted, 0, kept)


def counted_tally(detection: LanguageDetection, allowed: Sequence[str], rules: LanguageRules = LanguageRules()) -> dict[str, int]:
    """Counted samples per allowed language, in `allowed` order (for the `no majority` and `too few votes` CLI lines)."""
    return _counts(detection.samples, allowed, rules)

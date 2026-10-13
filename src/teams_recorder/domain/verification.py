"""Claim verification: which claims an analysis makes, the two checks done in code, and how verifications
are combined and written back. Pure functions; the patterns and labels come from the caller."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from typing import Iterable

from .models import Action, Analysis, ClaimKind, ClaimRef, Transcript, Verification, VerificationStatus


def claim_refs(analysis: Analysis) -> list[ClaimRef]:
    """Every verifiable claim of an analysis, in reading order."""
    return [
        *(ClaimRef(ClaimKind.DECISION, str(i)) for i in range(len(analysis.decisions))),
        *(ClaimRef(ClaimKind.ACTION, a.id) for a in analysis.all_actions),
        *(ClaimRef(ClaimKind.DEADLINE, str(i)) for i in range(len(analysis.deadlines))),
        *(ClaimRef(ClaimKind.PARTICIPANT, name) for name in analysis.participants),
    ]


def combine(first: Verification | None, second: Verification | None) -> Verification | None:
    """Two verdicts on one claim: unconfirmed if either is, with both reasons; None only if neither checked it."""
    if first is None or second is None:
        return first or second
    if first.status is second.status:
        reason = "; ".join(r for r in dict.fromkeys((first.reason, second.reason)) if r)
        return Verification(first.status, reason)
    return first if first.status is VerificationStatus.UNCONFIRMED else second


def with_verifications(analysis: Analysis, verdicts: dict[ClaimRef, Verification]) -> Analysis:
    """A copy of the analysis with each claim's verification set from `verdicts`; claims not in it keep theirs.
    The analysis passed in is not changed (actions are copied, not edited)."""
    def get(kind: ClaimKind, key: str, current: Verification | None) -> Verification | None:
        return verdicts.get(ClaimRef(kind, key), current)

    def actions(items: list[Action]) -> list[Action]:
        return [replace(a, verification=get(ClaimKind.ACTION, a.id, a.verification)) for a in items]

    checks = dict(analysis.participant_checks)
    for name in analysis.participants:
        found = verdicts.get(ClaimRef(ClaimKind.PARTICIPANT, name))
        if found is not None:
            checks[name] = found
    return replace(
        analysis,
        decisions=[replace(d, verification=get(ClaimKind.DECISION, str(i), d.verification)) for i, d in enumerate(analysis.decisions)],
        my_actions=actions(analysis.my_actions),
        others_actions=actions(analysis.others_actions),
        deadlines=[replace(d, verification=get(ClaimKind.DEADLINE, str(i), d.verification)) for i, d in enumerate(analysis.deadlines)],
        participant_checks=checks,
    )


def normalized(text: str) -> str:
    """Lower case without accents, so "Saúde" and "saude" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def sensitive_data(text: str, patterns: Iterable[str]) -> bool:
    """Whether a claim carries sensitive personal data (health, religion, politics...), by regular expressions
    matched against the normalized text."""
    plain = normalized(text)
    return any(re.search(p, plain) for p in patterns)


def participant_heard(name: str, transcript: Transcript, user_name: str, particles: Iterable[str], address: Iterable[str]) -> bool:
    """Whether a participant is a person in the meeting, not someone only mentioned: the recording's owner, a name
    said at least twice, or a name someone addresses (`address` templates with `{name}`, e.g. a greeting)."""
    if user_name and normalized(name.strip()) == normalized(user_name.strip()):
        return True
    skip = set(particles)
    names = [t for t in re.split(r"[\s()]+", normalized(name)) if len(t) >= 2 and t not in skip]
    if not names:
        return False
    text = normalized(transcript.text)
    plain = " " + " ".join(re.findall(r"\w+", text)) + " "
    if max(plain.count(f" {n} ") for n in names) >= 2:
        return True
    return any(re.search(template.format(name=re.escape(n)), text) for n in names for template in address)

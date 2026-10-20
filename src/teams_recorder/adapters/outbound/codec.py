"""Conversion between domain entities and JSON dictionaries.

Kept in the adapter so the domain knows nothing about the persistence format.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any, Iterable

import re

from teams_recorder.constants import Audio, Parse, Speakers
from teams_recorder.domain import (
    Action,
    ActionKind,
    ActionStatus,
    Analysis,
    CaptureStats,
    Criterion,
    Deadline,
    Decision,
    EnergyTimeline,
    LabelSummary,
    Meeting,
    MeetingType,
    PassKind,
    PassRecord,
    Priority,
    Publication,
    Segment,
    SkippedAction,
    SpeakerEvent,
    SpeakerLog,
    SILENCE_DB,
    StatusChange,
    StatusUpdate,
    StoryDrafts,
    Topic,
    Transcript,
    TranscriptHealth,
    SUGGESTION,
    UserStory,
    Verification,
    VerificationStatus,
    turns_from_events,
    window_subject,
)
from teams_recorder.messages import Err


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _parse_d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


# Meeting
def meeting_to_dict(m: Meeting) -> dict[str, Any]:
    return {"id": m.id, "started_at": _dt(m.started_at), "ended_at": _dt(m.ended_at), "pid": m.pid, "title": m.title}


def meeting_from_dict(d: dict[str, Any]) -> Meeting:
    return Meeting(
        id=d["id"],
        started_at=datetime.fromisoformat(d["started_at"]),
        ended_at=_parse_dt(d.get("ended_at")),
        pid=d.get("pid"),
        title=d.get("title"),
    )


# Transcript
def health_to_dict(h: TranscriptHealth) -> dict[str, Any]:
    return {
        "loop_share": h.loop_share,
        "covered_minutes": h.covered_minutes,
        "total_minutes": h.total_minutes,
        "degraded": h.degraded,
        "uncovered": [list(span) for span in h.uncovered],
        "retried": h.retried,
        "rate_mismatch": h.rate_mismatch,
        "short_padding_share": h.short_padding_share,
    }


def health_from_dict(d: dict[str, Any]) -> TranscriptHealth:
    return TranscriptHealth(
        loop_share=float(d["loop_share"]),
        covered_minutes=int(d["covered_minutes"]),
        total_minutes=int(d["total_minutes"]),
        degraded=bool(d["degraded"]),
        uncovered=tuple((int(start), int(end)) for start, end in d.get("uncovered", [])),
        retried=bool(d.get("retried", False)),
        rate_mismatch=bool(d.get("rate_mismatch", False)),
        short_padding_share=float(d.get("short_padding_share", 0.0)),
    )


def capture_stats_from_dict(d: dict[str, Any]) -> CaptureStats:
    """tap.stats.json, as teams-tap writes it (`--stats`)."""
    return CaptureStats(
        written_seconds=float(d["written_seconds"]),
        padded_seconds=float(d.get("padded_seconds", 0.0)),   # informative: the rate check reads only the two above and below
        short_padded_seconds=float(d["short_padded_seconds"]),
        gaps=int(d.get("gaps", 0)),
        device_rates=tuple(float(r) for r in d.get("device_rates", [])),
    )


def _segment_to_dict(s: Segment) -> dict[str, Any]:
    out: dict[str, Any] = {"start": s.start, "end": s.end, "text": s.text}
    return {**out, "speaker": s.speaker} if s.speaker else out   # unlabelled segments are written as before labels existed


def _speakers_to_dict(t: Transcript, labels: LabelSummary) -> dict[str, Any]:
    return {"roster": list(t.roster), "user_label": t.user_label, "labelled": labels.labelled, "eligible": labels.eligible,
            "reason": labels.reason}


def transcript_to_dict(t: Transcript) -> dict[str, Any]:
    out = {"language": t.language, "health": health_to_dict(t.health) if t.health else None, "segments": [_segment_to_dict(s) for s in t.segments]}
    return {**out, "speakers": _speakers_to_dict(t, t.labels)} if t.labels is not None else out


def transcript_from_dict(d: dict[str, Any]) -> Transcript:
    # transcripts written before 2026-10-11 have no health; before speaker attribution, no speaker and no speakers summary
    speakers = d.get("speakers")
    if speakers is not None and not isinstance(speakers, dict):
        raise TypeError(Err.BAD_SPEAKERS.format(value=speakers))
    return Transcript(
        language=d.get("language", Audio.DEFAULT_LANGUAGE),
        segments=[Segment(float(s["start"]), float(s["end"]), s["text"], _optional_text(s.get("speaker"))) for s in d.get("segments", [])],
        health=health_from_dict(d["health"]) if d.get("health") else None,
        roster=tuple(str(n) for n in speakers.get("roster", [])) if speakers else (),
        user_label=_optional_text(speakers.get("user_label")) if speakers else None,
        labels=LabelSummary(int(speakers["labelled"]), int(speakers["eligible"]), _optional_text(speakers.get("reason"))) if speakers else None,
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(Err.BAD_TEXT.format(value=value))
    return value or None


# Speaker observer events (speakers.jsonl, written by teams-speakers; see docs/tasks/speaker-attribution/_dx.md)
def speakers_unavailable_line(reason: str, at: float) -> str:
    """The single line the recorder writes when the observer could not start."""
    return json.dumps({"t": at, "event": "unavailable", "reason": reason}) + "\n"


def _finite(value: Any) -> float | None:
    """`value` as a finite float; None for anything else (text, NaN, infinity, an integer too large for a float)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _event(line: str) -> dict[str, Any] | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict) or not isinstance(record.get("event"), str) or _finite(record.get("t")) is None:
        return None
    return record


def speaker_log_from_lines(lines: Iterable[str], fallback_epoch: float, end: float) -> SpeakerLog:
    """The observer's record of a meeting. Times become seconds since the epoch the helper echoes in its start event,
    or since `fallback_epoch` (the meeting's start) when that event is missing. An unavailable line wins over anything
    else; lines that are not events are skipped and counted.

    A turn left open closes at the time of the last event of the file (a stop, a heartbeat or any other), not at `end`,
    the meeting's length: the helper writes nothing after it dies or while its window is frozen, so what it did not
    report is not credited to the last speaker it saw. `end` stays in the signature as the repository port's contract.
    """
    records: list[dict[str, Any]] = []
    skipped = 0
    for line in lines:
        if not line.strip():
            continue
        record = _event(line)
        if record is None:
            skipped += 1
        else:
            records.append(record)
    unavailable = next((r for r in records if r["event"] == "unavailable"), None)
    if unavailable is not None:
        return SpeakerLog(unavailable=str(unavailable.get("reason") or ""), skipped=skipped)
    start = next((r for r in records if r["event"] == "start"), None)
    start_epoch = _finite(start.get("epoch")) if start is not None else None
    epoch = start_epoch if start_epoch is not None else fallback_epoch
    events: list[SpeakerEvent] = []
    roster: list[str] = []
    me: str | None = None
    subject: str | None = None
    ended = False
    last = 0.0
    for r in records:
        kind, at, window = r["event"], float(r["t"]) - epoch, str(r.get("window") or r.get("kind") or "")
        last = max(last, at)
        name = r.get("name")
        if kind == "speaking" and isinstance(name, str) and name:
            events.append(SpeakerEvent(at, name, bool(r.get("speaking")), window))
        elif kind == "seen" and isinstance(name, str) and name:
            roster.append(name)
            if r.get("me") and me is None:
                me = name
        elif kind == "window":
            if r.get("state") in (Speakers.WINDOW_LOST, Speakers.WINDOW_FROZEN):   # a frozen tree reports nothing true: close like a lost window
                events.append(SpeakerEvent(at, "", False, window))
            elif subject is None and isinstance(r.get("title"), str):
                subject = window_subject(r["title"], compact=window == "compact")
        elif kind == "title" and subject is None and isinstance(r.get("subject"), str) and r["subject"].strip():
            subject = r["subject"].strip()
        elif kind == "stop":
            ended = True
        elif kind not in ("start", "speaking", "seen", "title", Speakers.HEARTBEAT_EVENT):
            skipped += 1
    return SpeakerLog(turns_from_events(events, last), tuple(dict.fromkeys(roster)), me, subject, ended, skipped=skipped)


# Track levels (energy.json)
def energy_to_dict(energy: dict[str, EnergyTimeline]) -> dict[str, Any]:
    step = next(iter(energy.values())).step if energy else 0.1
    return {"step_seconds": step, "tracks": {name: list(t.levels) for name, t in energy.items()}}


def _level(value: Any, track: str) -> float:
    """One dBFS level, with -inf and anything below the silence floor read as the floor; a value that is not a number, is NaN,
    or sits above `Speakers.MAX_LEVEL_DB` (a power of ten of it would overflow) is a ValueError naming the track."""
    try:
        level = float(value)
    except OverflowError:
        level = math.inf
    if math.isnan(level) or level > Speakers.MAX_LEVEL_DB:
        raise ValueError(Err.BAD_ENERGY_LEVEL.format(limit=Speakers.MAX_LEVEL_DB, value=value, track=track))
    return max(level, SILENCE_DB)


def energy_from_dict(d: dict[str, Any]) -> dict[str, EnergyTimeline]:
    step = _finite(d["step_seconds"])
    if step is None or step <= 0:
        raise ValueError(Err.BAD_ENERGY_STEP.format(value=d["step_seconds"]))
    tracks = d["tracks"]
    if not isinstance(tracks, dict):
        raise TypeError(Err.BAD_ENERGY.format(value=tracks))
    out: dict[str, EnergyTimeline] = {}
    for name, levels in tracks.items():
        if not isinstance(levels, list) or not all(isinstance(v, (int, float)) for v in levels):
            raise TypeError(Err.BAD_ENERGY.format(value=name))
        out[str(name)] = EnergyTimeline(step, tuple(_level(v, str(name)) for v in levels))
    return out


# Verification (fidelity guard). Written only when a claim was verified, so files and the JSON
# sent to the story writer and the curator stay as before for claims that were not. Read back
# strictly: absent, null or {} means "not verified"; any other value that is not an object
# (false, 0, "", [] included) raises TypeError, and the repository reports the file.
def _verification_to_dict(v: Verification) -> dict[str, Any]:
    return {"status": v.status.value, "reason": v.reason}


def _verification_from_dict(d: Any) -> Verification:
    if not isinstance(d, dict):
        raise TypeError(Err.BAD_VERIFICATION.format(value=d))
    reason = d.get("reason", "")
    if not isinstance(reason, str):
        raise TypeError(Err.BAD_REASON.format(value=reason))
    return Verification(VerificationStatus(d["status"]), reason)


def _verified(v: Verification | None) -> dict[str, Any]:
    """The `verification` key of a claim, or nothing when the claim was not verified."""
    return {"verification": _verification_to_dict(v)} if v else {}


def _verification_or_none(d: Any) -> Verification | None:
    """A claim's `verification`; absent, null or {} means the claim was not verified."""
    return None if d is None or d == {} else _verification_from_dict(d)


def _participant_checks(checks: dict[str, Verification]) -> dict[str, Any]:
    """The `participant_checks` key of an analysis, or nothing when no participant was verified."""
    return {"participant_checks": {name: _verification_to_dict(v) for name, v in checks.items()}} if checks else {}


def _participant_checks_from(d: Any) -> dict[str, Verification]:
    if d is None:
        return {}
    if not isinstance(d, dict):
        raise TypeError(Err.BAD_PARTICIPANT_CHECKS.format(value=d))
    return {str(name): _verification_from_dict(v) for name, v in d.items()}


# Action
def action_to_dict(a: Action) -> dict[str, Any]:
    return {
        "id": a.id,
        "description": a.description,
        "owner": a.owner,
        "source_meeting": a.source_meeting,
        "due": _d(a.due),
        "status": a.status.value,
        "priority": a.priority.value if a.priority else None,
        "at": a.at,
        "kind": a.kind.value if a.kind else None,
        **({"for_whom": a.for_whom} if a.for_whom else {}),
        **_verified(a.verification),
    }


def action_from_dict(d: dict[str, Any]) -> Action:
    return Action(
        id=d["id"],
        description=d["description"],
        owner=d["owner"],
        source_meeting=d["source_meeting"],
        due=_parse_d(d.get("due")),
        status=ActionStatus(d.get("status", ActionStatus.OPEN)),
        priority=Priority(d["priority"]) if d.get("priority") else None,
        at=d.get("at"),
        kind=ActionKind(d["kind"]) if d.get("kind") else None,
        verification=_verification_or_none(d.get("verification")),
        for_whom=d.get("for_whom") or None,
    )


def _decision_from(value: Any) -> Decision:
    # analyses written before 2026-10-05 stored decisions as plain strings
    if isinstance(value, str):
        return Decision(value)
    return Decision(value["text"], value.get("at"), _verification_or_none(value.get("verification")))


# Status update: progress the meeting reported on earlier work. Optional keys are written only when set.
def status_update_to_dict(u: StatusUpdate) -> dict[str, Any]:
    return {
        "about": u.about,
        "change": u.change.value,
        "who": u.who,
        "evidence": u.evidence,
        "at": u.at,
        **({"new_due": u.new_due.isoformat()} if u.new_due else {}),
        **({"new_owner": u.new_owner} if u.new_owner else {}),
        **_verified(u.verification),
    }


def status_update_from_dict(d: dict[str, Any]) -> StatusUpdate:
    return StatusUpdate(
        about=d["about"],
        change=StatusChange(d["change"]),
        who=d.get("who", ""),
        evidence=d.get("evidence", ""),
        at=d.get("at"),
        new_due=_parse_d(d.get("new_due")),
        new_owner=d.get("new_owner") or None,
        verification=_verification_or_none(d.get("verification")),
    )


# Analysis
def analysis_to_dict(a: Analysis) -> dict[str, Any]:
    return {
        "meeting_id": a.meeting_id,
        "summary": a.summary,
        "title": a.title,
        "purpose": a.purpose,
        "meeting_type": a.meeting_type.value,
        "participants": list(a.participants),
        "topics": [{"title": t.title, "points": list(t.points)} for t in a.topics],
        "decisions": [{"text": dec.text, "at": dec.at, **_verified(dec.verification)} for dec in a.decisions],
        "my_actions": [action_to_dict(x) for x in a.my_actions],
        "others_actions": [action_to_dict(x) for x in a.others_actions],
        "deadlines": [{"what": dl.what, "when": _d(dl.when), "who": dl.who, **_verified(dl.verification)} for dl in a.deadlines],
        "open_questions": list(a.open_questions),
        "next_meetings": list(a.next_meetings),
        "risks": list(a.risks),
        **_participant_checks(a.participant_checks),
        **({"status_updates": [status_update_to_dict(u) for u in a.status_updates]} if a.status_updates else {}),
    }


def analysis_from_dict(d: dict[str, Any]) -> Analysis:
    return Analysis(
        meeting_id=d["meeting_id"],
        summary=d.get("summary", ""),
        decisions=[_decision_from(x) for x in d.get("decisions", [])],
        my_actions=[action_from_dict(x) for x in d.get("my_actions", [])],
        others_actions=[action_from_dict(x) for x in d.get("others_actions", [])],
        deadlines=[Deadline(x["what"], _parse_d(x.get("when")), x.get("who", ""), _verification_or_none(x.get("verification")))
                   for x in d.get("deadlines", [])],
        open_questions=list(d.get("open_questions", [])),
        next_meetings=list(d.get("next_meetings", [])),
        title=d.get("title", ""),
        purpose=d.get("purpose", ""),
        meeting_type=MeetingType(d.get("meeting_type", MeetingType.OTHER)),
        participants=list(d.get("participants", [])),
        topics=[Topic(x["title"], list(x.get("points", []))) for x in d.get("topics", [])],
        risks=list(d.get("risks", [])),
        participant_checks=_participant_checks_from(d.get("participant_checks")),
        status_updates=[status_update_from_dict(x) for x in d.get("status_updates", [])],
    )


# User story drafts
def criterion_to_value(c: Criterion) -> Any:
    """A criterion with a source as {text, source}; one without (drafted before provenance) as the plain text it was."""
    return {"text": c.text, "source": c.source} if c.source is not None else c.text


def criterion_from_value(value: Any) -> Criterion:
    """Strict, like the verification reader: a source must be HH:MM:SS or SUGGESTION, so a damaged file cannot
    show an invented citation as confirmed."""
    if isinstance(value, str):   # drafts written before 2026-10-14 stored criteria as plain strings
        return Criterion(value)
    text, source = value["text"], value.get("source")
    if not isinstance(text, str):
        raise TypeError(Err.BAD_CRITERION.format(value=value))
    if source is not None and source != SUGGESTION and not (isinstance(source, str) and re.fullmatch(Parse.CLOCK, source)):
        raise ValueError(Err.BAD_CRITERION.format(value=value))
    return Criterion(text, source)


def story_to_dict(s: UserStory) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "narrative": s.narrative,
        "acceptance_criteria": [criterion_to_value(c) for c in s.acceptance_criteria],
        "details": s.details,
        "open_questions": list(s.open_questions),
        "source_action_ids": list(s.source_action_ids),
        "source_meetings": list(s.source_meetings),
        "priority": s.priority.value if s.priority else None,
        "due": _d(s.due),
        "publications": [
            {"destination": pub.destination, "ref": pub.ref, "published_at": _dt(pub.published_at)} for pub in s.publications
        ],
        "kind": s.kind.value if s.kind else None,
        **({"source_text": s.source_text} if s.source_text is not None else {}),   # absent on planner-era drafts and unchanged files
        **_verified(s.verification),
    }


def story_from_dict(d: dict[str, Any]) -> UserStory:
    return UserStory(
        id=d["id"],
        title=d["title"],
        narrative=d.get("narrative", ""),
        acceptance_criteria=[criterion_from_value(c) for c in d.get("acceptance_criteria", [])],
        details=d.get("details", ""),
        open_questions=list(d.get("open_questions", [])),
        source_action_ids=list(d.get("source_action_ids", [])),
        source_meetings=list(d.get("source_meetings", [])),
        priority=Priority(d["priority"]) if d.get("priority") else None,
        due=_parse_d(d.get("due")),
        publications=[
            Publication(x["destination"], x["ref"], datetime.fromisoformat(x["published_at"])) for x in d.get("publications", [])
        ],
        kind=ActionKind(d["kind"]) if d.get("kind") else None,
        verification=_verification_or_none(d.get("verification")),
        source_text=d.get("source_text"),
    )


def skipped_to_dict(k: SkippedAction) -> dict[str, Any]:
    return {"action_id": k.action_id, "reason": k.reason, "duplicate_of": k.duplicate_of,
            **({"source_line": k.source_line} if k.source_line is not None else {})}


def skipped_from_dict(d: dict[str, Any]) -> SkippedAction:
    return SkippedAction(d["action_id"], d.get("reason", ""), d.get("duplicate_of"), d.get("source_line"))


def story_drafts_to_dict(drafts: StoryDrafts) -> dict[str, Any]:
    return {
        "day": drafts.day.isoformat(),
        "stories": [story_to_dict(s) for s in drafts.stories],
        "skipped": [skipped_to_dict(k) for k in drafts.skipped],
    }


def story_drafts_from_dict(d: dict[str, Any]) -> StoryDrafts:
    return StoryDrafts(
        day=date.fromisoformat(d["day"]),
        stories=[story_from_dict(x) for x in d.get("stories", [])],
        skipped=[skipped_from_dict(x) for x in d.get("skipped", [])],
    )


# Activities pass record: one line of the pass log, and `_pass.json` in the version folder.
def pass_record_to_dict(r: PassRecord) -> dict[str, Any]:
    return {
        "ts": r.ts.isoformat(),
        "kind": r.kind.value,
        "meetings": list(r.meetings),
        "ops_applied": r.ops_applied,
        "retried": r.retried,
        "retried_by_kind": dict(r.retried_by_kind),
        "unaccounted_refs": list(r.unaccounted_refs),
        "ignored": r.ignored,
        "user_removed": r.user_removed,
        "box_rescued": r.box_rescued,
        "during_edits": r.during_edits,
        "summary": r.summary,
        "version": r.version,
        "archive_file": r.archive_file,
        "archive_bytes_before": r.archive_bytes_before,
        "archive_bytes_after": r.archive_bytes_after,
        "carried_edits": r.carried_edits,
        "undoes": r.undoes,
        "doc_chars": r.doc_chars,
        "error": r.error,
    }


def pass_record_from_dict(d: dict[str, Any]) -> PassRecord:
    return PassRecord(
        ts=datetime.fromisoformat(d["ts"]),
        kind=PassKind(d["kind"]),
        meetings=tuple(d["meetings"]),
        ops_applied=int(d["ops_applied"]),
        retried=bool(d["retried"]),
        retried_by_kind={str(k): int(v) for k, v in d["retried_by_kind"].items()},
        unaccounted_refs=tuple(d["unaccounted_refs"]),
        ignored=int(d["ignored"]),
        user_removed=int(d["user_removed"]),
        box_rescued=int(d["box_rescued"]),
        during_edits=d["during_edits"],
        summary=d["summary"],
        version=d["version"],
        archive_file=d["archive_file"],
        archive_bytes_before=_optional_int(d["archive_bytes_before"]),
        archive_bytes_after=_optional_int(d["archive_bytes_after"]),
        carried_edits=d["carried_edits"],
        undoes=d["undoes"],
        doc_chars=int(d["doc_chars"]),
        error=d["error"],
    )


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)

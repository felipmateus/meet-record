"""The activities document: pure functions over its text, and the types the curator exchanges.

The document is one Markdown file the user edits and an agent keeps. The agent returns edit operations on whole lines
(`replace`, `insert_after`, `move`, `archive`); `apply_ops` applies them in order and enforces the one code rule: only
`archive` takes a checkbox line away, and no edit changes a box. Lines no edit targets are copied byte for byte.

Everything the functions write or recognise (markers, headings, labels, weekday names, checkbox patterns, the link
target) arrives in a frozen `DocFormat`, the first argument; the application layer builds it from `messages` and
`constants`. This module imports neither, so the Portuguese text and the folder names live in one place each.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Callable, Sequence

from .models import Analysis, TranscriptHealth


class OpKind(StrEnum):
    REPLACE = "replace"
    INSERT_AFTER = "insert_after"
    MOVE = "move"
    ARCHIVE = "archive"


@dataclass(frozen=True)
class Op:
    kind: OpKind
    target: str                 # one or more whole lines, exactly as in the document (trailing whitespace ignored)
    text: str | None = None     # replace / insert_after; "" in replace removes the lines
    reason: str | None = None   # archive (Portuguese, shown in the archive)
    anchor: str | None = None   # move: one whole line; the target is pasted right after it, byte for byte
    refs: tuple[str, ...] = ()  # analysis refs it accounts for ("1.a1", "1.u2", ...)


class OpError(StrEnum):
    """The closed set of reasons an edit is rejected (`OpFailure.error`); two of them carry a count, see below."""

    NOT_FOUND = "not found"  # literal-ok: failure code shown to the repair round; the domain cannot import messages
    PROTECTED = "targets the box or link block"  # literal-ok: failure code, as above
    BREAKS_RULE = "breaks the checkbox rule"  # literal-ok: failure code, as above
    ANCHOR_NOT_FOUND = "anchor not found"  # literal-ok: failure code, as above
    ANCHOR_INSIDE = "anchor inside the target"  # literal-ok: failure code, as above


FOUND_TIMES = "found {n} times"  # literal-ok: failure code with the count, shown to the repair round
ANCHOR_FOUND_TIMES = "anchor found {n} times"  # literal-ok: failure code with the count, as above
RULE_DETAIL = "target: {t_open} open, {t_ticked} ticked; text: {x_open} open, {x_ticked} ticked"  # literal-ok: detail shown to the repair round


@dataclass(frozen=True)
class OpFailure:
    index: int                  # position of the op in the list of its round (first answer, or the repair answer)
    op: Op
    error: str                  # an `OpError` value, `FOUND_TIMES` or `ANCHOR_FOUND_TIMES` filled in
    detail: str = ""            # for the checkbox rule, the counts


@dataclass(frozen=True)
class Applied:
    text: str                   # the document after the ops that applied
    archived: tuple[str, ...]   # texts removed by archive ops, in order (with their reasons below)
    reasons: tuple[str, ...]
    failures: tuple[OpFailure, ...]


@dataclass(frozen=True)
class DocFormat:
    """All document text the pure functions write or recognise; built by the application's `doc_format()`."""

    box_start: str                    # the whole opening marker line of the box
    box_end_prefix: str               # the closing marker is prefix + (" " + stamp when stamped) + suffix
    box_end_suffix: str
    skeleton_stamp: str               # the fixed stamp of the skeleton's closing marker, never a pass version
    links_start: str
    links_end: str
    link_target: str                  # with `{id}`: where a reference label points; render_links fills the id in
    heading_actions: str
    heading_waiting: str
    heading_agenda: str
    heading_context: str
    updated_label: str                # box header
    after_label: str
    focus_label: str
    weekdays: tuple[str, ...]         # Monday first (calendar_strip, box header)
    today_label: str
    open_re: str                      # a line with an open checkbox
    ticked_re: str                    # a line with a ticked checkbox
    label_re: str                     # one capture group: the label of a reference link


class PassKind(StrEnum):
    MEETING = "meeting"
    UNDO = "undo"
    SKIPPED_EMPTY = "skipped_empty"
    FAILED = "failed"


@dataclass(frozen=True)
class MeetingContext:                      # built by CurateMeetings; the adapter only formats it
    meeting_id: str
    title: str
    analysis: Analysis
    health: TranscriptHealth | None
    excerpts: str                          # the transcript around the status updates, with speaker labels


@dataclass(frozen=True)
class RemovedItem:
    text: str
    note: str


@dataclass(frozen=True)
class IgnoredRef:
    ref: str
    why: str


@dataclass(frozen=True)
class CuratorInput:
    document: str
    meetings: list[MeetingContext]        # oldest first
    calendar: str
    user_edits: str                        # the previous pass's during_edits + unified diff of the bodies base -> document
    box_lines: list[str]                   # lines the user typed inside the box
    recent_archive: list[str]              # last 60 entries: header + first line
    last_summary: str | None
    today: datetime
    user_name: str


@dataclass(frozen=True)
class CuratorOutput:
    ops: list[Op]
    user_removed: list[RemovedItem]        # text + note; archived by code as removed by the user
    focus: list[str]                       # 3-5 lines
    summary: str                           # one line
    notify: bool
    ignored: list[IgnoredRef]


@dataclass(frozen=True)
class PassRecord:
    ts: datetime
    kind: PassKind
    meetings: tuple[str, ...]
    ops_applied: int
    retried: bool
    retried_by_kind: dict[str, int]
    unaccounted_refs: tuple[str, ...]
    ignored: int
    user_removed: int
    box_rescued: int                       # lines typed in the box that code had to put back
    during_edits: str                      # unified diff of the bodies F -> F': what the user changed during the call
    summary: str
    version: str                           # names the version files; a meeting pass writes it as the box stamp
    archive_file: str | None
    archive_bytes_before: int | None
    archive_bytes_after: int | None        # undo truncates only while the archive still has this size
    carried_edits: str                     # the during_edits part of the user_edits this pass received
    undoes: str | None                     # kind undo: the version of the pass it undid
    doc_chars: int
    error: str | None


# --- lines ------------------------------------------------------------------------------------------------------

_SPACE = " "
_QUOTE = "> "          # a line of the box
_BARE_QUOTE = ">"
_BOLD = "**"
_DOT = ". "
_SEP = " · "
_LIST = ", "


def _lines(text: str) -> list[str]:
    """Lines with their endings; only "\\n" separates lines (the other Unicode separators stay inside a line)."""
    parts = text.split("\n")
    out = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        out.append(parts[-1])
    return out


def _ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def _terminated(lines: list[str], eol: str = "\n") -> list[str]:
    """Every line but the last ends its line (an edit may leave an unterminated last line in the middle)."""
    return [line if line.endswith("\n") else line + eol for line in lines[:-1]] + lines[-1:]


@lru_cache(maxsize=None)
def _pattern(source: str) -> re.Pattern[str]:
    return re.compile(source)


@lru_cache(maxsize=None)
def _box_end(fmt: DocFormat) -> re.Pattern[str]:
    return re.compile(re.escape(fmt.box_end_prefix) + r"(?:" + _SPACE + r"(\S+))?" + re.escape(fmt.box_end_suffix))


def _regions(fmt: DocFormat, lines: list[str]) -> tuple[int, int, int]:
    """(first line of the body, line after the body, first line of the box or -1). The box counts only when both of
    its markers are present, in order; the link block likewise."""
    keys = [line.rstrip() for line in lines]
    start, box = 0, -1
    end_re = _box_end(fmt)
    for i, key in enumerate(keys):
        if key == fmt.box_start:
            for j in range(i + 1, len(keys)):
                if end_re.fullmatch(keys[j]):
                    start, box = j + 1, i
                    break
            break
    end = len(lines)
    for i in range(start, len(keys)):
        if keys[i] == fmt.links_start:
            if fmt.links_end in keys[i + 1:]:
                end = i
            break
    return start, end, box


def _chars(lines: list[str], upto: int) -> int:
    return sum(len(line) for line in lines[:upto])


def body_span(fmt: DocFormat, document: str) -> tuple[int, int]:
    """Character range of the body: everything but the box (and what precedes it) and the link block."""
    lines = _lines(document)
    start, end, _ = _regions(fmt, lines)
    return _chars(lines, start), _chars(lines, end)


def body_text(fmt: DocFormat, document: str) -> str:
    """The body: what diffs and edit targets are computed on."""
    first, last = body_span(fmt, document)
    return document[first:last]


def box_stamp(fmt: DocFormat, document: str) -> str | None:
    """The stamp in the box's closing marker; None when the marker has none (or was deleted or rewritten)."""
    end_re = _box_end(fmt)
    for line in _lines(document):
        found = end_re.fullmatch(line.rstrip())
        if found:
            return found.group(1)
    return None


def open_count(fmt: DocFormat, text: str) -> int:
    pattern = _pattern(fmt.open_re)
    return sum(1 for line in text.split("\n") if pattern.match(line.rstrip("\r")))


def ticked_count(fmt: DocFormat, text: str) -> int:
    pattern = _pattern(fmt.ticked_re)
    return sum(1 for line in text.split("\n") if pattern.match(line.rstrip("\r")))


_FOCUS_LINE = re.compile(r"^> \d+\. ")  # literal-ok: a numbered line of the box, written by render_box
_SECTION_HEADING = "## "


def box_focus(fmt: DocFormat, document: str) -> list[str]:
    """The numbered focus lines of the box as stored, without the quote mark (`1. **Enviar** à Carla`); none without a box."""
    lines = _lines(document)
    _, _, box = _regions(fmt, lines)
    if box < 0:
        return []
    end_re = _box_end(fmt)
    focus: list[str] = []
    for line in lines[box + 1:]:
        key = line.rstrip()
        if end_re.fullmatch(key):
            break
        if _FOCUS_LINE.match(key):
            focus.append(key[len(_QUOTE):])
    return focus


def section_counts(fmt: DocFormat, document: str) -> dict[str, int]:
    """What is left to do per section, keyed by its heading: open checkboxes under the actions and waiting headings, lines (blank
    and indented ones aside) under the agenda and context headings. A section ends at the next `## ` line. A heading the user
    renamed or removed is absent; one that appears twice adds up."""
    counted: dict[str, int] = {}
    current: str | None = None
    for line in body_text(fmt, document).split("\n"):
        key = line.rstrip()
        if key.startswith(_SECTION_HEADING):
            current = key if key in (fmt.heading_actions, fmt.heading_waiting, fmt.heading_agenda, fmt.heading_context) else None
            if current is not None:
                counted.setdefault(current, 0)
        elif current in (fmt.heading_actions, fmt.heading_waiting):
            counted[current] += 1 if _pattern(fmt.open_re).match(key) else 0
        elif current is not None and key and not key[0].isspace() and not key.startswith("#"):
            counted[current] += 1
    return counted


# --- apply_ops --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Failed:
    error: str
    detail: str = ""


@dataclass(frozen=True)
class _Done:
    text: str
    archived: str | None = None


def _wanted(text: str | None) -> list[str]:
    """The lines a target or anchor names, without trailing whitespace (one final newline is not a blank line)."""
    parts = [part.rstrip() for part in (text or "").split("\n")]
    if parts and parts[-1] == "":
        parts.pop()
    return parts if any(parts) else []


def _occurrences(keys: list[str], wanted: list[str]) -> list[int]:
    size = len(wanted)
    if not size:
        return []
    return [i for i in range(len(keys) - size + 1) if keys[i:i + size] == wanted]


def _locate(keys: list[str], body: tuple[int, int], wanted: list[str], not_found: str, many: str) -> int | _Failed:
    """The one place `wanted` occurs in the body; a failure otherwise (the box and link block never match)."""
    first, last = body
    hits = [first + i for i in _occurrences(keys[first:last], wanted)]
    if len(hits) == 1:
        return hits[0]
    if hits:
        return _Failed(many.format(n=len(hits)))
    return _Failed(OpError.PROTECTED if _occurrences(keys, wanted) else not_found)


def _touches_protected(fmt: DocFormat, text: str) -> bool:
    end_re = _box_end(fmt)
    for line in text.split("\n"):
        key = line.rstrip()
        if key in (fmt.box_start, fmt.links_start, fmt.links_end) or end_re.fullmatch(key):
            return True
    return False


def _written(text: str | None, eol: str, last_ending: str) -> list[str]:
    """The lines of an op's text; the last one takes `last_ending`, so the document keeps its way of ending."""
    if not text:
        return []
    body = text[:-1] if text.endswith("\n") else text
    parts = [part.rstrip("\r") for part in body.split("\n")]
    return [part + eol for part in parts[:-1]] + [parts[-1] + last_ending]


def _apply_one(fmt: DocFormat, document: str, op: Op) -> _Failed | _Done:
    lines = _lines(document)
    keys = [line.rstrip() for line in lines]
    start, end, _ = _regions(fmt, lines)
    wanted = _wanted(op.target)
    found = _locate(keys, (start, end), wanted, OpError.NOT_FOUND, FOUND_TIMES)
    if isinstance(found, _Failed):
        return found
    first, last = found, found + len(wanted)
    target = lines[first:last]
    eol = "\r\n" if target[0].endswith("\r\n") else "\n"
    last_ending = _ending(target[-1])
    if op.kind in (OpKind.REPLACE, OpKind.INSERT_AFTER) and _touches_protected(fmt, op.text or ""):
        return _Failed(OpError.PROTECTED)
    target_text = "".join(target)

    if op.kind is OpKind.REPLACE:
        t_open, t_ticked = open_count(fmt, target_text), ticked_count(fmt, target_text)
        x_open, x_ticked = open_count(fmt, op.text or ""), ticked_count(fmt, op.text or "")
        if x_open < t_open or x_ticked != t_ticked:
            return _Failed(OpError.BREAKS_RULE, RULE_DETAIL.format(t_open=t_open, t_ticked=t_ticked, x_open=x_open, x_ticked=x_ticked))
        out = lines[:first] + _written(op.text, eol, last_ending) + lines[last:]
        return _Done("".join(_terminated(out, eol)))

    if op.kind is OpKind.INSERT_AFTER:
        x_open, x_ticked = open_count(fmt, op.text or ""), ticked_count(fmt, op.text or "")
        if x_ticked:
            return _Failed(OpError.BREAKS_RULE, RULE_DETAIL.format(t_open=0, t_ticked=0, x_open=x_open, x_ticked=x_ticked))
        before = lines[:last]
        if before and not before[-1].endswith("\n"):
            before[-1] += eol
            added = _written(op.text, eol, "")
        else:
            added = _written(op.text, eol, eol)
        return _Done("".join(_terminated(before + added + lines[last:], eol)))

    if op.kind is OpKind.ARCHIVE:
        out = lines[:first] + lines[last:]
        return _Done("".join(out), target_text.rstrip("\r\n"))

    # move: cut the target lines and paste them right after the anchor line, byte for byte
    anchor = _wanted(op.anchor)
    where = _locate(keys, (start, end), anchor, OpError.ANCHOR_NOT_FOUND, ANCHOR_FOUND_TIMES)
    if isinstance(where, _Failed):
        return where
    anchor_end = where + len(anchor)
    if where < last and first < anchor_end:
        return _Failed(OpError.ANCHOR_INSIDE)
    rest = lines[:first] + lines[last:]
    position = anchor_end if anchor_end <= first else anchor_end - len(target)
    out = rest[:position] + target + rest[position:]
    return _Done("".join(_terminated(out, eol)))


def apply_ops(fmt: DocFormat, document: str, ops: Sequence[Op]) -> Applied:
    """Apply the ops in order, each to the text the previous ones left. A failing op changes nothing and the rest still
    apply. Targets and anchors are whole lines, unique within the body; trailing whitespace is ignored.

    Checkbox rule, per op: `replace` keeps at least as many open lines as its target had and exactly as many ticked
    ones; `insert_after` adds no ticked line; `move` cannot change a count; `archive` is unrestricted. The rule guards
    state and count, not the identity of a line."""
    text = document
    archived: list[str] = []
    reasons: list[str] = []
    failures: list[OpFailure] = []
    for index, op in enumerate(ops):
        outcome = _apply_one(fmt, text, op)
        if isinstance(outcome, _Failed):
            failures.append(OpFailure(index=index, op=op, error=str(outcome.error), detail=outcome.detail))
            continue
        text = outcome.text
        if outcome.archived is not None:
            archived.append(outcome.archived)
            reasons.append(op.reason or "")
    return Applied(text=text, archived=tuple(archived), reasons=tuple(reasons), failures=tuple(failures))


# --- the box, the user's lines in it, the link block -------------------------------------------------------------

def _is_generated(fmt: DocFormat, line: str, written: Counter[str] | None) -> bool:
    """A line of the box the app writes: blank, the header, the focus title or a numbered focus line. A numbered line looks the
    same typed by hand (`> 2. Ligar para o João`, the natural way to add an item to a numbered list), so with the focus lines the
    last pass wrote (`written`) a numbered line counts as generated only while one of those is left to match it; without them
    (no base yet) every numbered line does."""
    key = line.rstrip()
    if not key or key == _BARE_QUOTE:
        return True
    if key.startswith(_QUOTE + _BOLD + fmt.updated_label) or key.startswith(_QUOTE + _BOLD + fmt.focus_label + _BOLD):
        return True
    if re.match(re.escape(_QUOTE) + r"\d+\. ", key) is None:
        return False
    if written is None:
        return True
    if written[key] > 0:
        written[key] -= 1
        return True
    return False


def _closing(fmt: DocFormat, stamp: str) -> str:
    return fmt.box_end_prefix + (_SPACE + stamp if stamp else "") + fmt.box_end_suffix


def render_box(fmt: DocFormat, document: str, focus: Sequence[str], meetings: Sequence[str], now: datetime, stamp: str,
               base: str | None = None) -> tuple[str, list[str]]:
    """Rewrites the box, writing `stamp` (the pass version) into its closing marker; returns the new document and the
    lines the user had typed inside the old box. Without a box, a new one goes on top. `base` is the document as the last pass
    left it: its focus lines are the numbered lines the app wrote, so any other numbered line in the box is the user's."""
    written = Counter(_QUOTE + line for line in box_focus(fmt, base)) if base is not None else None
    lines = _lines(document)
    start, _, box = _regions(fmt, lines)
    end_re = _box_end(fmt)
    if box >= 0:
        close = next(i for i in range(box + 1, len(lines)) if end_re.fullmatch(lines[i].rstrip()))
        typed = [line.rstrip("\r\n") for line in lines[box + 1:close] if not _is_generated(fmt, line, written)]
    else:
        box, close, typed = 0, -1, []
    when = _SPACE.join([fmt.weekdays[now.weekday()], now.strftime("%d/%m"), now.strftime("%H:%M")])
    header = _QUOTE + _BOLD + fmt.updated_label + _SPACE + when + _BOLD
    if meetings:
        header += _SEP + fmt.after_label + _SPACE + _LIST.join(meetings)
    new = [fmt.box_start, header]
    if focus:
        new += [_BARE_QUOTE, _QUOTE + _BOLD + fmt.focus_label + _BOLD]
        new += [_QUOTE + f"{n}" + _DOT + _SPACE.join(item.split()) for n, item in enumerate(focus, 1)]
    new.append(_closing(fmt, stamp))
    block = [line + "\n" for line in new]
    after = lines[close + 1:]
    if close < 0 and after and after[0].strip():
        block.append("\n")
    return "".join(lines[:box] + block + after), typed


def rescue_box_lines(fmt: DocFormat, document: str, lines: Sequence[str]) -> str:
    """Puts each line (not already a line of the body) at the top of the `## Minhas ações` section, creating the heading
    right after the box when it is missing. No sub-line is added: the next pass treats them as user lines."""
    doc = _lines(document)
    start, end, _ = _regions(fmt, doc)
    present = {line.rstrip() for line in doc[start:end] if line.strip()}
    missing = [line.rstrip("\r\n") for line in lines if line.strip() and line.rstrip() not in present]
    if not missing:
        return document
    added = [line + "\n" for line in missing]
    heading = next((i for i in range(start, end) if doc[i].rstrip() == fmt.heading_actions), -1)
    if heading < 0:
        block = [fmt.heading_actions + "\n", "\n"] + added
        if start < len(doc) and doc[start].strip():
            block.append("\n")
        return "".join(_terminated(doc[:start]) + block + doc[start:])
    at = heading + 1
    if at < len(doc) and not doc[at].strip():
        at += 1
    tail = doc[at:]
    if tail and tail[0].startswith("#"):
        added.append("\n")
    return "".join(_terminated(doc[:at]) + added + tail)


def render_links(fmt: DocFormat, document: str, meeting_exists: Callable[[str], bool]) -> str:
    """Regenerates the link block from the labels in use outside it, sorted, one definition per existing meeting."""
    lines = _lines(document)
    first = last = -1
    for i, line in enumerate(lines):
        if line.rstrip() == fmt.links_start:
            for j in range(i + 1, len(lines)):
                if lines[j].rstrip() == fmt.links_end:
                    first, last = i, j
                    break
            break
    outside = lines if first < 0 else lines[:first] + lines[last + 1:]
    pattern = _pattern(fmt.label_re)
    labels = sorted({found for line in outside for found in pattern.findall(line)})
    block = [fmt.links_start + "\n"]
    block += ["[" + label + "]: " + fmt.link_target.replace("{id}", label) + "\n" for label in labels if meeting_exists(label)]
    block.append(fmt.links_end + "\n")
    if first >= 0:
        return "".join(lines[:first] + block + lines[last + 1:])
    head = _terminated(lines) if lines else []
    if head and not head[-1].endswith("\n"):
        head[-1] += "\n"
    if head and head[-1].strip():
        head.append("\n")
    return "".join(head + block)


# --- calendar, working days, diff ---------------------------------------------------------------------------------

def calendar_strip(fmt: DocFormat, today: date, days: int = 14) -> str:
    """`days` entries from today on: weekday and day/month, today marked, weekend days in brackets."""
    entries: list[str] = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        entry = _SPACE.join([fmt.weekdays[day.weekday()], day.strftime("%d/%m")] + ([fmt.today_label] if offset == 0 else []))
        entries.append("[" + entry + "]" if day.weekday() >= 5 else entry)
    return _LIST.join(entries)


def working_days_ago(today: date, n: int) -> date:
    """Today is day 0 and is not counted, even on a weekend; each step back lands on the previous Monday-Friday day,
    holidays ignored. n = 0 is today."""
    day = today
    for _ in range(n):
        day -= timedelta(days=1)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
    return day


def _plain(text: str) -> list[str]:
    parts = [part.rstrip("\r") for part in text.split("\n")]
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def unified_diff(base: str, current: str) -> str:
    """The hunks (no file header) that turn `base` into `current`; "" when they are the same. Callers pass bodies."""
    return "\n".join(list(difflib.unified_diff(_plain(base), _plain(current), lineterm="", n=2))[2:])

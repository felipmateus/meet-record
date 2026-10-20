"""File-backed store of the activities document (ADR-003): one OS lock, a recoverable commit order, a pass log.

Layout under <data_dir>:
  activities/atividades.md                the document the user edits by hand
  activities/arquivo/<YYYY-MM>.md         append-only archive, one file per month
  activities/.curator/lock                flock target (always empty)
  activities/.curator/base.md             the document as the last pass left it
  activities/.curator/versions/<version>_{before,after,base,prevbase}.md and <version>_pass.json
  log/activities.jsonl                    one PassRecord per line; the line is the commit point of a pass

`commit` writes, in order: the version files, the archive entries, the document, base.md and the pass-log line.
A failure raised inside the process before the document is replaced undoes what was written; after it, the
remaining steps are retried. After a hard stop, `lock()` reconciles each version set with no pass-log line on
entry: the document was replaced iff its box stamp is not None and equals the stamp of the set's `_after`.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.fs_retry import atomic_write, retry_io
from teams_recorder.application.ports import VersionFiles
from teams_recorder.constants import Activities, Files, VersionPart
from teams_recorder.domain import CommitIncomplete, DocFormat, PassRecord, RepositoryError, box_stamp
from teams_recorder.messages import ActivityDoc, Err, Log

log = logging.getLogger(__name__)

_NEWLINE = "\n"
_ENCODING = "utf-8"


@contextmanager
def _io_boundary() -> Iterator[None]:
    """The store's edge towards the callers: a file system failure leaves it as a `RepositoryError` (the CLI and the doctor
    report those; a raw `OSError` would end as a traceback). Also a decorator, for the methods that are not a generator."""
    try:
        yield
    except OSError as exc:
        raise RepositoryError(Err.ACTIVITY_STORE_IO.format(error=exc)) from exc


def append_text(path: Path, text: str) -> None:
    """Appends `text` (UTF-8, newlines untouched) to `path`, creating it and its folders, and flushes it to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        with open(path, "ab") as handle:
            handle.write(text.encode(_ENCODING))
            handle.flush()
            os.fsync(handle.fileno())

    retry_io(run, str(path))


def _read_bytes(path: Path) -> bytes | None:
    try:
        return retry_io(path.read_bytes, str(path))
    except FileNotFoundError:
        return None


def _read(path: Path) -> str | None:
    """The file's text with its line endings untouched; None when it does not exist."""
    data = _read_bytes(path)
    return None if data is None else data.decode(_ENCODING)


def _size(path: Path) -> int:
    try:
        return retry_io(lambda: path.stat().st_size, str(path))
    except FileNotFoundError:
        return 0


def _delete(path: Path) -> None:
    retry_io(lambda: path.unlink(missing_ok=True), str(path))


def _cut(path: Path, size: int) -> None:
    """Truncates `path` to `size` bytes (never grows it); a file left empty is removed, like one that never existed."""
    current = _size(path)
    if current > size:
        def run() -> None:
            with open(path, "r+b") as handle:
                handle.truncate(size)
                handle.flush()
                os.fsync(handle.fileno())

        retry_io(run, str(path))
    if size == 0 and path.exists() and _size(path) == 0:
        _delete(path)


class FsActivityStore:
    """`ActivityStore` on files. `write` and `append` are the only ways it changes a file's content, so a test can make
    one step fail (or stop) and look at what is left."""

    def __init__(self, data_dir: Path, fmt: DocFormat, keep_versions: int = Activities.KEEP_VERSIONS, *,
                 write: Callable[[Path, str], None] = atomic_write, append: Callable[[Path, str], None] = append_text,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.fmt = fmt
        self.keep_versions = keep_versions
        self._write = write
        self._append = append
        self._sleep = sleep
        self.root = Path(data_dir) / Files.ACTIVITIES_DIR
        self.document = self.root / Files.ACTIVITIES_DOC
        self.archive_dir = self.root / Files.ARCHIVE_DIR
        self.curator_dir = self.root / Files.CURATOR_DIR
        self.base_file = self.curator_dir / Files.CURATOR_BASE
        self.versions_dir = self.curator_dir / Files.VERSIONS_DIR
        self.lock_file = self.curator_dir / Files.CURATOR_LOCK
        self.pass_log = Path(data_dir) / Files.LOG_DIR / Files.ACTIVITIES_LOG

    # --- lock and reconciliation ----------------------------------------
    @contextmanager
    def lock(self, wait: bool = True) -> Iterator[bool]:
        with _io_boundary():   # only the setup: what the caller's block raises is not the store's to translate
            self.curator_dir.mkdir(parents=True, exist_ok=True)
            handle = retry_io(lambda: open(self.lock_file, "a+b"), str(self.lock_file))
        try:
            with _io_boundary():
                acquired = self._acquire(handle, wait)
            if not acquired:
                yield False
                return
            try:
                with _io_boundary():
                    self._reconcile()
                yield True
            finally:
                self._release(handle)
        finally:
            handle.close()

    def _acquire(self, handle: IO[bytes], wait: bool) -> bool:
        if sys.platform == "win32":
            import msvcrt
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    return True
                except OSError:
                    if not wait:
                        return False
                    self._sleep(Activities.LOCK_POLL)
        import fcntl
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            return True
        except BlockingIOError:
            return False

    @staticmethod
    def _release(handle: IO[bytes]) -> None:
        if sys.platform == "win32":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_UN)

    def _reconcile(self) -> None:
        """Settles every version set whose pass-log line is missing: completed when the document carries the stamp of its
        `_after`, undone otherwise (a document with no stamp, or none at all, is never counted as replaced)."""
        logged = {record.version for record in self.passes()}
        for version in self._versions():
            if version in logged:
                continue
            record = self._saved_record(version)
            after = _read(self._part(version, VersionPart.AFTER))
            document = self.read_document()
            stamp = box_stamp(self.fmt, document) if document is not None else None
            if record is not None and after is not None and stamp is not None and stamp == box_stamp(self.fmt, after):
                log.warning(Log.ACTIVITIES_ROLLED_FORWARD, version)
                self._complete(version, record)
            else:
                log.warning(Log.ACTIVITIES_ROLLED_BACK, version)
                self._undo_writes(version, record)

    def _saved_record(self, version: str) -> PassRecord | None:
        text = _read(self._part(version, VersionPart.PASS))
        if text is None:
            return None
        try:
            return codec.pass_record_from_dict(json.loads(text))
        except (ValueError, KeyError, TypeError, AttributeError):
            return None   # unreadable: nothing was appended to the archive without a readable record

    # --- paths -----------------------------------------------------------
    def path(self) -> Path:
        return self.document

    def _part(self, version: str, part: VersionPart) -> Path:
        return self.versions_dir / Files.VERSION_FILE.format(version=version, part=part.value)

    def _versions(self) -> list[str]:
        """The versions that have at least one file, oldest first (a version is the file name up to its first underscore)."""
        if not self.versions_dir.is_dir():
            return []
        names = retry_io(lambda: [p.name for p in self.versions_dir.iterdir()], str(self.versions_dir))
        return sorted({name.partition("_")[0] for name in names if "_" in name and not name.endswith(Files.TMP_SUFFIX)})

    # --- reads -----------------------------------------------------------
    @_io_boundary()
    def read_document(self) -> str | None:
        return _read(self.document)

    @_io_boundary()
    def read_base(self) -> str | None:
        return _read(self.base_file)

    @_io_boundary()
    def version(self, name: str) -> VersionFiles:
        def required(part: VersionPart) -> str:
            path = self._part(name, part)
            text = _read(path)
            if text is None:
                raise RepositoryError(Err.FILE_MISSING.format(path=path))
            return text

        return VersionFiles(required(VersionPart.BEFORE), required(VersionPart.AFTER), _read(self._part(name, VersionPart.BASE)),
                            _read(self._part(name, VersionPart.PREVBASE)))

    @_io_boundary()
    def version_names(self) -> list[str]:
        return self._versions()

    @_io_boundary()
    def passes(self) -> list[PassRecord]:
        text = _read(self.pass_log)
        if text is None:
            return []
        lines = [(number, line) for number, line in enumerate(text.split(_NEWLINE), 1) if line.strip()]
        records: list[PassRecord] = []
        for position, (number, line) in enumerate(lines):
            record = self._parse_line(line)
            if record is not None:
                records.append(record)
            elif position == len(lines) - 1:
                log.warning(Log.ACTIVITIES_LOG_TORN, self.pass_log)   # a stop in the middle of the write: absent
            else:
                raise RepositoryError(Err.BAD_JSON.format(path=self.pass_log, error=Err.ACTIVITY_LOG_LINE.format(line=number)))
        return records

    @staticmethod
    def _parse_line(line: str) -> PassRecord | None:
        try:
            return codec.pass_record_from_dict(json.loads(line))
        except (ValueError, KeyError, TypeError, AttributeError):
            return None

    # --- archive -----------------------------------------------------------
    def _entry(self, text: str, reason: str, record: PassRecord) -> str:
        header = ActivityDoc.ARCHIVE_HEADER.format(date=record.ts.strftime(Activities.DATE_FORMAT), reason=reason)
        body = text if text.endswith(_NEWLINE) else text + _NEWLINE
        labels = sorted(set(re.findall(self.fmt.label_re, text)))
        links = [ActivityDoc.LINK_DEFINITION.format(label=label, target=Activities.ARCHIVE_LINK_UP + self.fmt.link_target.replace("{id}", label))
                 for label in labels]
        return header + _NEWLINE + body + "".join(link + _NEWLINE for link in links) + _NEWLINE

    @_io_boundary()
    def recent_archive(self, limit: int) -> list[str]:
        if limit <= 0 or not self.archive_dir.is_dir():
            return []
        files = retry_io(lambda: sorted(self.archive_dir.iterdir(), reverse=True), str(self.archive_dir))
        found: list[str] = []
        for path in files:
            text = _read(path) or ""
            entries = self._entries(text)
            found = entries + found
            if len(found) >= limit:
                break
        return found[-limit:]

    @staticmethod
    def _entries(text: str) -> list[str]:
        """Each entry of an archive file as its heading line and its first text line."""
        lines = text.split(_NEWLINE)
        entries: list[str] = []
        for i, line in enumerate(lines):
            if line.startswith(ActivityDoc.ARCHIVE_PREFIX):
                first = lines[i + 1] if i + 1 < len(lines) and not lines[i + 1].startswith(ActivityDoc.ARCHIVE_PREFIX) else ""
                entries.append(line + (_NEWLINE + first if first.strip() else ""))
        return entries

    @_io_boundary()
    def truncate_archive(self, record: PassRecord) -> bool:
        if record.archive_file is None or record.archive_bytes_before is None or record.archive_bytes_after is None:
            return True   # the pass archived nothing: nothing to take back
        path = self.root / record.archive_file
        size = _size(path)
        if size != record.archive_bytes_after:
            log.warning(Log.ACTIVITIES_ARCHIVE_CHANGED, record.archive_file, record.archive_bytes_after, size)
            return False
        _cut(path, record.archive_bytes_before)
        return True

    # --- commit ------------------------------------------------------------
    @_io_boundary()
    def commit(self, before: str, after: str, archived: list[tuple[str, str]], base: str | None, record: PassRecord) -> None:
        version = record.version
        prevbase = self.read_base()
        entries = "".join(self._entry(text, reason, record) for text, reason in archived)
        archive_path: Path | None = None
        if entries:
            name = Files.ARCHIVE_MONTH.format(month=record.ts.strftime(Activities.MONTH_FORMAT))
            archive_path = self.archive_dir / name
            size = _size(archive_path)
            record = dataclasses.replace(record, archive_file=(Path(Files.ARCHIVE_DIR) / name).as_posix(), archive_bytes_before=size,
                                         archive_bytes_after=size + len(entries.encode(_ENCODING)))
        try:
            self._write(self._part(version, VersionPart.BEFORE), before)
            self._write(self._part(version, VersionPart.AFTER), after)
            if base is not None:
                self._write(self._part(version, VersionPart.BASE), base)
            if prevbase is not None:
                self._write(self._part(version, VersionPart.PREVBASE), prevbase)
            self._write(self._part(version, VersionPart.PASS), json.dumps(codec.pass_record_to_dict(record), ensure_ascii=False, indent=2))
            if archive_path is not None:
                self._append(archive_path, entries)
            self._write(self.document, after)
        except Exception:
            self._undo_writes(version, record)
            raise
        self._finish(version, record, base)

    def _finish(self, version: str, record: PassRecord, base: str | None) -> None:
        """What follows the document replace: base.md, then the pass-log line (the commit point), then the rotation."""
        self._retried(version, Files.CURATOR_BASE, lambda: self._write_base(base))
        self._retried(version, Files.ACTIVITIES_LOG, lambda: self._log_pass(record))
        self._rotate()

    def _retried(self, version: str, step: str, operation: Callable[[], None]) -> None:
        for attempt in range(1, Activities.COMMIT_ATTEMPTS + 1):
            try:
                operation()
                return
            except OSError as exc:
                if attempt == Activities.COMMIT_ATTEMPTS:
                    raise CommitIncomplete(Err.ACTIVITY_COMMIT_INCOMPLETE.format(version=version, step=step, error=exc)) from exc
                log.warning(Log.ACTIVITIES_COMMIT_RETRY, version, step, exc, attempt, Activities.COMMIT_ATTEMPTS)

    def _write_base(self, base: str | None) -> None:
        if base is None:
            _delete(self.base_file)
        else:
            self._write(self.base_file, base)

    @_io_boundary()
    def log_pass(self, record: PassRecord) -> None:
        """Appends a record of a pass that changed nothing (skipped as empty, or failed): no version files, no document write."""
        self._log_pass(record)

    def _log_pass(self, record: PassRecord) -> None:
        self._repair_log_tail()
        self._append(self.pass_log, json.dumps(codec.pass_record_to_dict(record), ensure_ascii=False) + _NEWLINE)

    def _repair_log_tail(self) -> None:
        """A write cut short leaves a last line with no newline: complete it when it is a whole record, drop it when not."""
        data = _read_bytes(self.pass_log)
        if not data or data.endswith(_NEWLINE.encode()):
            return
        cut = data.rfind(_NEWLINE.encode()) + 1
        if self._parse_line(data[cut:].decode(_ENCODING, errors="replace")) is not None:
            self._append(self.pass_log, _NEWLINE)
        else:
            _cut(self.pass_log, cut)

    def _complete(self, version: str, record: PassRecord) -> None:
        """Rolls an interrupted commit forward: base.md from the set's `_base` (deleted when it has none), the pass-log line."""
        self._write_base(_read(self._part(version, VersionPart.BASE)))
        self._log_pass(record)
        self._rotate()

    def _undo_writes(self, version: str, record: PassRecord | None) -> None:
        """Takes back what a pass wrote before the document: the archive entries, then the version files."""
        if record is not None and record.archive_file is not None and record.archive_bytes_before is not None:
            _cut(self.root / record.archive_file, record.archive_bytes_before)
        for part in VersionPart:
            path = self._part(version, part)
            _delete(path)
            _delete(path.with_name(path.name + Files.TMP_SUFFIX))

    def _rotate(self) -> None:
        """Keeps the version files of the newest `keep_versions` passes; the pass is already committed, so a failure is logged."""
        try:
            versions = self._versions()
            for version in versions[:max(len(versions) - self.keep_versions, 0)]:
                for part in VersionPart:
                    _delete(self._part(version, part))
        except OSError as exc:
            log.warning(Log.ACTIVITIES_ROTATE_FAILED, self.versions_dir, exc)

"""Shared, hardware-independent scan naming, durable CSV and JSONL recording.

The recorders know nothing about Tkinter or instrument drivers.  The legacy
application re-exports these helpers, and its recorder subclass preserves the
old monkeypatchable entry points for existing callers.
"""

from __future__ import annotations

import csv
import datetime as datetime_module
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

WINDOWS_RESERVED_FILE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)


def scan_file_stem(name: str) -> str:
    """The typed name as a file stem: stripped, a typed ".csv" dropped; ""
    when blank (the page's timestamped default then).  ValueError unless it
    is a valid Windows file name without a path."""
    stem = str(name).strip()
    if not stem:
        return ""
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]
    if (not stem or stem.endswith((".", " ")) or re.search(r'[<>:"/\\|?*\x00-\x1f]', stem)
            or stem.split(".")[0].upper() in WINDOWS_RESERVED_FILE_NAMES):
        raise ValueError("Use a valid Windows file name without a path.")
    return stem


def make_scan_run_folder(parent: Path, stem: str) -> Path:
    """Make and return <parent>/<stem>/, or <stem>_01, _02, ... when the name
    is taken (by a folder or a file), as SHV's live CSV took _01, _02 ...
    before it had a run folder.  No exist_ok: another run's folder is never
    reused, so nothing in it can be overwritten."""
    suffix = 0
    while True:
        directory = Path(parent) / (f"{stem}_{suffix:02d}" if suffix else stem)
        try:
            directory.mkdir()
        except FileExistsError:
            suffix += 1
            continue
        return directory


def scan_log_line(name: str, details: dict, *, datetime_class=None) -> str:
    """One JSON log record. Optionally use the caller's clock for compatibility.

    The original application allows tests to replace app.datetime_module.
    Its legacy wrapper passes that clock here; standalone core users default
    to Python's normal datetime.datetime.
    """
    clock = datetime_class if datetime_class is not None else datetime_module.datetime
    record = {
        "timestamp": clock.now().astimezone().isoformat(timespec="milliseconds"),
        "event": name,
        **details,
    }
    return json.dumps(record, ensure_ascii=False, default=str) + "\n"


class ScanRunRecorder:
    """A scan's run folder, live CSV and JSON-lines log, for every scan page
    (user, 2026-10-18); SHV's recorder generalised.

    <parent>/<stem>/ (or <stem>_01, ... when taken) holds <stem>.csv and
    <stem>.log, made empty here and opened "x".  The stem is the typed name,
    or <page>_<date>_<time> when it is blank.  With settings, the log's first
    line, run_prepared, is written here.  If it cannot be written, the run is
    closed not_started and the error raised, so nothing starts.  The folder
    and any file made stay, as evidence.

    The worker and the Tk thread both write, so every write and the close
    hold one lock.  A log write never raises: the STOP and the zeroing of a
    failure must never be skipped for a bad disk.  The first failure is kept
    instead and check() raises it on the worker.  A CSV row that cannot be
    written raises, as the PPMS live CSV does.  close() is best effort and
    runs once.

    directory, csv_path, log_path and rows_written are for the page to read;
    fieldnames is the CSV header (None until the first row)."""

    # A fixed header, written when the files are made (STFMR's columns); None:
    # the first row's keys.
    FIELDNAMES: tuple[str, ...] | None = None
    # Overridden by the legacy application shim; the standalone core does
    # not depend on a particular file's __file__ or application globals.
    PROGRAM_NAME = "Transport_all.py"
    APPLICATION_VERSION = ""

    def _validated_stem(self, stem: str) -> str:
        return scan_file_stem(stem)

    def _make_run_folder(self, parent: Path, stem: str) -> Path:
        return make_scan_run_folder(parent, stem)

    def _format_log(self, name: str, details: dict) -> str:
        return scan_log_line(name, details)


    def __init__(self, parent: Path, page: str, name: str = "", settings: dict | None = None, *,
                 label: str | None = None) -> None:
        # page: the blank name's <page>_<date>_<time>; label: the page's name
        # in messages (the page by default).
        self.page, self.label = page, label or page
        stem = name or self._default_stem()
        if self._validated_stem(stem) != stem:
            raise ValueError(f"{stem!r} is not a valid file name for the run folder")
        self.directory = self._make_run_folder(Path(parent), stem)
        stem = self.directory.name
        self.csv_path = self.directory / f"{stem}.csv"
        self.log_path = self.directory / f"{stem}.log"
        self.lock = threading.Lock()
        self.failure: BaseException | None = None
        self.closed = False
        self.rows_written = 0
        self.fieldnames = None if self.FIELDNAMES is None else list(self.FIELDNAMES)
        try:
            # The CSV first: one already there (another program) stops
            # everything before a log is made.
            for path, encoding in ((self.csv_path, "utf-8-sig"), (self.log_path, "utf-8")):
                with path.open("x", encoding=encoding, newline=""):
                    pass
            if self.fieldnames is not None:
                with self.csv_path.open("a", newline="", encoding="utf-8-sig") as handle:
                    csv.DictWriter(handle, fieldnames=self.fieldnames).writeheader()
                    self._sync(handle)
            if settings is not None:
                self.event("run_prepared", **self._prepared_details(name, settings))
                failure = self.failure
                if failure is not None:
                    self.close("not_started", error=str(failure))
                    raise failure
        except BaseException:
            # The folder and any file made stay, as evidence; nothing starts.
            self.closed = True
            raise

    def _default_stem(self) -> str:
        return f"{self.page}_{time.strftime('%Y%m%d_%H%M%S')}"

    def _prepared_details(self, name: str, settings: dict) -> dict:
        """run_prepared's fields; the page's own settings stay under "settings"
        so that none of them can replace the timestamp or the event name."""
        return dict(program=self.PROGRAM_NAME, app_version=self.APPLICATION_VERSION, python_version=sys.version,
                    file_name=name, run_folder=str(self.directory), csv_path=str(self.csv_path),
                    log_path=str(self.log_path), settings=settings)

    @staticmethod
    def _sync(handle) -> None:
        handle.flush()
        os.fsync(handle.fileno())

    def _append(self, text: str) -> None:
        """One record onto the log, opened for it and closed again."""
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(text)
            self._sync(handle)

    def event(self, name: str, /, **details) -> bool:
        """Write one record, from either thread; False when it was not
        written (the log closed, or the write failed: then kept for check())."""
        with self.lock:
            if self.closed:
                return False
            try:
                self._append(self._format_log(name, details))
                return True
            except Exception as error:
                if self.failure is None:
                    self.failure = error
                return False

    def note(self, text: str) -> bool:
        """A page log line of the running scan, as a "note" record."""
        return self.event("note", text=str(text))

    def check(self) -> None:
        """On the worker, between instrument steps: a failed write ends the scan."""
        error = self.failure
        if error is not None:
            raise RuntimeError(f"The {self.label} log could not be written ({error}); the scan stopped") from error

    def append_row(self, row: dict) -> None:
        """One row onto the live CSV, opened for it and closed again, flushed
        and fsynced before it returns.  The first row's keys are the header.
        A later row's missing cells are left blank; a key the header lacks
        raises before anything is written, so the columns never shift.  A
        failure raises, to end the scan through the page's failure path."""
        with self.lock:
            if self.closed:
                raise RuntimeError(f"The {self.label} live CSV is closed")
            first = self.fieldnames is None
            fields = list(row) if first else self.fieldnames
            known = set(fields)
            extra = [str(key) for key in row if key not in known]
            if extra:
                raise ValueError(f"The {self.label} live CSV has no column for {', '.join(extra)}; the row was not "
                                 "written, so that the columns do not shift")
            with self.csv_path.open("a", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, restval="")
                if first:
                    writer.writeheader()
                writer.writerow(row)
                self._sync(handle)
            self.fieldnames = fields
            self.rows_written += 1

    def write_header(self, fieldnames) -> None:
        """The live CSV's header now, before any row: for a page whose run
        must show its columns even when it stops before its first point
        (Gate-VI's summary, as its two other CSVs; review, 2026-10-18).
        Later rows keep these columns (append_row).  Does nothing once a
        header is there; a failure raises, to end the scan."""
        with self.lock:
            if self.closed:
                raise RuntimeError(f"The {self.label} live CSV is closed")
            if self.fieldnames is not None:
                return
            fields = [str(name) for name in fieldnames]
            with self.csv_path.open("a", newline="", encoding="utf-8-sig") as handle:
                csv.DictWriter(handle, fieldnames=fields).writeheader()
                self._sync(handle)
            self.fieldnames = fields

    def close(self, outcome: str, /, **details) -> list[str]:
        """run_finished, then closed for good; best effort, once (the later
        calls do nothing).  The errors are returned for the page to show."""
        with self.lock:
            if self.closed:
                return []
            self.closed = True
            try:
                self._append(self._format_log("run_finished", dict(outcome=outcome, **details)))
            except Exception as error:
                return [f"Failed to write the closing log entry: {error}"]
            return []



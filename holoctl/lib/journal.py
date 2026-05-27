"""Append-safe JSONL journal of session/tool events.

The journal lives at ``.holoctl/journal/<YYYY-MM-DD>.jsonl`` — one file per
day, one JSON object per line:

    {"ts": "2026-05-07T13:42:18Z", "source": "claude", "kind": "tool_use",
     "payload": {"tool": "Edit", "file": "src/api/auth.py"}}

The journal is the **input** for the curator. Hooks emitted by the Claude
compiler (`SessionStart`, `Stop`, `PostToolUse`, `PreToolUse`) call
``hctl journal record`` with a small payload — see
``holoctl/templates/hooks/``.

Writes are append-safe under concurrent processes via OS-level locking:
``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows. We keep the
critical section as small as possible (one open / lock / write / unlock /
close per record) so the lock window is microseconds even when two
assistants are writing at once.

This module is import-cheap (no I/O at import time) so it can be loaded
on hot CLI paths like ``hctl boot`` without slowing things down.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# Per-process lock — serializes threads in the same Python process.
# Cross-process serialization is handled by msvcrt.locking / fcntl.flock below.
_PROCESS_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _today_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"


@contextmanager
def _locked_append(path: Path) -> Iterator:
    """Open `path` in append mode under an OS-level exclusive lock.

    Released on context exit. On platforms that don't support flock-style
    locking (rare), this degrades to a plain append (still atomic at the
    OS level for small writes <PIPE_BUF, which our records are).

    Windows: retries non-blocking lock with exponential backoff up to ~1s.
    Real-world contention is microseconds; the backoff is just defense.
    """
    import time
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize threads in this process before touching the OS-level lock.
    # This avoids msvcrt.locking conflicts between threads sharing the same
    # process (which gets confused by multiple handles on the same byte range).
    _PROCESS_LOCK.acquire()
    f = open(path, "a", encoding="utf-8")
    _have_lock = False
    try:
        if sys.platform == "win32":
            try:
                import msvcrt
                deadline = time.monotonic() + 2.0
                wait = 0.001
                while time.monotonic() < deadline:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        _have_lock = True
                        break
                    except OSError:
                        time.sleep(wait)
                        wait = min(wait * 2, 0.05)
            except ImportError:
                pass
        else:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                _have_lock = True
            except (OSError, ImportError):
                _have_lock = False
        yield f
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
        if _have_lock:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        f.close()
        _PROCESS_LOCK.release()


class Journal:
    """Reader/writer over ``.holoctl/journal/``."""

    def __init__(self, project_root: Path):
        self.root = Path(project_root)
        self.dir = self.root / ".holoctl" / "journal"

    @property
    def today_path(self) -> Path:
        return self.dir / _today_filename()

    def record(
        self,
        kind: str,
        source: str = "manual",
        payload: dict[str, Any] | None = None,
        ts: str | None = None,
    ) -> dict:
        record = {
            "ts": ts or _now_iso(),
            "source": source,
            "kind": kind,
            "payload": payload or {},
        }
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
        with _locked_append(self.today_path) as f:
            f.write(line)
        return record

    def iter_records(
        self,
        *,
        since: str | None = None,
        kind: str | None = None,
        source: str | None = None,
    ) -> Iterator[dict]:
        """Yield records, newest first within each day, day-by-day descending.

        ``since`` is an ISO timestamp; records older than that are skipped.
        """
        if not self.dir.exists():
            return
        files = sorted(self.dir.glob("*.jsonl"), reverse=True)
        for f in files:
            day_records: list[dict] = []
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    for raw in fh:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            r = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if kind and r.get("kind") != kind:
                            continue
                        if source and r.get("source") != source:
                            continue
                        if since and r.get("ts", "") < since:
                            continue
                        day_records.append(r)
            except OSError:
                continue
            for r in reversed(day_records):
                yield r

    def recent(
        self,
        *,
        limit: int = 50,
        since: str | None = None,
        kind: str | None = None,
        source: str | None = None,
    ) -> list[dict]:
        out: list[dict] = []
        for r in self.iter_records(since=since, kind=kind, source=source):
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def count_by_kind(self, *, since: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.iter_records(since=since):
            k = r.get("kind", "unknown")
            counts[k] = counts.get(k, 0) + 1
        return counts

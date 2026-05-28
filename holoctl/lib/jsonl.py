"""Shared append-safe JSONL writer.

Both the event journal (``.holoctl/journal/<date>.jsonl``) and the board
activity log (``.holoctl/activity.jsonl``) are append-only JSONL files that
can be written concurrently by more than one assistant/process. They keep
separate files on purpose — different schemas and different consumers (the
journal feeds the curator + ``hctl journal``; the activity log feeds the
dashboard's per-ticket timeline) — but they MUST share the same locked-append
primitive so neither can interleave a half-written line.

Writes serialize on a per-process threading lock first, then take an OS-level
exclusive lock (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows). The
critical section is one open/lock/write/unlock/close per record, so the lock
window is microseconds even under contention.
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Per-process lock — serializes threads in the same Python process.
# Cross-process serialization is handled by msvcrt.locking / fcntl.flock below.
_PROCESS_LOCK = threading.Lock()


@contextmanager
def locked_append(path: Path) -> Iterator:
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


def append_jsonl_line(path: Path, line: str) -> None:
    """Append one pre-serialized JSONL line (incl. trailing newline) under lock."""
    with locked_append(path) as f:
        f.write(line)

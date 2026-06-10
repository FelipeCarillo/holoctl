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

The same OS-level locking primitive is exposed as :func:`file_lock` for callers
(e.g. the board) that need to guard a read→mutate→write critical section on a
separate sidecar lock file rather than appending to a JSONL.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Per-process lock — serializes threads in the same Python process.
# Cross-process serialization is handled by msvcrt.locking / fcntl.flock below.
_PROCESS_LOCK = threading.Lock()

# Default Windows non-blocking lock timeout (seconds). Overridable via the
# ``HOLOCTL_LOCK_TIMEOUT`` environment variable.
_DEFAULT_LOCK_TIMEOUT = 2.0


def _lock_timeout() -> float:
    """Windows lock acquisition deadline in seconds.

    Reads ``HOLOCTL_LOCK_TIMEOUT`` each call so tests / operators can tune it
    without re-importing. Falls back to the historical 2.0s on absent/garbage
    values.
    """
    raw = os.environ.get("HOLOCTL_LOCK_TIMEOUT")
    if not raw:
        return _DEFAULT_LOCK_TIMEOUT
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_LOCK_TIMEOUT
    return val if val > 0 else _DEFAULT_LOCK_TIMEOUT


def _os_lock(f) -> bool:
    """Acquire an OS-level exclusive lock on an open file. Returns True if held."""
    import time

    if sys.platform == "win32":
        try:
            import msvcrt
        except ImportError:
            return False
        deadline = time.monotonic() + _lock_timeout()
        wait = 0.001
        while time.monotonic() < deadline:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                time.sleep(wait)
                wait = min(wait * 2, 0.05)
        return False
    try:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        return True
    except (OSError, ImportError):
        return False


def _os_unlock(f) -> None:
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


@contextmanager
def locked_append(path: Path) -> Iterator:
    """Open `path` in append mode under an OS-level exclusive lock.

    Released on context exit. On platforms that don't support flock-style
    locking (rare), this degrades to a plain append (still atomic at the
    OS level for small writes <PIPE_BUF, which our records are).

    Windows: retries non-blocking lock with exponential backoff up to the
    configured ``HOLOCTL_LOCK_TIMEOUT`` (default ~2s). Real-world contention is
    microseconds; the backoff is just defense.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize threads in this process before touching the OS-level lock.
    # This avoids msvcrt.locking conflicts between threads sharing the same
    # process (which gets confused by multiple handles on the same byte range).
    _PROCESS_LOCK.acquire()
    f = open(path, "a", encoding="utf-8")
    _have_lock = False
    try:
        _have_lock = _os_lock(f)
        yield f
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
        if _have_lock:
            _os_unlock(f)
    finally:
        f.close()
        _PROCESS_LOCK.release()


@contextmanager
def file_lock(lock_path: Path) -> Iterator:
    """Hold an exclusive cross-process lock on a dedicated sidecar lock file.

    Unlike :func:`locked_append`, this does not write to the file — it exists
    purely to guard a critical section (e.g. the board's
    read→mutate→atomic-write window) against concurrent CLI + MCP-server
    writers. The lock file is created if absent and left in place between runs.

    Serializes same-process threads on ``_PROCESS_LOCK`` first (so a single
    process never races itself on the OS lock), then takes the OS-level
    exclusive lock. Released on context exit.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _PROCESS_LOCK.acquire()
    # `a+` so we never truncate; the file's contents are irrelevant.
    f = open(lock_path, "a+", encoding="utf-8")
    _have_lock = False
    try:
        _have_lock = _os_lock(f)
        if not _have_lock:
            # Proceeding without the OS lock reopens the last-write-wins window
            # this lock exists to close — callers' mutations may clobber a
            # concurrent writer. Unlike locked_append (where an unlocked small
            # append is still atomic), here silence would hide real corruption
            # risk, so make the degradation observable.
            logging.getLogger(__name__).warning(
                "file_lock: could not acquire OS lock on %s (timeout %.1fs); "
                "proceeding without cross-process serialization — a concurrent "
                "writer may clobber this mutation",
                lock_path,
                _lock_timeout(),
            )
        yield
        if _have_lock:
            _os_unlock(f)
    finally:
        f.close()
        _PROCESS_LOCK.release()


def append_jsonl_line(path: Path, line: str) -> None:
    """Append one pre-serialized JSONL line (incl. trailing newline) under lock."""
    with locked_append(path) as f:
        f.write(line)

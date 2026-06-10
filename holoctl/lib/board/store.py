"""Board index persistence: load / save / cache / lock / rebuild.

``BoardIndexStore`` is a mixin — :class:`holoctl.lib.board.Board` inherits it
and supplies ``_root`` / ``_board_dir`` / ``_index_path`` / ``_lock_path``
from its constructor (split out of the former board.py god module, item 5.3).
Also home to the activity-log appender. Invariants:

- **Source of truth**: the per-ticket ``.md`` files. ``index.json`` is a
  denormalized projection — ``rebuild_index()`` regenerates it from the
  markdown, so a lost or corrupt index is recoverable by design.
- **Cache key contract**: ``_INDEX_CACHE`` maps the resolved index path to
  ``(mtime_ns, size, data)``. ``_load()`` re-stats on every read and serves
  the cached object only when BOTH mtime_ns and size match.
- **Torn-read defense**: ``_save()`` stages to a same-directory temp file,
  fsyncs, then ``os.replace``s — atomic on POSIX and Windows. The replace
  changes the file's stat, so the revalidation above guarantees a reader
  sees either the old projection or the new one, never a mix or a stale hit.
- **Lock ordering**: mutators must hold ``_locked()`` (the cross-process
  ``index.json.lock``) across the entire load→mutate→save window, and must
  mutate a ``_load_mut()`` deep copy — a published cache entry is never
  mutated in place. Plain readers (``_load()``) take no lock.
"""
from __future__ import annotations

import copy
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..jsonl import file_lock
from ..markdown import parse_frontmatter
from ..ticket import Ticket
from .markdown_sync import _count_acceptance
from .validate import _normalize_array

# Process-wide cache of parsed index.json, keyed by absolute index path.
# Each entry is (mtime_ns, size, data). Validated on every read against the
# file's current stat so a concurrent writer (which calls os.replace, changing
# mtime/size) is never served a stale or torn projection. Invalidated on save.
#
# Unbounded by design: one entry per board ever touched by this process, and a
# parsed index is small (tens of KB for hundreds of tickets). The CLI sees one
# board; the dashboard sees one per registered project. Revisit with an
# eviction policy only if holoctl grows a long-running multi-tenant server.
_INDEX_CACHE: dict[str, tuple[int, int, dict]] = {}


def _replace_with_retry(src: str, dst: "Path | str", attempts: int = 20) -> None:
    """``os.replace`` with a short bounded retry for Windows.

    On Windows, replacing a file that a concurrent reader currently holds
    open fails with ``PermissionError`` (WinError 5) — readers like the
    dashboard SSE poller or another CLI's ``_load()`` only hold the index
    open for the duration of a single ``read_text``, so a few millisecond
    retries are enough. POSIX renames never take this path.
    """
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.005 * (attempt + 1))


def _now() -> str:
    """ISO 8601 UTC timestamp with `Z` suffix, e.g. `2026-05-06T13:42:18Z`.

    Used for `created`, `updated`, `completed`, and the activity log.
    Older tickets that still have date-only values (`2026-05-04`) are read
    transparently — `datetime.fromisoformat` accepts both forms in 3.11+.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log_activity(project_root: Path, event: dict) -> None:
    """Append a board mutation to ``.holoctl/activity.jsonl``.

    This is a *separate* store from the event journal (``.holoctl/journal/``):
    it has a ticket-scoped schema (``{ts, type, ticket, ...}``) and feeds the
    dashboard's per-ticket activity timeline, whereas the journal has a
    session-event schema and feeds the curator. They share the same locked
    append primitive so neither interleaves a half-written line under
    concurrent writers.
    """
    from ..jsonl import append_jsonl_line
    log_path = project_root / ".holoctl" / "activity.jsonl"
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), **event}
    # `ensure_ascii=False`: payloads may carry the ticket title/agent name,
    # which can contain pt-BR accents. Match the journal writer's policy
    # (see `lib/journal.py`).
    append_jsonl_line(log_path, json.dumps(entry, ensure_ascii=False) + "\n")


class BoardIndexStore:
    """Index I/O mixin: cross-process lock, cached load, atomic save, rebuild."""

    # Supplied by Board.__init__ (see holoctl/lib/board/__init__.py).
    _root: Path
    _config: dict
    _board_dir: Path
    _index_path: Path
    _tickets_dir: Path
    _lock_path: Path

    @contextmanager
    def _locked(self):
        """Hold the board's cross-process lock for a mutation critical section.

        Serializes concurrent CLI + MCP-server writers so a load→mutate→save
        window is not last-write-wins. Reuses the OS-level locking primitive
        from ``lib.jsonl``.
        """
        self._board_dir.mkdir(parents=True, exist_ok=True)
        with file_lock(self._lock_path):
            yield

    def _cache_key(self) -> str:
        return str(self._index_path.resolve())

    def _load(self) -> dict:
        # Reader-side mirror of `_replace_with_retry`: on Windows, opening the
        # index while a concurrent writer's os.replace is in flight fails with
        # a transient PermissionError (sharing violation). Retry briefly so
        # unlocked readers (dashboard GETs, CLI list) don't surface a 500 /
        # crash for a millisecond-scale race; a *persistent* error (real ACL
        # problem) still raises after the bounded attempts.
        attempts = 20
        for attempt in range(attempts):
            if not self._index_path.exists():
                return {
                    "meta": {"version": 1, "updated": _now(), "nextId": 1, "counts": {}},
                    "tickets": [],
                }
            # In-memory cache keyed by (path, mtime_ns, size). We re-stat on
            # every read and only serve the cached object when both mtime AND
            # size match, so a concurrent writer's os.replace (which changes
            # the inode's stat) always forces a fresh parse — never a torn read.
            key = self._cache_key()
            try:
                st = self._index_path.stat()
                cached = _INDEX_CACHE.get(key)
                if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
                    return cached[2]
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.005 * (attempt + 1))
                continue
            except FileNotFoundError:
                # Deleted/replaced between exists() and open — re-evaluate from
                # the top (next iteration returns the empty default if gone).
                continue
            _INDEX_CACHE[key] = (st.st_mtime_ns, st.st_size, data)
            return data
        raise PermissionError(f"could not read {self._index_path} after {attempts} attempts")

    def _load_mut(self) -> dict:
        """Deep copy of the index for a mutation critical section.

        ``_load()`` returns the SHARED cached object — concurrent readers in
        other threads (e.g. dashboard GET handlers in FastAPI's threadpool)
        may be iterating it at any moment. Mutators therefore work on a
        private deep copy and republish it via ``_save``; a published cache
        entry is never mutated in place, so a reader can never observe a
        half-applied mutation (or a list resized mid-iteration). Callers of
        mutators must still treat returned ticket rows as read-only — they
        alias the freshly published object.
        """
        return copy.deepcopy(self._load())

    def _save(self, data: dict) -> None:
        self._board_dir.mkdir(parents=True, exist_ok=True)
        # `ensure_ascii=False` keeps accented titles (e.g. "métricas — fase 1")
        # readable in the on-disk index.json and in anything that surfaces the
        # raw JSON (SSE payload, MCP responses, `git diff`). Default would
        # escape every non-ASCII codepoint to `\uXXXX` — functional, but
        # mojibake when a consumer prints the raw bytes without decoding.
        payload = json.dumps(data, indent="\t", ensure_ascii=False) + "\n"
        # Atomic write: stage to a temp file in the same directory, fsync, then
        # os.replace (atomic rename on POSIX & Windows). A reader either sees
        # the old file or the new one — never a half-written index.
        key = self._cache_key()
        # Invalidate the cache first so a crash between replace and the cache
        # update below can't leave a stale entry that outlives the file.
        _INDEX_CACHE.pop(key, None)
        fd, tmp_name = self._mk_tempfile()
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            _replace_with_retry(tmp_name, self._index_path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        # Refresh the cache to the just-written object so the immediately
        # following _load() in the same call is a cache hit (validated by stat).
        try:
            st = self._index_path.stat()
            _INDEX_CACHE[key] = (st.st_mtime_ns, st.st_size, data)
        except OSError:
            pass

    def _mk_tempfile(self) -> tuple[int, str]:
        import tempfile

        return tempfile.mkstemp(
            dir=str(self._board_dir), prefix=".index.", suffix=".tmp"
        )

    def _recount(self, tickets: list[Ticket]) -> dict:
        counts: dict = {s: 0 for s in self._config["board"]["statuses"]}
        for t in tickets:
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        return counts

    def rebuild_index(self) -> dict:
        self._tickets_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self._tickets_dir.glob("*.md"))
        tickets: list[Ticket] = []
        now = _now()

        for f in files:
            if f.name.startswith("_"):
                continue
            data_fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
            if not data_fm.get("id"):
                continue
            # Migration: legacy `scope: "X"` → `projects: ["X"]`.
            projects_fm = data_fm.get("projects")
            if projects_fm is None and data_fm.get("scope"):
                projects_fm = data_fm["scope"]

            acc_total, acc_done = _count_acceptance(body)

            def _scalar(v):
                return v if v not in (None, "null", "") else None
            tickets.append({
                "id": data_fm["id"],
                "title": data_fm.get("title", ""),
                "kind": data_fm.get("kind") or "task",
                "parent": _scalar(data_fm.get("parent")),
                "source_provider": _scalar(data_fm.get("source_provider")),
                "source_ref": _scalar(data_fm.get("source_ref")),
                "source_url": _scalar(data_fm.get("source_url")),
                "source_label": _scalar(data_fm.get("source_label")),
                "agent": _normalize_array(data_fm.get("agent")),
                "files": _normalize_array(data_fm.get("files")),
                "projects": _normalize_array(projects_fm),
                "status": data_fm.get("status", "backlog"),
                "priority": data_fm.get("priority", "p2"),
                "sprint": data_fm.get("sprint"),
                "created": data_fm.get("created", now),
                "updated": data_fm.get("updated", now),
                "completed": data_fm.get("completed"),
                "depends": _normalize_array(data_fm.get("depends")),
                "tags": _normalize_array(data_fm.get("tags")),
                # Denormalized DoD progress, recomputed from the .md body.
                "acceptance_total": acc_total,
                "acceptance_done": acc_done,
                "file": f"tickets/{f.name}",
            })

        tickets.sort(key=lambda t: int(t["id"].split("-")[-1]))
        max_num = max((int(t["id"].split("-")[-1]) for t in tickets), default=0)

        index = {
            "meta": {
                "version": 1,
                "updated": now,
                "nextId": max_num + 1,
                "counts": self._recount(tickets),
            },
            "tickets": tickets,
        }
        with self._locked():
            self._save(index)
        return {"ticketCount": len(tickets), "nextId": max_num + 1}

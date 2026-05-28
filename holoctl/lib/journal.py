"""Append-safe JSONL journal of session/tool events.

The journal lives at ``.holoctl/journal/<YYYY-MM-DD>.jsonl`` — one file per
day, one JSON object per line:

    {"ts": "2026-05-07T13:42:18Z", "source": "claude", "kind": "tool_use",
     "payload": {"tool": "Edit", "file": "src/api/auth.py"}}

The journal is the **input** for the curator. Hooks emitted by the Claude
compiler (`SessionStart`, `Stop`, `PostToolUse`, `PreToolUse`) call
``hctl journal record`` with a small payload — see
``holoctl/templates/hooks/``.

Writes are append-safe under concurrent processes via the shared
``lib.jsonl.append_jsonl_line`` primitive (OS-level ``fcntl.flock`` /
``msvcrt.locking``), the same one the board's activity log uses.

This module is import-cheap (no I/O at import time) so it can be loaded
on hot CLI paths like ``hctl boot`` without slowing things down.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .jsonl import append_jsonl_line


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _today_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"


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
        append_jsonl_line(self.today_path, line)
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

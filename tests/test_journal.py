"""Tests for holoctl.lib.journal — append-safe JSONL session events."""
from __future__ import annotations

import json
import threading
from pathlib import Path


from holoctl.lib.journal import Journal


def test_record_creates_today_file(tmp_path: Path):
    j = Journal(tmp_path)
    j.record("session_start", source="claude")
    assert j.today_path.exists()
    line = j.today_path.read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["kind"] == "session_start"
    assert rec["source"] == "claude"


def test_record_appends_multiple(tmp_path: Path):
    j = Journal(tmp_path)
    for i in range(5):
        j.record("tool_use", source="claude", payload={"i": i})
    lines = [l for l in j.today_path.read_text(encoding="utf-8").splitlines() if l]
    assert len(lines) == 5
    payloads = [json.loads(l)["payload"]["i"] for l in lines]
    assert payloads == [0, 1, 2, 3, 4]


def test_recent_returns_newest_first(tmp_path: Path):
    j = Journal(tmp_path)
    j.record("a", source="x")
    j.record("b", source="x")
    j.record("c", source="x")
    out = j.recent(limit=10)
    kinds = [r["kind"] for r in out]
    assert kinds == ["c", "b", "a"]


def test_recent_filters_by_kind(tmp_path: Path):
    j = Journal(tmp_path)
    j.record("a", source="x")
    j.record("b", source="x")
    j.record("a", source="x")
    out = j.recent(limit=10, kind="a")
    assert all(r["kind"] == "a" for r in out)
    assert len(out) == 2


def test_recent_filters_by_source(tmp_path: Path):
    j = Journal(tmp_path)
    j.record("k", source="claude")
    j.record("k", source="cursor")
    j.record("k", source="claude")
    out = j.recent(limit=10, source="cursor")
    assert all(r["source"] == "cursor" for r in out)
    assert len(out) == 1


def test_count_by_kind(tmp_path: Path):
    j = Journal(tmp_path)
    j.record("session_start", source="x")
    j.record("tool_use", source="x")
    j.record("tool_use", source="x")
    j.record("tool_use", source="x")
    j.record("stop", source="x")
    counts = j.count_by_kind()
    assert counts == {"session_start": 1, "tool_use": 3, "stop": 1}


def test_iter_records_handles_empty_lines(tmp_path: Path):
    j = Journal(tmp_path)
    j.record("a", source="x")
    j.today_path.write_text(
        j.today_path.read_text(encoding="utf-8") + "\n\n\n",
        encoding="utf-8",
    )
    out = list(j.iter_records())
    assert len(out) == 1


def test_iter_records_skips_malformed(tmp_path: Path):
    j = Journal(tmp_path)
    j.record("a", source="x")
    j.today_path.write_text(
        j.today_path.read_text(encoding="utf-8") + "{not json\n",
        encoding="utf-8",
    )
    out = list(j.iter_records())
    assert len(out) == 1


def test_concurrent_writes_do_not_corrupt(tmp_path: Path):
    """Threaded writes serialize via OS lock — every record lands intact."""
    j = Journal(tmp_path)
    N = 50

    def write(i: int):
        for k in range(N):
            j.record("tool_use", source="t", payload={"thread": i, "k": k})

    threads = [threading.Thread(target=write, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = [l for l in j.today_path.read_text(encoding="utf-8").splitlines() if l]
    assert len(lines) == N * 4
    parsed = [json.loads(l) for l in lines]
    seen = {(r["payload"]["thread"], r["payload"]["k"]) for r in parsed}
    assert len(seen) == N * 4


def test_no_records_yields_empty(tmp_path: Path):
    j = Journal(tmp_path)
    assert list(j.iter_records()) == []
    assert j.recent() == []
    assert j.count_by_kind() == {}

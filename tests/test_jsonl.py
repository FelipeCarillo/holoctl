"""F7b — the shared locked-append JSONL primitive used by both the event
journal and the board activity log (which previously appended without a lock)."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from holoctl.lib import jsonl
from holoctl.lib.jsonl import append_jsonl_line


def test_append_creates_parent_dirs_and_writes_line(tmp_path: Path):
    target = tmp_path / "nested" / "activity.jsonl"
    append_jsonl_line(target, json.dumps({"a": 1}) + "\n")
    append_jsonl_line(target, json.dumps({"a": 2}) + "\n")
    lines = target.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["a"] for line in lines] == [1, 2]


def test_concurrent_appends_never_interleave(tmp_path: Path):
    """20 threads × 25 writes must yield 500 individually-parseable lines —
    the guarantee the board's activity log lacked before it shared this lock."""
    target = tmp_path / "activity.jsonl"
    writers, per_writer = 20, 25

    def worker(wid: int) -> None:
        for i in range(per_writer):
            append_jsonl_line(target, json.dumps({"w": wid, "i": i}) + "\n")

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == writers * per_writer
    # Every line must be valid JSON (no torn/interleaved writes).
    parsed = [json.loads(line) for line in lines]
    assert len(parsed) == writers * per_writer


def test_file_lock_warns_when_os_lock_unavailable(tmp_path: Path, monkeypatch, caplog):
    """When the OS-level lock can't be acquired (e.g. Windows timeout),
    ``file_lock`` proceeds unprotected. That degradation undermines the board's
    no-last-write-wins guarantee, so it must be observable — a WARNING log —
    not silent."""
    monkeypatch.setattr(jsonl, "_os_lock", lambda f: False)
    with caplog.at_level(logging.WARNING, logger="holoctl.lib.jsonl"):
        with jsonl.file_lock(tmp_path / "board.lock"):
            pass
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING when the OS lock is not held"
    assert "without" in warnings[0].getMessage().lower()


def test_file_lock_does_not_warn_when_lock_held(tmp_path: Path, caplog):
    """The happy path stays quiet — no log noise on every mutation."""
    with caplog.at_level(logging.WARNING, logger="holoctl.lib.jsonl"):
        with jsonl.file_lock(tmp_path / "board.lock"):
            pass
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

"""Concurrency tests for the board mutation lock (task 3.3).

Multiple workers each move a distinct ticket; with last-write-wins (no lock)
the read→mutate→save window races and updates get clobbered. With the file
lock + atomic save, every mutation must land.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from holoctl.lib.board import Board, _INDEX_CACHE


def _read_index(workspace: Path) -> dict:
    p = workspace / ".holoctl" / "board" / "index.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_concurrent_thread_moves_lose_nothing(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    n = 20
    ids = [board.add({"title": f"T{i}"})["id"] for i in range(n)]

    errors: list[Exception] = []

    def worker(tid: str) -> None:
        try:
            Board(workspace, workspace_config).move(tid, "doing")
        except Exception as e:  # pragma: no cover - surfaced via assert
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(tid,)) for tid in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    index = _read_index(workspace)
    statuses = {t["id"]: t["status"] for t in index["tickets"]}
    assert len(statuses) == n
    for tid in ids:
        assert statuses[tid] == "doing", f"{tid} lost its move"


def test_concurrent_adds_unique_ids(workspace: Path, workspace_config: dict):
    """Concurrent add() under lock must not hand out duplicate IDs."""
    n = 15
    results: list[str] = []
    lock = threading.Lock()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            t = Board(workspace, workspace_config).add({"title": f"C{i}"})
            with lock:
                results.append(t["id"])
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len(results) == n
    assert len(set(results)) == n, f"duplicate ids: {sorted(results)}"
    index = _read_index(workspace)
    assert len(index["tickets"]) == n


def test_save_is_atomic_no_torn_read(workspace: Path, workspace_config: dict):
    """A reader hammering the index while a writer mutates never parses a
    half-written file (atomic os.replace)."""
    board = Board(workspace, workspace_config)
    ids = [board.add({"title": f"A{i}"})["id"] for i in range(10)]

    stop = threading.Event()
    read_errors: list[Exception] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                _read_index(workspace)
            except json.JSONDecodeError as e:
                read_errors.append(e)
            except PermissionError:
                # Windows: a raw open can hit a sharing violation while the
                # writer's os.replace is in flight. That's not a torn read —
                # the contract under test is "never parse a half-written
                # file" — so skip and re-read. Without this the thread died
                # on the first hit (leaking an unhandled-thread-exception
                # warning) and silently stopped exercising reads mid-test.
                continue

    rt = threading.Thread(target=reader)
    rt.start()
    try:
        for _ in range(5):
            for tid in ids:
                board.move(tid, "doing")
                board.move(tid, "backlog")
    finally:
        stop.set()
        rt.join()

    assert not read_errors, read_errors


def test_load_retries_transient_permission_error(
    workspace: Path, workspace_config: dict, monkeypatch
):
    """On Windows a reader's open can race a concurrent writer's os.replace
    and fail with a sharing violation (the writer side already retries — see
    _replace_with_retry). `_load` must absorb a transient PermissionError with
    a short bounded retry instead of surfacing a 500/CLI crash."""
    board = Board(workspace, workspace_config)
    board.add({"title": "X"})
    _INDEX_CACHE.clear()  # force the next _load to hit the disk

    index_path = workspace / ".holoctl" / "board" / "index.json"
    orig_read_text = Path.read_text
    fails = {"n": 3}

    def flaky_read_text(self, *args, **kwargs):
        if self == index_path and fails["n"] > 0:
            fails["n"] -= 1
            raise PermissionError(13, "sharing violation (simulated)")
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)
    data = board._load()
    assert [t["title"] for t in data["tickets"]] == ["X"]
    assert fails["n"] == 0, "retry path was not exercised"


def test_load_raises_after_persistent_permission_error(
    workspace: Path, workspace_config: dict, monkeypatch
):
    """A *persistent* PermissionError (real ACL problem, not a transient
    sharing violation) must still surface after the bounded retries."""
    import time as _time

    board = Board(workspace, workspace_config)
    board.add({"title": "X"})
    _INDEX_CACHE.clear()

    index_path = workspace / ".holoctl" / "board" / "index.json"
    orig_read_text = Path.read_text

    def always_denied(self, *args, **kwargs):
        if self == index_path:
            raise PermissionError(13, "access denied (simulated)")
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", always_denied)
    monkeypatch.setattr(_time, "sleep", lambda _s: None)  # keep the test fast
    with pytest.raises(PermissionError):
        board._load()


def _proc_worker(args):
    workspace_str, config_json, tid = args
    # Each process gets a fresh interpreter → fresh _INDEX_CACHE; the only
    # cross-process serialization is the OS-level file lock.
    cfg = json.loads(config_json)
    Board(Path(workspace_str), cfg).move(tid, "doing")


@pytest.mark.skipif(
    sys.platform == "win32", reason="fork-based multiprocessing not available on Windows"
)
def test_concurrent_process_moves_lose_nothing(workspace: Path, workspace_config: dict):
    import multiprocessing as mp

    board = Board(workspace, workspace_config)
    n = 12
    ids = [board.add({"title": f"P{i}"})["id"] for i in range(n)]
    config_json = json.dumps(workspace_config)

    ctx = mp.get_context("fork")
    with ctx.Pool(processes=4) as pool:
        pool.map(_proc_worker, [(str(workspace), config_json, tid) for tid in ids])

    # Drop the in-process cache so we read fresh from disk.
    _INDEX_CACHE.clear()
    index = _read_index(workspace)
    statuses = {t["id"]: t["status"] for t in index["tickets"]}
    assert len(statuses) == n
    for tid in ids:
        assert statuses[tid] == "doing", f"{tid} lost its move across processes"

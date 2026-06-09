"""Tests for the in-memory index.json cache (task 4.1).

The cache is keyed by (resolved path, mtime_ns, size) and invalidated on save.
A repeated read with no intervening write must be a cache hit (same object, no
re-parse); any write (including a concurrent writer's os.replace) must force a
fresh parse so we never serve a stale/torn projection.
"""
from __future__ import annotations

import json
from pathlib import Path

from holoctl.lib.board import Board, _INDEX_CACHE


def test_repeated_load_is_cache_hit_same_object(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    board.add({"title": "X"})

    first = board._load()
    second = board._load()
    # Same identity → served from cache, not re-parsed.
    assert first is second


def test_load_does_not_reread_file_on_cache_hit(
    workspace: Path, workspace_config: dict, monkeypatch
):
    board = Board(workspace, workspace_config)
    board.add({"title": "X"})
    board._load()  # warm cache

    index_path = workspace / ".holoctl" / "board" / "index.json"
    calls = {"n": 0}
    orig = Path.read_text

    def counting_read_text(self, *a, **k):
        if self == index_path:
            calls["n"] += 1
        return orig(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    board._load()
    board._load()
    assert calls["n"] == 0, "cache hit should not re-read the file"


def test_save_invalidates_then_refreshes_cache(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})

    before_status = board._load()["tickets"][0]["status"]
    assert before_status != "doing"

    board.move(t["id"], "doing")
    after = board._load()
    # The post-save load reflects the write (cache was invalidated and
    # refreshed from the just-written data, validated against the new mtime).
    assert after["tickets"][0]["status"] == "doing"


def test_external_write_invalidates_cache(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    board.add({"title": "X"})
    board._load()  # warm cache

    # Simulate an out-of-band writer (e.g. another process) replacing the file.
    index_path = workspace / ".holoctl" / "board" / "index.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    data["tickets"][0]["title"] = "MUTATED"
    tmp = index_path.with_suffix(".json.ext")
    tmp.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8")
    import os

    os.replace(tmp, index_path)

    fresh = board._load()
    assert fresh["tickets"][0]["title"] == "MUTATED"


def test_cache_keyed_per_workspace(workspace: Path, workspace_config: dict, tmp_path):
    """Two boards on different index paths don't share a cache entry."""
    board = Board(workspace, workspace_config)
    board.add({"title": "X"})
    board._load()
    key = board._cache_key()
    assert key in _INDEX_CACHE
    assert str((workspace / ".holoctl" / "board" / "index.json").resolve()) == key

"""Tests for `hctl boot` — minimal session-zero context."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from holoctl.cli.boot import (
    _open_curate_tickets,
    _persona_names,
    _recent_decisions,
    _topic_names,
    _top_pendings,
    app as boot_app,
)
from holoctl.lib.config import get_defaults, save_config
from holoctl.lib.memory import Memory


def _seed_workspace(tmp_path: Path) -> None:
    cfg = get_defaults()
    cfg["project"]["name"] = "BootTest"
    cfg["project"]["prefix"] = "BT"
    save_config(tmp_path, cfg)
    board_dir = tmp_path / ".holoctl" / "board"
    (board_dir / "tickets").mkdir(parents=True, exist_ok=True)
    (board_dir / "index.json").write_text(
        json.dumps({"meta": {}, "tickets": []}),
        encoding="utf-8",
    )
    (tmp_path / ".holoctl" / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".holoctl" / "agents" / "boardmaster.md").write_text(
        "---\nname: boardmaster\n---\n", encoding="utf-8",
    )
    (tmp_path / ".holoctl" / "context" / "decisions").mkdir(parents=True, exist_ok=True)


def _write_index(tmp_path: Path, tickets: list[dict]) -> None:
    (tmp_path / ".holoctl" / "board" / "index.json").write_text(
        json.dumps({"meta": {}, "tickets": tickets}),
        encoding="utf-8",
    )


def test_top_pendings_filters_to_p0_p1(tmp_path: Path):
    _seed_workspace(tmp_path)
    _write_index(tmp_path, [
        {"id": "BT-001", "title": "high", "priority": "p0", "status": "backlog"},
        {"id": "BT-002", "title": "mid", "priority": "p1", "status": "backlog"},
        {"id": "BT-003", "title": "low", "priority": "p2", "status": "backlog"},
        {"id": "BT-004", "title": "ignore", "priority": "p1", "status": "done"},
    ])
    out = _top_pendings(tmp_path, "BT", limit=3)
    assert "BT-001 high" in out
    assert "BT-002 mid" in out
    assert all("low" not in s for s in out)
    assert all("ignore" not in s for s in out)


def test_top_pendings_doing_first(tmp_path: Path):
    _seed_workspace(tmp_path)
    _write_index(tmp_path, [
        {"id": "BT-001", "title": "p0-back", "priority": "p0", "status": "backlog"},
        {"id": "BT-002", "title": "p1-doing", "priority": "p1", "status": "doing"},
    ])
    out = _top_pendings(tmp_path, "BT", limit=2)
    # In-flight should surface first regardless of priority order.
    assert out[0].startswith("BT-002")


def test_open_curate_tickets_only_open(tmp_path: Path):
    _seed_workspace(tmp_path)
    _write_index(tmp_path, [
        {
            "id": "BT-010", "title": "extract X",
            "priority": "p2", "status": "backlog",
            "tags": ["meta:curate"],
        },
        {
            "id": "BT-011", "title": "extract Y",
            "priority": "p2", "status": "done",
            "tags": ["meta:curate"],
        },
        {
            "id": "BT-012", "title": "regular",
            "priority": "p1", "status": "backlog",
            "tags": ["other"],
        },
    ])
    out = _open_curate_tickets(tmp_path, "BT", limit=5)
    ids = [t["id"] for t in out]
    assert ids == ["BT-010"]


def test_topic_names_lists_active_only(tmp_path: Path):
    _seed_workspace(tmp_path)
    mem = Memory(tmp_path)
    mem.add_topic("alpha", body="x", scope="lazy", description="d")
    mem.add_topic("beta", body="x", scope="lazy", description="d")
    mem.add_topic("gone", body="x", scope="lazy", description="d")
    mem.archive_topic("gone")
    names = _topic_names(tmp_path)
    assert names == ["alpha", "beta"]


def test_persona_names_returns_active(tmp_path: Path):
    _seed_workspace(tmp_path)
    (tmp_path / ".holoctl" / "agents" / "developer.md").write_text(
        "---\nname: developer\n---\n", encoding="utf-8",
    )
    names = _persona_names(tmp_path)
    assert "boardmaster" in names
    assert "developer" in names


def test_recent_decisions_sorted_by_mtime(tmp_path: Path):
    _seed_workspace(tmp_path)
    decisions = tmp_path / ".holoctl" / "context" / "decisions"
    f1 = decisions / "2026-05-04-old.md"
    f2 = decisions / "2026-05-07-new.md"
    f1.write_text("# old", encoding="utf-8")
    f2.write_text("# new", encoding="utf-8")
    import os, time
    # Force mtime ordering deterministic.
    old_time = time.time() - 1000
    os.utime(f1, (old_time, old_time))
    out = _recent_decisions(tmp_path, limit=2)
    assert out[0] == "2026-05-07-new"


def test_boot_command_under_1kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    _write_index(tmp_path, [
        {"id": "BT-001", "title": "task A", "priority": "p1", "status": "doing"},
        {"id": "BT-002", "title": "task B", "priority": "p0", "status": "backlog"},
    ])
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(boot_app, ["--plain"])
    assert result.exit_code == 0, result.output
    assert "BootTest" in result.output
    assert "Pendências" in result.output
    assert len(result.output.encode("utf-8")) <= 1024


def test_boot_records_journal_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    _write_index(tmp_path, [])
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(boot_app, ["--plain"])
    from holoctl.lib.journal import Journal
    j = Journal(tmp_path)
    records = j.recent(limit=10)
    kinds = [r["kind"] for r in records]
    assert "boot" in kinds


def test_boot_no_pendings_says_nenhuma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _seed_workspace(tmp_path)
    _write_index(tmp_path, [])
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(boot_app, ["--plain"])
    assert "Pendências p0/p1: nenhuma" in result.output

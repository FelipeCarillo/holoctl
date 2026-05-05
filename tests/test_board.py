"""Tests for holoctl.lib.board — ticket CRUD + scope→projects migration."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from holoctl.lib.board import Board


def test_add_creates_ticket_with_id_and_md_file(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    ticket = board.add({"title": "First", "agent": "developer"})
    assert ticket["id"] == "TST-001"
    assert ticket["title"] == "First"
    assert ticket["agent"] == ["developer"]
    md_path = workspace / ".holoctl" / "board" / ticket["file"]
    assert md_path.exists()
    assert "id: TST-001" in md_path.read_text(encoding="utf-8")


def test_add_increments_id(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    a = board.add({"title": "A"})
    b = board.add({"title": "B"})
    c = board.add({"title": "C"})
    assert (a["id"], b["id"], c["id"]) == ("TST-001", "TST-002", "TST-003")
    assert board.next_id() == "TST-004"


def test_add_accepts_projects_array(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "projects": ["app", "api"]})
    assert t["projects"] == ["app", "api"]
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "projects: app, api" in md


def test_add_accepts_legacy_scope_string(workspace: Path, workspace_config: dict):
    """A patch with legacy `scope: backend` becomes `projects: ['backend']`."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "Legacy", "scope": "backend"})
    assert t["projects"] == ["backend"]
    assert "scope" not in t or t.get("scope") in (None, "")


def test_add_default_projects_is_empty(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "Workspace-wide"})
    assert t["projects"] == []


def test_ls_filter_by_status(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    board.add({"title": "A"})
    board.add({"title": "B"})
    second = board.add({"title": "C"})
    board.move(second["id"], "doing")
    backlog = board.ls({"status": "backlog"})
    doing = board.ls({"status": "doing"})
    assert len(backlog) == 2
    assert len(doing) == 1
    assert doing[0]["id"] == second["id"]


def test_ls_filter_by_project(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    board.add({"title": "A", "projects": ["app"]})
    board.add({"title": "B", "projects": ["api"]})
    board.add({"title": "C", "projects": ["app", "api"]})
    in_app = board.ls({"project": "app"})
    in_api = board.ls({"project": "api"})
    assert sorted(t["title"] for t in in_app) == ["A", "C"]
    assert sorted(t["title"] for t in in_api) == ["B", "C"]


def test_move_updates_status_and_md(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    result = board.move(t["id"], "doing")
    assert result == {"id": t["id"], "from": "backlog", "to": "doing"}
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "status: doing" in md


def test_move_to_done_sets_completed(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.move(t["id"], "done")
    fresh = board.get(t["id"])
    assert fresh["status"] == "done"
    assert fresh["completed"] is not None


def test_move_to_invalid_status_raises(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    with pytest.raises(ValueError):
        board.move(t["id"], "bogus")


def test_set_field_updates_index_and_md(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.set(t["id"], "priority", "p0")
    fresh = board.get(t["id"])
    assert fresh["priority"] == "p0"


def test_set_rejects_unknown_field(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    with pytest.raises(ValueError):
        board.set(t["id"], "secret_admin_flag", "true")


def test_stat_counts_by_status(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    a = board.add({"title": "A"})
    b = board.add({"title": "B"})
    board.add({"title": "C"})
    board.move(a["id"], "doing")
    board.move(b["id"], "done")
    counts = board.stat()
    assert counts["backlog"] == 1
    assert counts["doing"] == 1
    assert counts["done"] == 1
    assert counts["nextId"] == 4


def test_rebuild_index_migrates_legacy_scope(workspace: Path, workspace_config: dict):
    """A ticket .md with `scope: backend` should be reindexed as projects=['backend']."""
    legacy_md = """---
id: TST-099
title: Legacy ticket
agent: developer
scope: backend
status: backlog
priority: p2
sprint: null
created: 2026-01-01
updated: 2026-01-01
completed: null
depends: null
tags: null
---

# Start
"""
    target = workspace / ".holoctl" / "board" / "tickets" / "TST-099-legacy.md"
    target.write_text(legacy_md, encoding="utf-8")

    board = Board(workspace, workspace_config)
    result = board.rebuild_index()
    assert result["ticketCount"] == 1
    fresh = board.get("TST-099")
    assert fresh["projects"] == ["backend"]


def test_activity_log_records_create(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    board.add({"title": "X"})
    log = (workspace / ".holoctl" / "activity.jsonl").read_text(encoding="utf-8")
    entries = [json.loads(line) for line in log.strip().splitlines() if line]
    assert any(e["type"] == "ticket.created" for e in entries)

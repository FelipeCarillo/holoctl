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


def test_add_rejects_invalid_status(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="Invalid status"):
        board.add({"title": "X", "status": "todo"})


def test_add_rejects_invalid_priority(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="Invalid priority"):
        board.add({"title": "X", "priority": "high"})


def test_add_rejects_unknown_agent(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="Unknown agent"):
        board.add({"title": "X", "agent": "intern"})


def test_add_rejects_empty_title(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(ValueError, match="title is required"):
        board.add({"title": "  "})


def test_set_rejects_invalid_priority(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    with pytest.raises(ValueError, match="Invalid priority"):
        board.set(t["id"], "priority", "high")


def test_set_rejects_unknown_agent(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    with pytest.raises(ValueError, match="Unknown agent"):
        board.set(t["id"], "agent", "intern")


def test_created_and_updated_use_iso_8601_utc(workspace: Path, workspace_config: dict):
    """Timestamps must be full ISO 8601 with UTC `Z` suffix, not date-only."""
    import re
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    iso_z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    assert iso_z.match(t["created"]), f"created not ISO+Z: {t['created']!r}"
    assert iso_z.match(t["updated"]), f"updated not ISO+Z: {t['updated']!r}"


def test_add_with_structured_body_fields(workspace: Path, workspace_config: dict):
    """`goal` + `context` flow into the .md as proper sections."""
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "Auth",
        "agent": "developer",
        "goal": ["JWT signing", "Tests pass"],
        "context": "Sessions are cookie-based today.",
    })
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "# Goal — Definition of Done" in md
    assert "- [ ] JWT signing" in md
    assert "- [ ] Tests pass" in md
    assert "# Context" in md
    assert "Sessions are cookie-based today." in md
    # Optional sections not provided → not rendered.
    assert "# Start" not in md
    assert "# Out of scope" not in md


def test_add_with_raw_body_overrides_template(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "X",
        "agent": "developer",
        "body": "# Anything goes\n\njust freeform text",
    })
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "# Anything goes" in md
    assert "just freeform text" in md
    # Default template sections must not leak in.
    assert "# Start" not in md
    assert "# Goal — Definition of Done" not in md


def test_add_body_field_wins_over_structured(workspace: Path, workspace_config: dict):
    """`body` is the override — structured fields are ignored when both passed."""
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "X",
        "agent": "developer",
        "body": "# Override",
        "goal": ["should be ignored"],
        "context": "should be ignored",
    })
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "# Override" in md
    assert "should be ignored" not in md


def test_add_without_body_falls_back_to_template(workspace: Path, workspace_config: dict):
    """No body / structured fields → use the existing _template.md content."""
    template = workspace / ".holoctl" / "board" / "tickets" / "_template.md"
    template.write_text(
        "---\nid: TPL\n---\n\n# Goal — Definition of Done\n\n- [ ] template criterion\n",
        encoding="utf-8",
    )
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer"})
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "template criterion" in md


def test_set_body_replaces_body_keeps_frontmatter(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer", "goal": ["original"]})
    result = board.set_body(t["id"], "# Goal — Definition of Done\n\n- [x] new content")
    assert result["id"] == t["id"]

    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    # New body present, old goal item gone.
    assert "- [x] new content" in md
    assert "- [ ] original" not in md
    # Frontmatter preserved.
    assert f"id: {t['id']}" in md
    assert "title: X" in md


def test_set_body_rejects_unknown_ticket(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(KeyError, match="not found"):
        board.set_body("MISSING-001", "# X")


def test_set_body_logs_activity(workspace: Path, workspace_config: dict):
    import json as _j
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer"})
    board.set_body(t["id"], "# Updated")
    log = (workspace / ".holoctl" / "activity.jsonl").read_text(encoding="utf-8")
    entries = [_j.loads(line) for line in log.strip().splitlines() if line]
    assert any(e["type"] == "ticket.body_updated" and e["ticket"] == t["id"] for e in entries)

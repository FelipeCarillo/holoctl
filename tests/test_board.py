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
    """`acceptance` (legacy `goal`) + `context` flow into the .md as proper sections."""
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "Auth",
        "agent": "developer",
        "acceptance": ["JWT signing", "Tests pass"],
        "context": "Sessions are cookie-based today.",
    })
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "# Acceptance — Definition of Done" in md
    assert "- [ ] JWT signing" in md
    assert "- [ ] Tests pass" in md
    assert "# Context" in md
    assert "Sessions are cookie-based today." in md
    # Optional sections not provided → not rendered.
    assert "# Start" not in md
    assert "# Out of scope" not in md


def test_add_with_legacy_goal_field_renders_as_acceptance(workspace: Path, workspace_config: dict):
    """Legacy `goal` field is a backwards-compatible alias for `acceptance`."""
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "Auth",
        "agent": "developer",
        "goal": ["JWT signing", "Tests pass"],
    })
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "# Acceptance — Definition of Done" in md
    assert "- [ ] JWT signing" in md


def test_add_with_legacy_out_of_scope_aliases(workspace: Path, workspace_config: dict):
    """Legacy `outOfScope` camelCase is an alias for snake_case `out_of_scope`."""
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "X",
        "agent": "developer",
        "out_of_scope": "no refresh tokens",
    })
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "# Out of scope" in md
    assert "no refresh tokens" in md


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
    assert "# Acceptance — Definition of Done" not in md


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


def test_show_returns_frontmatter_and_body(workspace: Path, workspace_config: dict):
    """`board.show()` is the canonical primitive for ticket inspection."""
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "Auth",
        "agent": "developer",
        "acceptance": ["JWT signing", "Tests pass"],
        "context": "OAuth landing.",
    })
    rec = board.show(t["id"])
    assert rec["id"] == t["id"]
    assert rec["frontmatter"]["title"] == "Auth"
    assert "JWT signing" in rec["body"]
    assert "OAuth landing." in rec["body"]
    assert rec["raw"].startswith("---")


def test_show_rejects_unknown_ticket(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(KeyError, match="not found"):
        board.show("MISSING-001")


def test_ack_toggles_dod_checkbox(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "X",
        "agent": "developer",
        "acceptance": ["criterion A", "criterion B", "criterion C"],
    })
    result = board.ack(t["id"], 1)
    assert result["checked"] is True
    assert result["idx"] == 1
    assert "criterion B" in result["text"]

    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "- [ ] criterion A" in md
    assert "- [x] criterion B" in md
    assert "- [ ] criterion C" in md

    # Toggling back is idempotent in reverse.
    result2 = board.ack(t["id"], 1)
    assert result2["checked"] is False


def test_ack_rejects_out_of_range_idx(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "X",
        "agent": "developer",
        "acceptance": ["only one"],
    })
    with pytest.raises(ValueError, match="out of range"):
        board.ack(t["id"], 5)


def test_ack_rejects_when_no_checkboxes(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({
        "title": "X",
        "agent": "developer",
        "body": "# Notes only\n\njust prose, no checkboxes",
    })
    with pytest.raises(ValueError, match="no DoD checkboxes"):
        board.ack(t["id"], 0)


def test_note_appends_to_notes_section(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer", "acceptance": ["x"]})

    result = board.note(t["id"], "switched to PyJWT")
    assert result["id"] == t["id"]
    assert "PyJWT" in result["note"]

    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "# Notes" in md
    assert "switched to PyJWT" in md

    # Second note appends, doesn't overwrite.
    board.note(t["id"], "added test for edge case")
    md2 = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "switched to PyJWT" in md2
    assert "added test for edge case" in md2


def test_note_rejects_empty_text(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer"})
    with pytest.raises(ValueError, match="empty"):
        board.note(t["id"], "   ")


def test_note_logs_activity(workspace: Path, workspace_config: dict):
    import json as _j
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer"})
    board.note(t["id"], "checkpoint")
    log = (workspace / ".holoctl" / "activity.jsonl").read_text(encoding="utf-8")
    entries = [_j.loads(line) for line in log.strip().splitlines() if line]
    assert any(e["type"] == "ticket.note" and e["ticket"] == t["id"] for e in entries)


def test_delete_removes_md_and_index_entry(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t = board.add({"title": "Doomed", "agent": "developer"})
    md_path = workspace / ".holoctl" / "board" / t["file"]
    assert md_path.exists()

    result = board.delete(t["id"])
    assert result["id"] == t["id"]
    assert result["deleted"] is True

    # .md file gone.
    assert not md_path.exists()
    # Index entry gone.
    assert board.get(t["id"]) is None


def test_delete_does_not_reuse_id(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t1 = board.add({"title": "First", "agent": "developer"})
    board.delete(t1["id"])
    t2 = board.add({"title": "Second", "agent": "developer"})
    # IDs increment monotonically; deletion doesn't free the number.
    n1 = int(t1["id"].split("-")[-1])
    n2 = int(t2["id"].split("-")[-1])
    assert n2 > n1


def test_delete_rejects_unknown_ticket(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    with pytest.raises(KeyError, match="not found"):
        board.delete("MISSING-001")


def test_delete_logs_activity(workspace: Path, workspace_config: dict):
    import json as _j
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer"})
    board.delete(t["id"])
    log = (workspace / ".holoctl" / "activity.jsonl").read_text(encoding="utf-8")
    entries = [_j.loads(line) for line in log.strip().splitlines() if line]
    assert any(e["type"] == "ticket.deleted" and e["ticket"] == t["id"] for e in entries)


def test_batch_move_succeeds_per_ticket(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t1 = board.add({"title": "A", "agent": "developer"})
    t2 = board.add({"title": "B", "agent": "developer"})
    t3 = board.add({"title": "C", "agent": "developer"})
    result = board.batch_move([t1["id"], t2["id"], t3["id"]], "doing")
    assert result["count"] == 3
    assert result["errors"] == []
    for r in result["moved"]:
        assert r["to"] == "doing"
    for tid in (t1["id"], t2["id"], t3["id"]):
        assert board.get(tid)["status"] == "doing"


def test_batch_move_reports_per_id_errors(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t1 = board.add({"title": "Real", "agent": "developer"})
    result = board.batch_move([t1["id"], "FAKE-999"], "doing")
    assert result["count"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["id"] == "FAKE-999"
    # The real one still moved despite the bad sibling.
    assert board.get(t1["id"])["status"] == "doing"


def test_batch_set_applies_field_to_all(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t1 = board.add({"title": "A", "agent": "developer"})
    t2 = board.add({"title": "B", "agent": "developer"})
    result = board.batch_set([t1["id"], t2["id"]], "priority", "p0")
    assert result["count"] == 2
    assert result["errors"] == []
    assert board.get(t1["id"])["priority"] == "p0"
    assert board.get(t2["id"])["priority"] == "p0"


def test_batch_delete_removes_all(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    t1 = board.add({"title": "A", "agent": "developer"})
    t2 = board.add({"title": "B", "agent": "developer"})
    t3 = board.add({"title": "Keep", "agent": "developer"})
    result = board.batch_delete([t1["id"], t2["id"]])
    assert result["count"] == 2
    assert result["errors"] == []
    assert board.get(t1["id"]) is None
    assert board.get(t2["id"]) is None
    # Unrelated ticket survives.
    assert board.get(t3["id"]) is not None


def test_kind_defaults_to_task(workspace: Path, workspace_config: dict):
    """Work item without explicit kind is a 'task'."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X", "agent": "developer"})
    assert t["kind"] == "task"
    assert t["parent"] is None
    assert t["source_provider"] is None


def test_kind_and_parent_persist_in_frontmatter(workspace: Path, workspace_config: dict):
    """`kind` and `parent` are written to the .md frontmatter and round-trip."""
    board = Board(workspace, workspace_config)
    spec = board.add({"title": "Add auth", "kind": "spec"})
    child = board.add({
        "title": "JWT signing",
        "kind": "task",
        "parent": spec["id"],
        "agent": "developer",
    })
    md = (workspace / ".holoctl" / "board" / child["file"]).read_text(encoding="utf-8")
    assert "kind: task" in md
    assert f"parent: {spec['id']}" in md

    # Round-trip via rebuild_index.
    board.rebuild_index()
    again = board.get(child["id"])
    assert again["kind"] == "task"
    assert again["parent"] == spec["id"]


def test_source_fields_optional_and_persist(workspace: Path, workspace_config: dict):
    """External-board source fields are optional but round-trip when provided."""
    board = Board(workspace, workspace_config)
    # Without source: all None.
    t1 = board.add({"title": "Solo", "agent": "developer"})
    assert t1["source_provider"] is None
    assert t1["source_ref"] is None
    # With source.
    t2 = board.add({
        "title": "From Trello",
        "agent": "developer",
        "kind": "spec",
        "source_provider": "trello",
        "source_ref": "ABC123",
        "source_url": "https://trello.com/c/ABC123",
        "source_label": "Card #ABC: Add JWT",
    })
    assert t2["source_provider"] == "trello"
    assert t2["source_ref"] == "ABC123"

    md = (workspace / ".holoctl" / "board" / t2["file"]).read_text(encoding="utf-8")
    assert "source_provider: trello" in md
    assert "source_ref: ABC123" in md


def test_filter_by_kind(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    board.add({"title": "spec1", "kind": "spec"})
    board.add({"title": "bug1", "kind": "bug", "agent": "developer"})
    board.add({"title": "task1", "agent": "developer"})  # kind=task default
    specs = board.ls({"kind": "spec"})
    bugs = board.ls({"kind": "bug"})
    tasks = board.ls({"kind": "task"})
    assert len(specs) == 1
    assert len(bugs) == 1
    assert len(tasks) == 1


def test_filter_by_parent(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    spec = board.add({"title": "Spec", "kind": "spec"})
    c1 = board.add({"title": "Child 1", "agent": "developer", "parent": spec["id"]})
    c2 = board.add({"title": "Child 2", "agent": "developer", "parent": spec["id"]})
    board.add({"title": "Unrelated", "agent": "developer"})

    children = board.ls({"parent": spec["id"]})
    ids = {t["id"] for t in children}
    assert ids == {c1["id"], c2["id"]}


def test_children_returns_progress(workspace: Path, workspace_config: dict):
    board = Board(workspace, workspace_config)
    spec = board.add({"title": "Big spec", "kind": "spec"})
    c1 = board.add({
        "title": "T1", "agent": "developer", "parent": spec["id"],
        "acceptance": ["a", "b"],
    })
    c2 = board.add({
        "title": "T2", "agent": "developer", "parent": spec["id"],
        "acceptance": ["c"],
    })
    board.ack(c1["id"], 0)  # 1 of 2 done in c1
    board.move(c2["id"], "doing")

    result = board.children(spec["id"])
    assert result["parent"]["id"] == spec["id"]
    assert len(result["children"]) == 2
    assert result["total_acceptance"] == 3
    assert result["acked"] == 1
    assert result["by_status"].get("doing") == 1
    assert result["by_status"].get("backlog") == 1


def test_batch_add_propagates_parent_kind_source_from_shared(workspace: Path, workspace_config: dict):
    """When boardmaster decomposes a spec, children inherit shared fields."""
    board = Board(workspace, workspace_config)
    spec = board.add({
        "title": "Auth flow",
        "kind": "spec",
        "source_provider": "linear",
        "source_ref": "ENG-42",
    })
    result = board.batch_add(
        shared={
            "parent": spec["id"],
            "kind": "task",
            "source_provider": "linear",
            "source_ref": "ENG-42",
            "tags": ["par:auth-flow"],
        },
        tickets=[
            {"title": "JWT signing", "agent": "developer", "files": ["src/auth/jwt.py"]},
            {"title": "Middleware", "agent": "developer", "files": ["src/middleware/auth.py"]},
        ],
    )
    assert result["count"] == 2
    for t in result["tickets"]:
        assert t["parent"] == spec["id"]
        assert t["kind"] == "task"
        assert t["source_provider"] == "linear"
        assert t["source_ref"] == "ENG-42"
        assert "par:auth-flow" in t["tags"]


# ---- Parent cycle validation (v0.17 follow-up) ---------------------------


def test_set_parent_to_self_raises(workspace: Path, workspace_config: dict):
    """A ticket cannot be its own parent."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "Loop me", "kind": "spec"})
    with pytest.raises(ValueError, match="cycle|self"):
        board.set(t["id"], "parent", t["id"])


def test_set_parent_to_nonexistent_raises(workspace: Path, workspace_config: dict):
    """Parent ID must reference an existing ticket."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "Orphan", "agent": "developer"})
    with pytest.raises((KeyError, ValueError), match="TST-999|not found"):
        board.set(t["id"], "parent", "TST-999")


def test_set_parent_two_level_cycle_raises(workspace: Path, workspace_config: dict):
    """A→B exists; setting B.parent=A creates A→B→A and must fail."""
    board = Board(workspace, workspace_config)
    a = board.add({"title": "A", "kind": "spec"})
    b = board.add({"title": "B", "kind": "spec", "parent": a["id"]})
    # Now try to make A's parent = B → would close a cycle.
    with pytest.raises(ValueError, match="cycle"):
        board.set(a["id"], "parent", b["id"])


def test_set_parent_three_level_cycle_raises(workspace: Path, workspace_config: dict):
    """A→B→C; setting A.parent=C closes the cycle and must fail."""
    board = Board(workspace, workspace_config)
    a = board.add({"title": "A", "kind": "spec"})
    b = board.add({"title": "B", "kind": "spec", "parent": a["id"]})
    c = board.add({"title": "C", "kind": "spec", "parent": b["id"]})
    with pytest.raises(ValueError, match="cycle"):
        board.set(a["id"], "parent", c["id"])


def test_set_parent_clears_with_empty_value(workspace: Path, workspace_config: dict):
    """Empty/null string clears the parent (orphan the item)."""
    board = Board(workspace, workspace_config)
    spec = board.add({"title": "S", "kind": "spec"})
    child = board.add({"title": "C", "agent": "developer", "parent": spec["id"]})
    board.set(child["id"], "parent", "")
    assert board.get(child["id"])["parent"] in (None, "")


def test_set_parent_to_valid_sibling_succeeds(workspace: Path, workspace_config: dict):
    """Re-parenting between two unrelated specs is allowed."""
    board = Board(workspace, workspace_config)
    s1 = board.add({"title": "S1", "kind": "spec"})
    s2 = board.add({"title": "S2", "kind": "spec"})
    t = board.add({"title": "T", "agent": "developer", "parent": s1["id"]})
    board.set(t["id"], "parent", s2["id"])
    assert board.get(t["id"])["parent"] == s2["id"]


def test_add_with_nonexistent_parent_raises(workspace: Path, workspace_config: dict):
    """`board add` rejects a parent reference that doesn't exist yet."""
    board = Board(workspace, workspace_config)
    with pytest.raises((KeyError, ValueError), match="TST-999|not found"):
        board.add({"title": "Orphan", "agent": "developer", "parent": "TST-999"})


# ---- Tree rendering (v0.17 follow-up) ------------------------------------


def test_tree_flat_when_no_parents(workspace: Path, workspace_config: dict):
    """With no parent relationships, every ticket is a root (depth 0, empty prefix)."""
    board = Board(workspace, workspace_config)
    board.add({"title": "A", "agent": "developer"})
    board.add({"title": "B", "agent": "developer"})
    rows = board.tree()
    assert len(rows) == 2
    for r in rows:
        assert r["depth"] == 0
        assert r["prefix"] == ""


def test_tree_renders_two_level_hierarchy(workspace: Path, workspace_config: dict):
    """A spec with two children renders with ├─ for inner, └─ for last child."""
    board = Board(workspace, workspace_config)
    spec = board.add({"title": "Spec", "kind": "spec"})
    board.add({"title": "C1", "agent": "developer", "parent": spec["id"]})
    board.add({"title": "C2", "agent": "developer", "parent": spec["id"]})

    rows = board.tree()
    by_id = {r["ticket"]["id"]: r for r in rows}
    assert by_id[spec["id"]]["depth"] == 0
    assert by_id[spec["id"]]["prefix"] == ""
    # First child is not the last → uses ├─
    first_child_id = sorted(t["id"] for t in [r["ticket"] for r in rows] if t["id"] != spec["id"])[0]
    last_child_id = sorted(t["id"] for t in [r["ticket"] for r in rows] if t["id"] != spec["id"])[-1]
    assert by_id[first_child_id]["prefix"] == "├─ "
    assert by_id[last_child_id]["prefix"] == "└─ "


def test_tree_three_levels_uses_pipe_padding(workspace: Path, workspace_config: dict):
    """Grandchildren get the `│  ` continuation glyph for ancestors that still have siblings."""
    board = Board(workspace, workspace_config)
    spec = board.add({"title": "Spec", "kind": "spec"})
    a = board.add({"title": "A", "agent": "developer", "parent": spec["id"]})
    board.add({"title": "B", "agent": "developer", "parent": spec["id"]})  # makes A non-last
    board.add({"title": "A1", "agent": "developer", "parent": a["id"]})  # only child of A
    rows = board.tree()
    by_id = {r["ticket"]["id"]: r for r in rows}
    # A is non-last sibling under spec → ancestor padding for its child uses │
    a1 = next(r for r in rows if r["ticket"]["title"] == "A1")
    assert a1["prefix"] == "│  └─ "


def test_tree_filters_apply_but_keep_ancestors(workspace: Path, workspace_config: dict):
    """`tree({"kind":"task"})` filters tasks but still anchors them under their spec parent."""
    board = Board(workspace, workspace_config)
    spec = board.add({"title": "Spec", "kind": "spec"})
    board.add({"title": "T1", "agent": "developer", "parent": spec["id"]})
    rows = board.tree({"kind": "task"})
    ids = {r["ticket"]["id"] for r in rows}
    # The spec itself isn't a task, but it shows as an anchor so the hierarchy reads.
    assert spec["id"] in ids
    # The task shows up nested under the spec.
    task_row = next(r for r in rows if r["ticket"]["title"] == "T1")
    assert task_row["depth"] == 1


def test_tree_rooted_at_parent_id(workspace: Path, workspace_config: dict):
    """`tree(root=SPEC_ID)` returns only the subtree under SPEC_ID."""
    board = Board(workspace, workspace_config)
    s1 = board.add({"title": "S1", "kind": "spec"})
    s2 = board.add({"title": "S2", "kind": "spec"})
    board.add({"title": "C1", "agent": "developer", "parent": s1["id"]})
    board.add({"title": "C2", "agent": "developer", "parent": s2["id"]})

    rows = board.tree(root=s1["id"])
    titles = {r["ticket"]["title"] for r in rows}
    assert titles == {"S1", "C1"}


# ---- Status transition observability + completed reliability (Task B) --------


def _activity_events(workspace: Path, ticket_id: str) -> list[dict]:
    """Helper: read activity.jsonl and return events for a given ticket."""
    log = workspace / ".holoctl" / "activity.jsonl"
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("ticket") == ticket_id
    ]


def test_move_logs_ticket_moved_event(workspace: Path, workspace_config: dict):
    """move() logs a ticket.moved event with correct from/to fields."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.move(t["id"], "doing")
    events = _activity_events(workspace, t["id"])
    moved = [e for e in events if e["type"] == "ticket.moved"]
    assert len(moved) == 1
    assert moved[0]["from"] == "backlog"
    assert moved[0]["to"] == "doing"


def test_move_noop_does_not_log(workspace: Path, workspace_config: dict):
    """move() with the same status should not add a ticket.moved event."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.move(t["id"], "backlog")  # no-op: already backlog
    events = _activity_events(workspace, t["id"])
    moved = [e for e in events if e["type"] == "ticket.moved"]
    assert moved == []


def test_move_to_done_sets_completed_in_index_and_md(workspace: Path, workspace_config: dict):
    """move() to done sets completed on the index entry AND the .md frontmatter."""
    import re as _re
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.move(t["id"], "done")

    # Index
    fresh = board.get(t["id"])
    assert fresh["completed"] is not None
    assert _re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", fresh["completed"])

    # .md frontmatter
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert f"completed: {fresh['completed']}" in md


def test_move_away_from_done_clears_completed(workspace: Path, workspace_config: dict):
    """move() away from done clears completed in both index and .md."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.move(t["id"], "done")
    board.move(t["id"], "doing")

    fresh = board.get(t["id"])
    assert fresh["completed"] is None

    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert "completed: null" in md


def test_set_status_logs_ticket_moved_and_sets_completed(workspace: Path, workspace_config: dict):
    """set(field='status', value='done') sets completed AND logs ticket.moved."""
    import re as _re
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.set(t["id"], "status", "done")

    # completed set
    fresh = board.get(t["id"])
    assert fresh["completed"] is not None
    assert _re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", fresh["completed"])

    # ticket.moved logged
    events = _activity_events(workspace, t["id"])
    moved = [e for e in events if e["type"] == "ticket.moved"]
    assert len(moved) == 1
    assert moved[0]["from"] == "backlog"
    assert moved[0]["to"] == "done"


def test_set_status_away_from_done_clears_completed(workspace: Path, workspace_config: dict):
    """set(field='status') leaving done clears completed."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.set(t["id"], "status", "done")
    board.set(t["id"], "status", "doing")

    fresh = board.get(t["id"])
    assert fresh["completed"] is None


def test_set_status_noop_does_not_log(workspace: Path, workspace_config: dict):
    """set(field='status') with the current value logs nothing."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.move(t["id"], "doing")
    before = len(_activity_events(workspace, t["id"]))
    board.set(t["id"], "status", "doing")  # no-op
    after = len(_activity_events(workspace, t["id"]))
    assert after == before


def test_set_status_completed_written_to_md(workspace: Path, workspace_config: dict):
    """set() status-to-done persists completed in .md frontmatter."""
    board = Board(workspace, workspace_config)
    t = board.add({"title": "X"})
    board.set(t["id"], "status", "done")
    fresh = board.get(t["id"])
    md = (workspace / ".holoctl" / "board" / t["file"]).read_text(encoding="utf-8")
    assert f"completed: {fresh['completed']}" in md


def test_batch_move_logs_one_moved_event_per_changed_ticket(workspace: Path, workspace_config: dict):
    """batch_move logs a ticket.moved for each ticket that actually changed."""
    board = Board(workspace, workspace_config)
    t1 = board.add({"title": "A"})
    t2 = board.add({"title": "B"})
    t3 = board.add({"title": "C"})
    board.batch_move([t1["id"], t2["id"], t3["id"]], "doing")

    for tid in (t1["id"], t2["id"], t3["id"]):
        events = _activity_events(workspace, tid)
        moved = [e for e in events if e["type"] == "ticket.moved"]
        assert len(moved) == 1
        assert moved[0]["from"] == "backlog"
        assert moved[0]["to"] == "doing"


def test_batch_move_to_done_sets_completed_per_ticket(workspace: Path, workspace_config: dict):
    """batch_move to done sets completed on every ticket."""
    board = Board(workspace, workspace_config)
    t1 = board.add({"title": "A"})
    t2 = board.add({"title": "B"})
    board.batch_move([t1["id"], t2["id"]], "done")
    assert board.get(t1["id"])["completed"] is not None
    assert board.get(t2["id"])["completed"] is not None


def test_move_and_set_produce_same_event_schema(workspace: Path, workspace_config: dict):
    """ticket.moved events from move() and set() have identical fields."""
    board = Board(workspace, workspace_config)
    t1 = board.add({"title": "A"})
    t2 = board.add({"title": "B"})

    board.move(t1["id"], "doing")
    board.set(t2["id"], "status", "doing")

    ev1 = next(e for e in _activity_events(workspace, t1["id"]) if e["type"] == "ticket.moved")
    ev2 = next(e for e in _activity_events(workspace, t2["id"]) if e["type"] == "ticket.moved")

    # Both must have the same set of keys (ts may differ by value but same field).
    assert set(ev1.keys()) == set(ev2.keys())
    assert ev1["from"] == "backlog" and ev1["to"] == "doing"
    assert ev2["from"] == "backlog" and ev2["to"] == "doing"

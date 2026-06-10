"""Schema-drift guard for ``holoctl.lib.ticket.Ticket``.

The ``Ticket`` TypedDict must cover every key the board actually produces —
both the index rows written by ``Board.add()`` and the rows rebuilt from the
ticket .md frontmatter by ``Board.rebuild_index()``. Whenever a new field is
added to the ticket shape in ``board.py``, these tests fail until the schema
in ``ticket.py`` is updated to match (and vice-versa stays honest via the
two-way checks on the canonical key set).
"""
from __future__ import annotations

import json
from pathlib import Path

from holoctl.lib.board import Board
from holoctl.lib.markdown import parse_frontmatter
from holoctl.lib.ticket import TICKET_LIST_FIELDS, TICKET_SOURCE_FIELDS, Ticket

# A patch that exercises every user-settable field flowing into Board.add()
# (kind/parent/source_* included), so the produced ticket carries the full
# key surface — not just the defaults.
_FULL_PATCH = {
    "title": "Wire the auth flow",
    "kind": "task",
    "agent": "developer",
    "priority": "p1",
    "sprint": "2026-S3",
    "projects": ["app", "api"],
    "files": ["src/auth.py", "src/session.py"],
    "depends": ["TST-001"],
    "tags": ["auth", "backend"],
    "source_provider": "linear",
    "source_ref": "ENG-123",
    "source_url": "https://linear.app/x/issue/ENG-123",
    "source_label": "ENG-123: Wire the auth flow",
    "acceptance": ["login works", "session persists"],
    "context": "Why this exists",
}


def _make_full_ticket(workspace: Path, config: dict) -> tuple[Board, dict]:
    board = Board(workspace, config)
    parent = board.add({"title": "Auth spec", "kind": "spec"})
    ticket = board.add({**_FULL_PATCH, "parent": parent["id"]})
    return board, ticket


def test_ticket_schema_covers_board_add_keys(workspace: Path, workspace_config: dict):
    """Every key Board.add() writes to the index must be declared on Ticket."""
    _, ticket = _make_full_ticket(workspace, workspace_config)
    missing = set(ticket) - set(Ticket.__annotations__)
    assert not missing, f"Board.add() produces keys missing from Ticket: {sorted(missing)}"


def test_ticket_schema_covers_rebuild_index_keys(workspace: Path, workspace_config: dict):
    """Every key rebuild_index() reconstructs from .md frontmatter is declared."""
    board, _ = _make_full_ticket(workspace, workspace_config)
    board.rebuild_index()
    index = json.loads(
        (workspace / ".holoctl" / "board" / "index.json").read_text(encoding="utf-8")
    )
    assert index["tickets"], "rebuild_index dropped the tickets"
    for row in index["tickets"]:
        missing = set(row) - set(Ticket.__annotations__)
        assert not missing, (
            f"rebuild_index() produces keys missing from Ticket: {sorted(missing)}"
        )


def test_add_and_rebuild_produce_the_same_key_set(workspace: Path, workspace_config: dict):
    """The index row shape must not drift between add() and rebuild_index()."""
    board, ticket = _make_full_ticket(workspace, workspace_config)
    add_keys = set(ticket)
    board.rebuild_index()
    index = json.loads(
        (workspace / ".holoctl" / "board" / "index.json").read_text(encoding="utf-8")
    )
    rebuilt = next(r for r in index["tickets"] if r["id"] == ticket["id"])
    assert set(rebuilt) == add_keys


def test_ticket_schema_covers_md_frontmatter_keys(workspace: Path, workspace_config: dict):
    """Every frontmatter key written to the ticket .md is declared on Ticket."""
    _, ticket = _make_full_ticket(workspace, workspace_config)
    md = (workspace / ".holoctl" / "board" / ticket["file"]).read_text(encoding="utf-8")
    fm, _body = parse_frontmatter(md)
    assert fm, "ticket .md has no parseable frontmatter"
    missing = set(fm) - set(Ticket.__annotations__)
    assert not missing, (
        f"_create_ticket_md() writes frontmatter keys missing from Ticket: {sorted(missing)}"
    )


def test_list_and_source_field_constants_are_declared():
    """The helper constants must point at real Ticket fields."""
    annotations = set(Ticket.__annotations__)
    assert set(TICKET_LIST_FIELDS) <= annotations
    assert set(TICKET_SOURCE_FIELDS) <= annotations
    # List fields are exactly the ones Board serializes as comma-joined CSV.
    assert TICKET_LIST_FIELDS == ("agent", "projects", "files", "depends", "tags")


def test_list_fields_are_lists_on_a_real_ticket(workspace: Path, workspace_config: dict):
    """The fields declared list-typed in the schema are lists in the index."""
    _, ticket = _make_full_ticket(workspace, workspace_config)
    for field in TICKET_LIST_FIELDS:
        assert isinstance(ticket[field], list), f"{field} should be a list"

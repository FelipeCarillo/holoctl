"""F7 — render_tree is now a pure function, unit-testable without a Board."""
from __future__ import annotations

import pytest

from holoctl.lib.board_tree import render_tree


def _t(tid, parent=None):
    return {"id": tid, "title": tid, "parent": parent}


def test_flat_roots_have_empty_prefix_and_depth_zero():
    tickets = [_t("A-1"), _t("A-2")]
    rows = render_tree(tickets, {"A-1", "A-2"})
    assert [r["ticket"]["id"] for r in rows] == ["A-1", "A-2"]
    assert all(r["depth"] == 0 and r["prefix"] == "" for r in rows)


def test_children_get_glyph_prefixes_and_depth():
    tickets = [_t("A-1"), _t("A-2", parent="A-1"), _t("A-3", parent="A-1")]
    rows = render_tree(tickets, {t["id"] for t in tickets})
    by_id = {r["ticket"]["id"]: r for r in rows}
    assert by_id["A-1"]["depth"] == 0 and by_id["A-1"]["prefix"] == ""
    assert by_id["A-2"]["depth"] == 1 and by_id["A-2"]["prefix"] == "├─ "
    assert by_id["A-3"]["depth"] == 1 and by_id["A-3"]["prefix"] == "└─ "  # last child


def test_ancestor_kept_when_only_descendant_matches():
    tickets = [_t("A-1"), _t("A-2", parent="A-1")]
    # Only the child matched the filter; the parent must still appear.
    rows = render_tree(tickets, {"A-2"})
    ids = [r["ticket"]["id"] for r in rows]
    assert ids == ["A-1", "A-2"]


def test_root_argument_restricts_to_subtree():
    tickets = [_t("A-1"), _t("A-2", parent="A-1"), _t("A-3")]
    rows = render_tree(tickets, {t["id"] for t in tickets}, root="A-1")
    ids = [r["ticket"]["id"] for r in rows]
    assert ids == ["A-1", "A-2"]
    assert "A-3" not in ids


def test_unknown_root_raises():
    with pytest.raises(KeyError):
        render_tree([_t("A-1")], {"A-1"}, root="NOPE")

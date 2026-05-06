"""Tests for holoctl.lib.board._build_body — structured ticket body assembly."""
from __future__ import annotations

from holoctl.lib.board import _build_body


def test_returns_none_for_empty_patch():
    """No body / structured fields → None signals "fall back to template"."""
    assert _build_body({}) is None
    assert _build_body({"title": "X", "agent": "developer"}) is None


def test_raw_body_wins():
    """If `body` is set, it wins regardless of structured fields."""
    out = _build_body({"body": "# Custom\n\nfreeform", "goal": ["ignored"]})
    assert out == "# Custom\n\nfreeform"


def test_blank_body_falls_through_to_structured():
    """An empty/whitespace `body` is treated as absent."""
    out = _build_body({"body": "  \n  ", "goal": ["criterion"]})
    assert out is not None
    assert "# Goal — Definition of Done" in out
    assert "- [ ] criterion" in out


def test_goal_array_renders_checklist():
    out = _build_body({"goal": ["build X", "test X", "lint passes"]})
    assert "# Goal — Definition of Done" in out
    assert "- [ ] build X" in out
    assert "- [ ] test X" in out
    assert "- [ ] lint passes" in out


def test_goal_string_split_on_newline():
    """An agent might pass a multi-line string instead of array."""
    out = _build_body({"goal": "build X\ntest X\n\nlint"})
    assert "- [ ] build X" in out
    assert "- [ ] test X" in out
    assert "- [ ] lint" in out


def test_optional_sections_preserved():
    out = _build_body({
        "goal": ["foo"],
        "start": "Currently the auth uses cookies.",
        "context": "OAuth landing requires bearer tokens.",
        "outOfScope": "Refresh tokens",
        "executionNotes": "PR #42",
    })
    assert "# Start" in out and "Currently the auth uses cookies." in out
    assert "# Context" in out and "bearer tokens" in out
    assert "# Out of scope" in out and "Refresh tokens" in out
    assert "# Execution notes" in out and "PR #42" in out


def test_blank_optional_section_omitted():
    """Empty / whitespace-only optional fields are dropped, no header rendered."""
    out = _build_body({
        "goal": ["foo"],
        "start": "  ",
        "context": "real context",
    })
    assert "# Start" not in out
    assert "# Context" in out


def test_section_order_is_canonical():
    """Goal first, then start/context/outOfScope/executionNotes in that order."""
    out = _build_body({
        "executionNotes": "1",
        "outOfScope": "2",
        "context": "3",
        "start": "4",
        "goal": ["5"],
    })
    g = out.find("# Goal")
    s = out.find("# Start")
    c = out.find("# Context")
    o = out.find("# Out of scope")
    e = out.find("# Execution notes")
    assert -1 < g < s < c < o < e


def test_empty_goal_list_does_not_emit_header():
    """`goal: []` is the same as no goal — Goal section is omitted."""
    out = _build_body({"goal": [], "context": "ctx"})
    assert out is not None
    assert "# Goal" not in out
    assert "# Context" in out


def test_goal_filters_blank_items():
    out = _build_body({"goal": ["real", "", "  ", "another"]})
    assert "- [ ] real" in out
    assert "- [ ] another" in out
    # Filtered blank items should not render as bare `- [ ]` lines.
    assert "- [ ] \n" not in out

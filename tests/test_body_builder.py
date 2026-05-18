"""Tests for holoctl.lib.board._build_body — structured ticket body assembly."""
from __future__ import annotations

from holoctl.lib.board import _build_body


def test_returns_none_for_empty_patch():
    """No body / structured fields → None signals "fall back to template"."""
    assert _build_body({}) is None
    assert _build_body({"title": "X", "agent": "developer"}) is None


def test_raw_body_wins():
    """If `body` is set, it wins regardless of structured fields."""
    out = _build_body({"body": "# Custom\n\nfreeform", "acceptance": ["ignored"]})
    assert out == "# Custom\n\nfreeform"


def test_blank_body_falls_through_to_structured():
    """An empty/whitespace `body` is treated as absent."""
    out = _build_body({"body": "  \n  ", "acceptance": ["criterion"]})
    assert out is not None
    assert "# Acceptance — Definition of Done" in out
    assert "- [ ] criterion" in out


def test_acceptance_array_renders_checklist():
    out = _build_body({"acceptance": ["build X", "test X", "lint passes"]})
    assert "# Acceptance — Definition of Done" in out
    assert "- [ ] build X" in out
    assert "- [ ] test X" in out
    assert "- [ ] lint passes" in out


def test_legacy_goal_field_is_alias_for_acceptance():
    """Backwards compat: `goal` keeps working as alias for `acceptance`."""
    out = _build_body({"goal": ["build X", "test X"]})
    assert "# Acceptance — Definition of Done" in out
    assert "- [ ] build X" in out


def test_acceptance_string_split_on_newline():
    """An agent might pass a multi-line string instead of array."""
    out = _build_body({"acceptance": "build X\ntest X\n\nlint"})
    assert "- [ ] build X" in out
    assert "- [ ] test X" in out
    assert "- [ ] lint" in out


def test_optional_sections_preserved():
    """Legacy field names (`start`, `outOfScope`, `executionNotes`) still work as aliases."""
    out = _build_body({
        "acceptance": ["foo"],
        "start": "Currently the auth uses cookies.",
        "context": "OAuth landing requires bearer tokens.",
        "outOfScope": "Refresh tokens",
        "executionNotes": "PR #42",
    })
    # `start` merges into context (M8 design)
    assert "# Context" in out and "bearer tokens" in out and "cookies" in out
    assert "# Out of scope" in out and "Refresh tokens" in out
    assert "# Notes" in out and "PR #42" in out


def test_preferred_snake_case_field_names():
    """`out_of_scope` and `notes` are the preferred names."""
    out = _build_body({
        "acceptance": ["foo"],
        "context": "the why",
        "out_of_scope": "Don't do X",
        "notes": "PR #42",
    })
    assert "# Context" in out and "the why" in out
    assert "# Out of scope" in out and "Don't do X" in out
    assert "# Notes" in out and "PR #42" in out


def test_blank_optional_section_omitted():
    """Empty / whitespace-only optional fields are dropped, no header rendered."""
    out = _build_body({
        "acceptance": ["foo"],
        "start": "  ",
        "context": "real context",
    })
    assert "real context" in out
    assert "# Out of scope" not in out


def test_section_order_is_canonical():
    """Acceptance first, then context/out_of_scope/notes in that order."""
    out = _build_body({
        "notes": "1",
        "out_of_scope": "2",
        "context": "3",
        "acceptance": ["5"],
    })
    a = out.find("# Acceptance")
    c = out.find("# Context")
    o = out.find("# Out of scope")
    n = out.find("# Notes")
    assert -1 < a < c < o < n


def test_empty_acceptance_list_does_not_emit_header():
    """`acceptance: []` is the same as no acceptance — section is omitted."""
    out = _build_body({"acceptance": [], "context": "ctx"})
    assert out is not None
    assert "# Acceptance" not in out
    assert "# Context" in out


def test_acceptance_filters_blank_items():
    out = _build_body({"acceptance": ["real", "", "  ", "another"]})
    assert "- [ ] real" in out
    assert "- [ ] another" in out
    # Filtered blank items should not render as bare `- [ ]` lines.
    assert "- [ ] \n" not in out

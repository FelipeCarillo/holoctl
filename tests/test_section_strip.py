"""Tests for the dashboard's empty-section stripper."""
from __future__ import annotations

from holoctl.server.app import _strip_empty_sections, _is_placeholder_only


def test_keeps_section_with_real_content():
    body = """\
# Goal

- [ ] Implement JWT auth
- [x] Tests pass
"""
    assert _strip_empty_sections(body) == body


def test_drops_section_with_only_placeholder_paren():
    body = """\
# Context

(Why this exists)

# Goal

- [ ] real
"""
    out = _strip_empty_sections(body)
    assert "Context" not in out
    assert "Goal" in out
    assert "real" in out


def test_drops_section_with_only_placeholder_checklist():
    body = """\
# Goal

- [ ] (criteria 1)
- [ ] (criteria 2)
"""
    out = _strip_empty_sections(body)
    assert "Goal" not in out
    assert "(criteria" not in out


def test_drops_empty_section():
    body = """\
# Out of scope


# Context

real content here
"""
    out = _strip_empty_sections(body)
    assert "Out of scope" not in out
    assert "Context" in out


def test_drops_html_comment_only_section():
    body = """\
# Start

<!-- Files that will be touched. -->

# Context

real content
"""
    out = _strip_empty_sections(body)
    assert "# Start" not in out
    assert "# Context" in out


def test_keeps_section_when_some_lines_real():
    body = """\
# Goal

- [ ] (placeholder)
- [ ] real criterion
"""
    out = _strip_empty_sections(body)
    assert "Goal" in out
    assert "real criterion" in out


def test_no_sections_returns_as_is():
    body = "Just a plain body with no headers."
    assert _strip_empty_sections(body) == body


def test_is_placeholder_only_recognizes_paren():
    assert _is_placeholder_only("\n(some hint)\n\n")


def test_is_placeholder_only_recognizes_html_comment():
    assert _is_placeholder_only("<!-- hint -->\n")


def test_is_placeholder_only_recognizes_blank():
    assert _is_placeholder_only("\n  \n\t\n")


def test_is_placeholder_only_rejects_real_content():
    assert not _is_placeholder_only("- [ ] real criterion\n")

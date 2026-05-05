"""Tests for holoctl.lib.markdown — frontmatter parse/serialize."""
from __future__ import annotations

from holoctl.lib.markdown import parse_frontmatter, serialize_frontmatter


def test_parse_simple_frontmatter():
    content = """---
id: PRJ-001
title: Hello
priority: p1
---

# Body
"""
    data, body = parse_frontmatter(content)
    assert data == {"id": "PRJ-001", "title": "Hello", "priority": "p1"}
    assert body.strip().startswith("# Body")


def test_parse_returns_empty_on_no_frontmatter():
    content = "no frontmatter here\n# just body"
    data, body = parse_frontmatter(content)
    assert data == {}
    assert body == content


def test_parse_typed_values():
    content = """---
ok: true
broken: false
count: 42
ratio: 1.5
nothing: null
empty:
---
"""
    data, _ = parse_frontmatter(content)
    assert data["ok"] is True
    assert data["broken"] is False
    assert data["count"] == 42
    assert data["ratio"] == 1.5
    assert data["nothing"] is None
    assert data["empty"] is None


def test_parse_quoted_strings():
    content = '---\nname: "with: colon"\nalt: \'with quotes\'\n---\n'
    data, _ = parse_frontmatter(content)
    assert data["name"] == "with: colon"
    assert data["alt"] == "with quotes"


def test_parse_inline_array():
    content = "---\ntags: [a, b, c]\n---\n"
    data, _ = parse_frontmatter(content)
    assert data["tags"] == ["a", "b", "c"]


def test_serialize_simple():
    out = serialize_frontmatter({"id": "X-1", "title": "T"}, body="content here")
    assert out.startswith("---\nid: X-1\ntitle: T\n---")
    assert "content here" in out


def test_serialize_typed_values():
    out = serialize_frontmatter({
        "ok": True,
        "n": 42,
        "nothing": None,
        "tags": ["a", "b"],
        "empty_list": [],
    })
    assert "ok: true" in out
    assert "n: 42" in out
    assert "nothing: null" in out
    assert "tags: a, b" in out
    assert "empty_list: null" in out


def test_roundtrip_preserves_known_keys():
    original = {"id": "PRJ-001", "title": "Hello", "priority": "p1"}
    serialized = serialize_frontmatter(original, body="X")
    reparsed, body = parse_frontmatter(serialized)
    assert reparsed == original
    assert body.strip() == "X"


def test_parse_skips_comments_and_blank_lines():
    content = """---
# this is a comment
id: PRJ-001

title: T
---
"""
    data, _ = parse_frontmatter(content)
    assert data == {"id": "PRJ-001", "title": "T"}

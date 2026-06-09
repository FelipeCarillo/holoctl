"""Round-trip tests for frontmatter parse/serialize and Board._patch_ticket_md.

Covers task 3.1 (patch via parse/serialize, body preserved byte-for-byte,
absent-field add) and task 3.2 (colons in values, quoted strings, lists).
"""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.board import Board
from holoctl.lib.markdown import parse_frontmatter, serialize_frontmatter


def _roundtrip(data: dict) -> dict:
    serialized = serialize_frontmatter(data, body="# Body\n")
    reparsed, _ = parse_frontmatter(serialized)
    return reparsed


def test_source_url_roundtrip_unquoted():
    data = {"source_url": "https://example.com/issues/42?x=1"}
    assert _roundtrip(data) == data


def test_source_url_roundtrip_quoted_in_source():
    content = '---\nsource_url: "https://example.com/x:y"\n---\nbody'
    fm, _ = parse_frontmatter(content)
    assert fm["source_url"] == "https://example.com/x:y"


def test_title_with_colon_roundtrips():
    data = {"title": "Metrics: phase 1"}
    out = _roundtrip(data)
    assert out["title"] == "Metrics: phase 1"


def test_title_with_trailing_colon_is_quoted_and_roundtrips():
    data = {"title": "TODO:"}
    serialized = serialize_frontmatter(data)
    # trailing colon must be quoted so it isn't read as an empty mapping
    assert 'title: "TODO:"' in serialized
    reparsed, _ = parse_frontmatter(serialized)
    assert reparsed["title"] == "TODO:"


def test_list_roundtrips_inline_array():
    content = "---\ntags: [a, b, c]\n---\n"
    fm, _ = parse_frontmatter(content)
    assert fm["tags"] == ["a", "b", "c"]


def test_list_item_with_colon_in_quotes():
    content = '---\nitems: ["a:1", "b:2"]\n---\n'
    fm, _ = parse_frontmatter(content)
    assert fm["items"] == ["a:1", "b:2"]


def test_comma_joined_list_roundtrips():
    data = {"agent": ["developer", "reviewer"]}
    out = _roundtrip(data)
    assert out["agent"] == "developer, reviewer"  # board reads via comma-split


def test_null_sentinel_serializes_bare():
    # The board uses the literal string "null" as its None sentinel.
    assert "x: null" in serialize_frontmatter({"x": "null"})
    assert "y: null" in serialize_frontmatter({"y": None})


def test_leading_whitespace_value_is_preserved():
    data = {"x": " leading"}
    out = _roundtrip(data)
    assert out["x"] == " leading"


# ----- Board._patch_ticket_md -------------------------------------------------


def _make_board(workspace: Path, workspace_config: dict) -> Board:
    return Board(workspace, workspace_config)


def test_patch_preserves_body_byte_for_byte(workspace: Path, workspace_config: dict):
    board = _make_board(workspace, workspace_config)
    t = board.add({"title": "X", "body": "# Custom\n\nLine one\nLine: two\n- [ ] task\n"})
    md_path = workspace / ".holoctl" / "board" / t["file"]
    before = md_path.read_text(encoding="utf-8")
    _, body_before = parse_frontmatter(before)

    board.set(t["id"], "priority", "p1")

    after = md_path.read_text(encoding="utf-8")
    fm_after, body_after = parse_frontmatter(after)
    # Body content is preserved (modulo the single frontmatter-block separator
    # newline, which is block formatting, not body content).
    assert body_after.lstrip("\n") == body_before.lstrip("\n")
    assert "Line: two" in body_after
    assert "- [ ] task" in body_after
    assert fm_after["priority"] == "p1"

    # And a second patch is idempotent — body does not grow.
    board.set(t["id"], "priority", "p2")
    _, body_after2 = parse_frontmatter(md_path.read_text(encoding="utf-8"))
    assert body_after2 == body_after


def test_patch_adds_absent_field(workspace: Path, workspace_config: dict):
    board = _make_board(workspace, workspace_config)
    t = board.add({"title": "X"})
    md_path = workspace / ".holoctl" / "board" / t["file"]

    # Strip a field from the .md to simulate a legacy file missing `sprint`.
    fm, body = parse_frontmatter(md_path.read_text(encoding="utf-8"))
    fm.pop("sprint", None)
    md_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")
    assert "sprint:" not in md_path.read_text(encoding="utf-8")

    board.set(t["id"], "sprint", "S1")

    fm2, _ = parse_frontmatter(md_path.read_text(encoding="utf-8"))
    assert fm2["sprint"] == "S1"


def test_patch_does_not_clobber_body_line_starting_with_key(
    workspace: Path, workspace_config: dict
):
    # A body line literally `status: in the README` must not be rewritten by a
    # status patch (the old re.sub bug).
    board = _make_board(workspace, workspace_config)
    t = board.add({"title": "X", "body": "# Notes\n\nstatus: keep this text\n"})
    md_path = workspace / ".holoctl" / "board" / t["file"]

    board.move(t["id"], "doing")

    _, body = parse_frontmatter(md_path.read_text(encoding="utf-8"))
    assert "status: keep this text" in body
    fm, _ = parse_frontmatter(md_path.read_text(encoding="utf-8"))
    assert fm["status"] == "doing"

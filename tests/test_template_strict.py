"""Task 3.6 — strict template resolution.

`resolve_template(..., strict=True)` must raise on an unresolved placeholder
(surfacing typos) while the lenient default leaves the literal `{{...}}` intact.
The compile path runs in strict mode against a complete config.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from holoctl.lib.compiler.template import (
    UnresolvedPlaceholderError,
    resolve_template,
)
from holoctl.lib.compiler import compile_project
from holoctl.lib.config import get_defaults


def test_lenient_leaves_unknown_placeholder_literal():
    out = resolve_template("hello {{project.nope}} world", {"project": {}})
    assert out == "hello {{project.nope}} world"


def test_strict_raises_on_unknown_placeholder():
    with pytest.raises(UnresolvedPlaceholderError) as exc:
        resolve_template("a {{project.nope}} b", {"project": {}}, strict=True)
    assert "project.nope" in str(exc.value)


def test_strict_resolves_known_placeholders():
    config = {"project": {"name": "Foo"}}
    assert resolve_template("hi {{project.name}}", config, strict=True) == "hi Foo"


def test_strict_reports_all_distinct_unresolved_keys():
    with pytest.raises(UnresolvedPlaceholderError) as exc:
        resolve_template("{{a.x}} {{b.y}} {{a.x}}", {}, strict=True)
    msg = str(exc.value)
    assert "a.x" in msg and "b.y" in msg
    # De-duped: a.x appears once in the message.
    assert msg.count("a.x") == 1


def test_strict_no_placeholders_is_noop():
    assert resolve_template("plain text", {}, strict=True) == "plain text"


# ----- Escape hatches (review follow-up) ---------------------------------------
#
# Strict mode runs over user-authored content (instructions.md, commands,
# skills, rules). Literal `{{...}}` prose needs a way through the compile:
#   1. `${{ ... }}` (foreign templating, e.g. GitHub Actions) passes untouched.
#   2. `\{{...}}` is an explicit escape that emits literal `{{...}}`.


def test_dollar_prefixed_placeholder_passes_through_strict():
    text = "run: echo ${{ secrets.GITHUB_TOKEN }} on ${{ matrix.os }}"
    assert resolve_template(text, {}, strict=True) == text


def test_dollar_prefixed_placeholder_passes_through_lenient():
    text = "uses ${{ github.ref }} here"
    assert resolve_template(text, {}) == text


def test_backslash_escape_emits_literal_braces_strict():
    out = resolve_template(r"docs: \{{not.a.key}} stays literal", {}, strict=True)
    assert out == "docs: {{not.a.key}} stays literal"


def test_backslash_escape_emits_literal_braces_lenient():
    out = resolve_template(r"\{{anything}}", {})
    assert out == "{{anything}}"


def test_escaped_and_real_placeholders_mix():
    config = {"project": {"name": "Foo"}}
    out = resolve_template(r"\{{project.name}} = {{project.name}}", config, strict=True)
    assert out == "{{project.name}} = Foo"


def test_strict_error_hints_at_escape_syntax():
    with pytest.raises(UnresolvedPlaceholderError) as exc:
        resolve_template("{{definitely.a.typo}}", {}, strict=True)
    assert "\\{{" in str(exc.value)


# ----- Missing key vs present-but-null (review follow-up) ----------------------


def test_strict_distinguishes_null_value_from_missing_key():
    config = {"board": {"wipLimit": None}}
    with pytest.raises(UnresolvedPlaceholderError) as exc:
        resolve_template("{{board.wipLimit}} {{board.nope}}", config, strict=True)
    msg = str(exc.value)
    # The null-valued key is reported as such, not as an unknown placeholder.
    assert "board.wipLimit" in msg and "null" in msg
    assert "board.nope" in msg and "unresolved" in msg


def test_lenient_leaves_null_valued_placeholder_literal():
    out = resolve_template("{{board.wipLimit}}", {"board": {"wipLimit": None}})
    assert out == "{{board.wipLimit}}"


def _seed(root: Path) -> dict:
    holoctl = root / ".holoctl"
    (holoctl / "agents").mkdir(parents=True, exist_ok=True)
    (holoctl / "commands").mkdir(parents=True, exist_ok=True)
    (holoctl / "agents" / "boardmaster.md").write_text(
        "---\nname: boardmaster\ndescription: bm\n---\n# bm body\n", encoding="utf-8"
    )
    (holoctl / "instructions.md").write_text("# Project\n\nseed.\n", encoding="utf-8")
    return get_defaults()


def test_compile_path_uses_strict_and_rejects_typo(tmp_path: Path):
    """A typo'd placeholder in a holoctl source surfaces at compile time."""
    config = _seed(tmp_path)
    # Plant a command with a bogus placeholder key.
    (tmp_path / ".holoctl" / "commands" / "bad.md").write_text(
        "---\nname: bad\n---\nuse {{project.nmae}} here\n", encoding="utf-8"
    )
    with pytest.raises(UnresolvedPlaceholderError):
        compile_project(tmp_path, config, "claude")


def test_compile_path_resolves_derived_keys(tmp_path: Path):
    """Derived placeholders (boardCliBin, statusesJoined) must resolve under
    strict mode — the compile path enriches the config before resolving."""
    config = _seed(tmp_path)
    (tmp_path / ".holoctl" / "commands" / "derived.md").write_text(
        "---\nname: derived\n---\n"
        "bin={{commands.boardCliBin}} "
        "stat={{board.statusesJoined}} "
        "prio={{board.prioritiesJoined}}\n",
        encoding="utf-8",
    )
    # Should not raise.
    compile_project(tmp_path, config, "claude")
    out = (tmp_path / ".claude" / "commands" / "derived.md").read_text(encoding="utf-8")
    assert "{{" not in out

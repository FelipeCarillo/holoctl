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

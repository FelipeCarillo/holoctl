"""F5 — Codex parity: `.codex/AGENTS.override.md` now inlines a memory summary
and the active personas, so Codex isn't left with strictly less context than
the Claude/Copilot targets (its only project surface is AGENTS[.override].md)."""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.compiler.codex import compile_codex
from holoctl.lib.config import get_defaults
from holoctl.lib.memory import Memory


def _config() -> dict:
    cfg = get_defaults()
    cfg["project"]["name"] = "CX"
    cfg["project"]["prefix"] = "CX"
    return cfg


def _seed(root: Path) -> None:
    (root / ".holoctl" / "agents").mkdir(parents=True, exist_ok=True)
    (root / ".holoctl" / "instructions.md").write_text(
        "# CX\n\nbase instructions.\n", encoding="utf-8"
    )
    (root / ".holoctl" / "agents" / "boardmaster.md").write_text(
        "---\nname: boardmaster\ndescription: Owns the board schema\n---\n# body\n",
        encoding="utf-8",
    )


def _override(root: Path) -> str:
    return (root / ".codex" / "AGENTS.override.md").read_text(encoding="utf-8")


def test_override_includes_personas(tmp_path: Path):
    _seed(tmp_path)
    compile_codex(tmp_path, _config())
    body = _override(tmp_path)
    assert "## Personas" in body
    assert "boardmaster" in body
    assert "Owns the board schema" in body


def test_override_includes_memory_index_and_topics(tmp_path: Path):
    _seed(tmp_path)
    mem = Memory(tmp_path)
    mem.ensure_seed("CX")
    mem.add_topic(
        "deploy", body="Use blue/green.", scope="lazy",
        description="How we ship to prod",
    )
    compile_codex(tmp_path, _config())
    body = _override(tmp_path)
    assert "## Workspace memory" in body
    assert "### Memory topics" in body
    assert "deploy" in body
    assert "How we ship to prod" in body


def test_override_omits_sections_when_absent(tmp_path: Path):
    # Only instructions, no agents dir, no memory → no Personas / Memory sections.
    (tmp_path / ".holoctl").mkdir(parents=True)
    (tmp_path / ".holoctl" / "instructions.md").write_text("# CX\n\njust this.\n", encoding="utf-8")
    compile_codex(tmp_path, _config())
    body = _override(tmp_path)
    assert "## Personas" not in body
    assert "## Workspace memory" not in body
    assert "just this." in body


def test_override_is_idempotent(tmp_path: Path):
    _seed(tmp_path)
    Memory(tmp_path).ensure_seed("CX")
    compile_codex(tmp_path, _config())
    first = _override(tmp_path)
    compile_codex(tmp_path, _config())
    assert _override(tmp_path) == first

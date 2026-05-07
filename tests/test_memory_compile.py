"""Tests for per-target memory emission (compiler/memory_emit.py)."""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.compiler import memory_emit
from holoctl.lib.memory import Memory


def _seed(tmp_path: Path) -> Memory:
    mem = Memory(tmp_path)
    mem.ensure_seed("TestProj")
    mem.ensure_gitignore()
    mem.add_topic(
        "decisions",
        body="2026-05-04 chose stdio over HTTP daemon for MCP.",
        scope="lazy",
        description="Architectural decisions log",
    )
    mem.add_topic(
        "api-conventions",
        body="REST endpoints use kebab-case in paths.",
        scope="glob",
        globs=["src/api/**", "tests/api/**"],
    )
    mem.add_topic(
        "always-rules",
        body="Never log credentials.",
        scope="always_on",
    )
    return mem


def test_emit_claude_writes_index_and_topic_skills(tmp_path: Path):
    _seed(tmp_path)
    paths = memory_emit.emit_claude(tmp_path)
    paths_set = set(paths)
    assert ".claude/skills/holoctl-memory/SKILL.md" in paths_set
    assert ".claude/skills/holoctl-memory-decisions/SKILL.md" in paths_set
    assert ".claude/skills/holoctl-memory-api-conventions/SKILL.md" in paths_set
    assert ".claude/skills/holoctl-memory-always-rules/SKILL.md" in paths_set


def test_emit_claude_lazy_topic_has_description(tmp_path: Path):
    _seed(tmp_path)
    memory_emit.emit_claude(tmp_path)
    body = (
        tmp_path / ".claude/skills/holoctl-memory-decisions/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "name: holoctl-memory-decisions" in body
    assert "Architectural decisions log" in body


def test_emit_claude_glob_topic_has_paths(tmp_path: Path):
    _seed(tmp_path)
    memory_emit.emit_claude(tmp_path)
    body = (
        tmp_path / ".claude/skills/holoctl-memory-api-conventions/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "paths:" in body
    assert "src/api/**" in body


def test_emit_cursor_writes_mdc_with_correct_modes(tmp_path: Path):
    _seed(tmp_path)
    paths = memory_emit.emit_cursor(tmp_path)
    paths_set = set(paths)
    assert ".cursor/rules/holoctl-memory.mdc" in paths_set
    assert ".cursor/rules/holoctl-memory-decisions.mdc" in paths_set

    index = (tmp_path / ".cursor/rules/holoctl-memory.mdc").read_text(encoding="utf-8")
    assert "alwaysApply: true" in index

    glob_topic = (
        tmp_path / ".cursor/rules/holoctl-memory-api-conventions.mdc"
    ).read_text(encoding="utf-8")
    assert "globs:" in glob_topic
    assert "src/api/**" in glob_topic

    lazy_topic = (
        tmp_path / ".cursor/rules/holoctl-memory-decisions.mdc"
    ).read_text(encoding="utf-8")
    assert "description:" in lazy_topic


def test_emit_windsurf_uses_native_triggers(tmp_path: Path):
    _seed(tmp_path)
    memory_emit.emit_windsurf(tmp_path)
    index = (
        tmp_path / ".windsurf/rules/holoctl-memory.md"
    ).read_text(encoding="utf-8")
    assert "trigger: always_on" in index

    decisions = (
        tmp_path / ".windsurf/rules/holoctl-memory-decisions.md"
    ).read_text(encoding="utf-8")
    assert "trigger: model_decision" in decisions

    api = (
        tmp_path / ".windsurf/rules/holoctl-memory-api-conventions.md"
    ).read_text(encoding="utf-8")
    assert "trigger: glob" in api


def test_emit_windsurf_does_not_touch_user_memories_dir(tmp_path: Path):
    """Windsurf's auto-memory dir (~/.codeium/...) is NOT a target —
    we write to .windsurf/rules/ in the workspace only (item 11/durability)."""
    _seed(tmp_path)
    paths = memory_emit.emit_windsurf(tmp_path)
    for p in paths:
        assert "memories" not in p
        assert ".windsurf/rules/" in p


def test_emit_copilot_uses_apply_to_glob(tmp_path: Path):
    _seed(tmp_path)
    memory_emit.emit_copilot(tmp_path)
    api = (
        tmp_path
        / ".github/instructions/holoctl-memory-api-conventions.instructions.md"
    ).read_text(encoding="utf-8")
    assert "applyTo:" in api
    assert "src/api/**" in api


def test_emit_devin_writes_rules_dir(tmp_path: Path):
    _seed(tmp_path)
    paths = memory_emit.emit_devin(tmp_path)
    assert ".devin/rules/holoctl-memory.md" in paths
    assert ".devin/rules/holoctl-memory-decisions.md" in paths


def test_emit_no_memory_dir_returns_empty(tmp_path: Path):
    """Compilers must be tolerant of workspaces without memory yet."""
    for emit in (
        memory_emit.emit_claude,
        memory_emit.emit_cursor,
        memory_emit.emit_windsurf,
        memory_emit.emit_copilot,
        memory_emit.emit_devin,
    ):
        assert emit(tmp_path) == []


def test_claude_memory_reference_block_mentions_index_and_cli():
    block = memory_emit.claude_memory_reference_block()
    assert "@.holoctl/memory/MEMORY.md" in block
    assert "hctl memory" in block

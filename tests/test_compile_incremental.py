"""Task 4.4 — incremental compile skips unchanged disk writes.

Compiling twice with no source change must NOT rewrite any owned output: the
manifest records the (unchanged) hash but the on-disk bytes — and therefore the
mtime — are left untouched. This avoids churning git diffs / mtimes.
"""
from __future__ import annotations

from pathlib import Path

from holoctl.lib.compiler import compile_project
from holoctl.lib.config import get_defaults


def _seed(root: Path) -> dict:
    holoctl = root / ".holoctl"
    (holoctl / "agents").mkdir(parents=True, exist_ok=True)
    (holoctl / "commands").mkdir(parents=True, exist_ok=True)
    (holoctl / "context").mkdir(parents=True, exist_ok=True)
    (holoctl / "agents" / "boardmaster.md").write_text(
        "---\nname: boardmaster\ndescription: bm\n---\n# bm body\n", encoding="utf-8"
    )
    (holoctl / "agents" / "dev.md").write_text(
        "---\nname: dev\ndescription: dev\n---\n# dev body\n", encoding="utf-8"
    )
    (holoctl / "commands" / "status.md").write_text(
        "---\nname: status\ndescription: st\n---\n# status body\n", encoding="utf-8"
    )
    (holoctl / "instructions.md").write_text("# Project\n\nseed.\n", encoding="utf-8")
    (holoctl / "context" / "objective.md").write_text("obj.\n", encoding="utf-8")
    return get_defaults()


def _output_mtimes(root: Path) -> dict[str, int]:
    """mtime_ns of every generated file under .claude/, CLAUDE.md, AGENTS.md."""
    mtimes: dict[str, int] = {}
    for base in (".claude",):
        d = root / base
        if d.exists():
            for p in sorted(d.rglob("*")):
                if p.is_file():
                    mtimes[p.relative_to(root).as_posix()] = p.stat().st_mtime_ns
    for top in ("CLAUDE.md",):
        p = root / top
        if p.exists():
            mtimes[top] = p.stat().st_mtime_ns
    return mtimes


def test_second_compile_does_not_touch_output_mtimes(tmp_path: Path):
    config = _seed(tmp_path)
    compile_project(tmp_path, config, "claude")

    before = _output_mtimes(tmp_path)
    assert before, "expected generated outputs after first compile"

    # Recompile with no source change.
    compile_project(tmp_path, config, "claude")
    after = _output_mtimes(tmp_path)

    # No output file's mtime changed on the second compile.
    changed = {k for k in before if before[k] != after.get(k)}
    assert not changed, f"these outputs were rewritten on an unchanged compile: {changed}"


def test_changed_source_still_rewrites_only_that_file(tmp_path: Path):
    """The incremental skip must not block a legitimate update: change one
    source, recompile, and only that output's mtime moves."""
    config = _seed(tmp_path)
    compile_project(tmp_path, config, "claude")
    before = _output_mtimes(tmp_path)

    # Mutate one source.
    (tmp_path / ".holoctl" / "agents" / "dev.md").write_text(
        "---\nname: dev\ndescription: dev\n---\n# dev body CHANGED\n", encoding="utf-8"
    )
    compile_project(tmp_path, config, "claude")
    after = _output_mtimes(tmp_path)

    dev_out = ".claude/agents/dev.md"
    assert after[dev_out] != before[dev_out], "changed source was not rewritten"
    # Everything else stayed put.
    others = {k for k in before if k != dev_out and before[k] != after.get(k)}
    assert not others, f"unchanged outputs were churned: {others}"

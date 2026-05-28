from __future__ import annotations
from pathlib import Path

from .agents import compile_agents
from .claude import compile_claude
from .manifest import CompileLedger

_COMPILERS = {
    # holoctl maintains a deep, native compiler only for Claude Code. Every
    # other assistant is served by the `holoctl-foreign-bootstrap` skill, which
    # teaches it to read `.holoctl/` and generate its own config dir.
    #
    # `agents` is NOT a second native compiler — it emits a minimal AGENTS.md
    # discovery shim (the cross-tool convention) that points any non-Claude
    # assistant at that bootstrap skill, plus the bootstrap body itself at
    # `.holoctl/foreign-bootstrap.md`.
    "agents": compile_agents,
    "claude": compile_claude,
}


def compile_project(
    project_root: Path,
    config: dict,
    target: str,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Compile one *target*, scoping the manifest ledger to that target.

    A fresh, target-scoped ledger is built per call (compile drives this once
    per target). The compiler writes through it; afterwards we prune orphans
    *belonging to this target* and finalize — merge-preserving other targets'
    manifest entries so a multi-target compile doesn't clobber its siblings'
    bookkeeping.

    Returns ``{"files", "skipped", "removed", "migrated"}``.
    """
    compiler = _COMPILERS.get(target)
    if not compiler:
        available = ", ".join(_COMPILERS)
        raise ValueError(f"Unknown compile target: {target}. Available: {available}")

    from ... import __version__

    ledger = CompileLedger.for_target(project_root, target, dry_run=dry_run, force=force)
    result = compiler(project_root, config, dry_run=dry_run, ledger=ledger)
    ledger.prune_orphans()
    ledger.finalize(holoctl_version=__version__)

    # `ledger.skipped` is authoritative (compilers append CLAUDE.md preserve
    # notes there too); read it AFTER prune so orphan-divergence notes are
    # included.
    out: dict = {
        "files": result.get("files", []),
        "skipped": ledger.skipped,
        "removed": ledger.removed,
        "migrated": ledger.migrated,
    }
    return out

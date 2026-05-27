from __future__ import annotations
from pathlib import Path

from .agents import compile_agents
from .claude import compile_claude

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


def compile_project(project_root: Path, config: dict, target: str, dry_run: bool = False) -> dict:
    compiler = _COMPILERS.get(target)
    if not compiler:
        available = ", ".join(_COMPILERS)
        raise ValueError(f"Unknown compile target: {target}. Available: {available}")
    return compiler(project_root, config, dry_run=dry_run)

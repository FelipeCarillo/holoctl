from __future__ import annotations
from pathlib import Path

from .agents import compile_agents
from .claude import compile_claude
from .codex import compile_codex
from .copilot import compile_copilot

_COMPILERS = {
    # Cross-tool universal: AGENTS.md respected by Aider / Zed / Junie /
    # Jules / Factory / goose and other agents.md-aware assistants. Codex
    # also reads AGENTS.md but has additional first-class surfaces
    # (.codex/config.toml for MCP, .codex/AGENTS.override.md) so it gets a
    # dedicated target on top of the cross-tool one.
    "agents": compile_agents,
    "claude": compile_claude,
    "copilot": compile_copilot,
    "codex": compile_codex,
}


def compile_project(project_root: Path, config: dict, target: str, dry_run: bool = False) -> dict:
    compiler = _COMPILERS.get(target)
    if not compiler:
        available = ", ".join(_COMPILERS)
        raise ValueError(f"Unknown compile target: {target}. Available: {available}")
    return compiler(project_root, config, dry_run=dry_run)

from __future__ import annotations
from pathlib import Path

from .claude import compile_claude
from .cursor import compile_cursor
from .windsurf import compile_windsurf
from .copilot import compile_copilot
from .generic import compile_generic

_COMPILERS = {
    "claude": compile_claude,
    "cursor": compile_cursor,
    "windsurf": compile_windsurf,
    "copilot": compile_copilot,
    "generic": compile_generic,
}


def compile_project(project_root: Path, config: dict, target: str, dry_run: bool = False) -> dict:
    compiler = _COMPILERS.get(target)
    if not compiler:
        available = ", ".join(_COMPILERS)
        raise ValueError(f"Unknown compile target: {target}. Available: {available}")
    return compiler(project_root, config, dry_run=dry_run)

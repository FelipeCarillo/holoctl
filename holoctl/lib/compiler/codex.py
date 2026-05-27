"""Compile target: OpenAI Codex CLI.

Codex reads two project-scoped surfaces (per the official docs):

  - ``AGENTS.md`` (and ``AGENTS.override.md``) anywhere from the repo root
    down to the cwd. The cross-tool ``agents`` target already emits the root
    ``AGENTS.md``; this compiler emits a Codex-scoped override at
    ``.codex/AGENTS.override.md`` so the user can keep Codex-specific
    instructions without polluting the universal file.
  - ``.codex/config.toml`` — loaded when the project is trusted. Used for
    ``[mcp_servers.<id>]`` tables. We declare the holoctl stdio MCP server
    here (delegated to ``mcp_emit.emit_codex``).

Codex has no documented per-project surface for slash commands or memory
rules — those live at user-level (``~/.codex/skills/`` etc.) which is
outside ``hctl init``'s scope. Cross-tool ``AGENTS.md`` carries the
project context in a format Codex understands natively.
"""
from __future__ import annotations
from pathlib import Path

from . import mcp_emit
from ._safe_write import HEADER as _HEADER, safe_write_md
from .template import resolve_template


def compile_codex(project_root: Path, config: dict, dry_run: bool = False) -> dict:
    files: list[str] = []
    skipped: list[dict] = []

    instructions_path = project_root / ".holoctl" / "instructions.md"
    if instructions_path.exists():
        content = instructions_path.read_text(encoding="utf-8")
        output = _HEADER + resolve_template(content, config)
        out_path = ".codex/AGENTS.override.md"
        if not dry_run:
            if safe_write_md(project_root / out_path, output, skipped=skipped):
                files.append(out_path)
        else:
            files.append(out_path)

    files.extend(mcp_emit.emit_codex(project_root, dry_run=dry_run))

    result = {"files": files}
    if skipped:
        result["skipped"] = skipped
    return result

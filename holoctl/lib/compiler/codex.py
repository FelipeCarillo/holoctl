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

Codex has no per-project surface for skills, subagents, or lazy memory like
Claude Code's ``.claude/`` tree. So, for parity, this compiler *inlines* a
summary of the workspace memory (the always-on index + a list of lazy topics)
and the active personas into ``AGENTS.override.md`` — the one channel Codex
reads — rather than leaving Codex with strictly less context than the other
targets.
"""
from __future__ import annotations
from pathlib import Path

from ..markdown import parse_frontmatter
from . import mcp_emit
from ._safe_write import HEADER as _HEADER, safe_write_md
from .template import resolve_template


def compile_codex(project_root: Path, config: dict, dry_run: bool = False) -> dict:
    files: list[str] = []
    skipped: list[dict] = []

    sections: list[str] = []
    instructions_path = project_root / ".holoctl" / "instructions.md"
    if instructions_path.exists():
        sections.append(
            resolve_template(instructions_path.read_text(encoding="utf-8"), config).strip()
        )

    mem_section = _memory_section(project_root)
    if mem_section:
        sections.append(mem_section)

    personas_section = _personas_section(project_root)
    if personas_section:
        sections.append(personas_section)

    # Empty input → empty output: only write the override when there's content.
    if sections:
        output = _HEADER + "\n\n".join(sections) + "\n"
        out_path = ".codex/AGENTS.override.md"
        if not dry_run:
            if safe_write_md(project_root / out_path, output, skipped=skipped):
                files.append(out_path)
        else:
            files.append(out_path)

    files.extend(mcp_emit.emit_codex(project_root, dry_run=dry_run))

    result: dict[str, object] = {"files": files}
    if skipped:
        result["skipped"] = skipped
    return result


def _memory_section(project_root: Path) -> str | None:
    """Inline the always-on memory index + a list of lazy topics for Codex.

    Codex can't lazy-load topic files the way Claude's skills do, so we surface
    the index verbatim (it's the always-on layer, kept short by design) and list
    the topics with their descriptions so Codex knows what to read on demand.
    """
    from ..memory import Memory

    mem = Memory(project_root)
    if not mem.dir.exists():
        return None
    index = mem.read_index().strip()
    topics = mem.list_topics()
    if not index and not topics:
        return None

    out = [
        "## Workspace memory",
        "",
        "Durable, cross-assistant memory lives in `.holoctl/memory/`. The "
        "always-on index follows; read individual topics on demand from "
        "`.holoctl/memory/topics/`.",
    ]
    if index:
        out += ["", index]
    if topics:
        out += ["", "### Memory topics", ""]
        for t in topics:
            desc = t.description or f"scope: {t.scope}"
            out.append(f"- **{t.name}** — {desc}")
    return "\n".join(out)


def _personas_section(project_root: Path) -> str | None:
    """List the active personas (name + description) for Codex.

    Codex has no subagent surface, but knowing the project's specialized roles
    lets it adopt the right mindset when a task matches one.
    """
    agents_dir = project_root / ".holoctl" / "agents"
    if not agents_dir.exists():
        return None
    personas: list[tuple[str, str]] = []
    for f in sorted(agents_dir.glob("*.md")):
        fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        name = str(fm.get("name") or f.stem)
        desc = str(fm.get("description") or "")
        personas.append((name, desc))
    if not personas:
        return None

    out = [
        "## Personas",
        "",
        "Specialized roles defined for this project (`.holoctl/agents/`). Codex "
        "has no subagent surface, but adopt the relevant role's mindset when a "
        "task matches:",
        "",
    ]
    for name, desc in personas:
        out.append(f"- **{name}** — {desc}" if desc else f"- **{name}**")
    return "\n".join(out)

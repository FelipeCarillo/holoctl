"""Compile target: minimal AGENTS.md discovery shim + foreign-bootstrap body.

holoctl maintains a deep, native compiler only for Claude Code. Every other
assistant is served by the `holoctl-foreign-bootstrap` skill rather than a
bespoke per-tool compiler. This target emits the two files that make that work:

  1. A **minimal `AGENTS.md`** at the repo root — the cross-tool convention
     ([agents.md](https://agents.md/)) that every non-Claude assistant reads.
     It no longer mirrors objective/architecture/conventions; it just points a
     foreign assistant at the bootstrap below.
  2. **`.holoctl/foreign-bootstrap.md`** — the bootstrap skill body (frontmatter
     stripped, per-tool format hints inlined) at a tool-neutral path a foreign
     assistant can read without knowing about `.claude/skills/`.

Both carry holoctl's generated `HEADER`, so the hand-edit guard and
`hctl doctor --compile-drift` treat them like any other compiled output.
"""
from __future__ import annotations

from pathlib import Path

from ._safe_write import HEADER as _HEADER, safe_write_md
from .template import resolve_template

_BOOTSTRAP_REL = ".holoctl/foreign-bootstrap.md"
_SKILL_NAME = "holoctl-foreign-bootstrap"


def compile_agents(project_root: Path, config: dict, dry_run: bool = False) -> dict:
    """Emit the minimal `AGENTS.md` shim + `.holoctl/foreign-bootstrap.md`.

    Idempotent: re-running produces identical content for unchanged inputs.
    """
    files: list[str] = []
    skipped: list[dict] = []

    project_name = config.get("project", {}).get("name") or project_root.name
    agents_md = _HEADER + resolve_template(_agents_shim(project_name), config)
    _emit(project_root / "AGENTS.md", "AGENTS.md", agents_md, files, skipped, dry_run)

    bootstrap = _HEADER + _foreign_bootstrap_body()
    _emit(project_root / _BOOTSTRAP_REL, _BOOTSTRAP_REL, bootstrap, files, skipped, dry_run)

    result: dict[str, object] = {"files": files}
    if skipped:
        result["skipped"] = skipped
    return result


def _emit(
    path: Path,
    rel: str,
    content: str,
    files: list[str],
    skipped: list[dict],
    dry_run: bool,
) -> None:
    if dry_run:
        files.append(rel)
        return
    if safe_write_md(path, content, skipped=skipped):
        files.append(rel)


def _agents_shim(project_name: str) -> str:
    return f"""# AGENTS.md — {project_name}

This repository is managed by **holoctl**. The canonical source of truth lives
in `.holoctl/` (tool-neutral). The `hctl` CLI (on PATH) compiles it into Claude
Code's native config only.

## If you are Claude Code

Your native config is already materialized in `.claude/` and `CLAUDE.md`. Use
those — you can ignore the rest of this file.

## If you are any other assistant (Copilot, Codex, Cursor, Aider, Zed, …)

holoctl does not maintain a compiler for you. Bootstrap yourself:

1. Read and follow **`.holoctl/foreign-bootstrap.md`** — it explains how to read
   `.holoctl/` and generate your own native config dir from it.
2. Quick map of where your output goes: Copilot → `.github/`; Codex → `.codex/`;
   Cursor → `.cursor/rules/`; generic AGENTS.md-aware tools → this file.

## Hard rules

- Never edit `.holoctl/board/index.json` or `.holoctl/memory/MEMORY.md` by hand —
  they are derived. Use `hctl <subcommand>` (e.g. `hctl board add`).
- Treat any config you generate (`.github/`, `.codex/`, `.cursor/`) as derived;
  regenerate it from `.holoctl/` after changes instead of hand-editing.
"""


def _foreign_bootstrap_body() -> str:
    """The foreign-bootstrap skill body (frontmatter stripped) with its per-tool
    format hints inlined, so the standalone `.holoctl/foreign-bootstrap.md` is
    self-contained for an assistant that can't read `.claude/skills/`."""
    skill_root = _package_skill_dir(_SKILL_NAME)
    parts: list[str] = []
    skill_md = skill_root / "SKILL.md"
    if skill_md.exists():
        parts.append(_strip_frontmatter(skill_md.read_text(encoding="utf-8")).strip())
    hints = skill_root / "references" / "format-hints.md"
    if hints.exists():
        parts.append(hints.read_text(encoding="utf-8").strip())
    if not parts:
        return (
            "# holoctl foreign-bootstrap\n\n"
            "Read `.holoctl/` (instructions.md, context/, agents/, memory/, "
            "commands/) and materialize it into your tool's native config dir.\n"
        )
    return "\n\n---\n\n".join(parts) + "\n"


def _package_skill_dir(name: str) -> Path:
    try:
        from importlib.resources import files as _ires_files
        root = _ires_files("holoctl") / "templates" / "skills" / name
    except (ModuleNotFoundError, AttributeError):
        root = Path(__file__).resolve().parent.parent.parent / "templates" / "skills" / name
    return Path(str(root))


def _strip_frontmatter(raw: str) -> str:
    """Drop a leading YAML frontmatter block, if present."""
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end != -1:
            return raw[end + 5 :]
    return raw

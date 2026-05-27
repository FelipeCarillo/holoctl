"""`hctl adopt` — bring foreign Claude config under holoctl management.

A file under `.claude/` that holoctl did NOT generate (not in the manifest)
is **foreign** — authored by the user or another plugin/tool. ``hctl adopt``
copies a foreign agent/skill/command into `.holoctl/` (the source of truth)
and records the CURRENT `.claude/` file in the manifest as managed.

The manifest record is the load-bearing part: it makes the next ``hctl
compile`` recognise the `.claude/` file as **owned** (on-disk hash == recorded
hash) and overwrite it with the version compiled from `.holoctl/`, instead of
preserving it as foreign. Adoption never auto-compiles — it tells the user to
run ``hctl compile``.

Non-interactive (no blocking prompts):
  - no args        → PREVIEW unmanaged items, adopt nothing.
  - ``--all``      → adopt every unmanaged agent/skill/command.
  - ``--type T``   → adopt that type (optionally one ``--name``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ._console import console
from .. import __version__
from ..lib.compiler.claude import _MODEL_MAP, _TOOL_MAP
from ..lib.compiler import manifest
from ..lib.config import find_project_root
from ..lib.ecosystem import scan_unmanaged
from ..lib.markdown import parse_frontmatter

_VALID_TYPES = ("agent", "skill", "command")
# Support subdirs copied verbatim for a skill (mirrors the compiler's set).
_SKILL_SUPPORT_DIRS = ("references", "scripts", "templates")


# ---------------------------------------------------------------------------
# Reverse frontmatter maps (derived from the forward maps — single source of
# truth). Forward maps live in compiler/claude.py.
# ---------------------------------------------------------------------------


def _build_reverse_tool_map() -> dict[str, str]:
    """Claude tool TOKEN → holoctl category.

    ``_TOOL_MAP`` values like ``"Grep, Glob"`` map one category to several
    tokens; split on ``", "`` and map each token back to its category.
    """
    reverse: dict[str, str] = {}
    for category, tokens in _TOOL_MAP.items():
        for token in str(tokens).split(", "):
            token = token.strip()
            if token:
                reverse[token] = category
    return reverse


_REVERSE_TOOL_MAP = _build_reverse_tool_map()
_REVERSE_MODEL_MAP = {claude: holo for holo, claude in _MODEL_MAP.items()}


def _reverse_tools(tools: object) -> list[str]:
    """Map a Claude ``tools`` value (list or comma string) → holoctl categories.

    Dedupe while preserving first-seen order; unknown tokens pass through
    unchanged. ``["Read","Grep","Glob","Edit","Write","Bash"]`` →
    ``["read","search","edit","write","shell"]``.
    """
    if not tools:
        return []
    if isinstance(tools, list):
        tokens = [str(t).strip() for t in tools]
    else:
        tokens = [t.strip() for t in str(tools).split(",")]
    out: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        category = _REVERSE_TOOL_MAP.get(tok, tok)
        if category not in out:
            out.append(category)
    return out


def _reverse_model(model: object) -> str | None:
    """Map a Claude model tier (haiku/sonnet/opus) → holoctl tier; passthrough unknown."""
    if not model:
        return None
    return _REVERSE_MODEL_MAP.get(str(model), str(model))


def _holoctl_agent_source(claude_text: str, name: str) -> str:
    """Build a `.holoctl/agents/<name>.md` from a Claude agent's content.

    Reverse-maps ``tools`` (→ categories) and ``model`` (→ tier), preserves
    ``name``/``description``/``paths``, and keeps the body verbatim.
    """
    data, body = parse_frontmatter(claude_text)
    lines = ["---", f"name: {data.get('name', name)}"]
    if data.get("description") is not None:
        lines.append(f"description: {data.get('description')}")

    categories = _reverse_tools(data.get("tools"))
    if categories:
        lines.append(f"tools: {', '.join(categories)}")

    tier = _reverse_model(data.get("model"))
    if tier:
        lines.append(f"model: {tier}")

    paths_val = data.get("paths")
    if paths_val:
        if isinstance(paths_val, list):
            lines.append(f"paths: {', '.join(str(p) for p in paths_val)}")
        else:
            lines.append(f"paths: {paths_val}")

    lines.append("---")
    return "\n".join(lines) + "\n" + body


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _require_root() -> Path:
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `hctl init` first.[/red]")
        raise typer.Exit(1)
    return root


def _preview(unmanaged: dict) -> None:
    """Print all unmanaged items grouped by type and how to adopt them."""
    agents = unmanaged["agents"]
    commands = unmanaged["commands"]
    skills = unmanaged["skills"]
    mcp = unmanaged["mcp_servers"]

    total = len(agents) + len(commands) + len(skills)
    console.print("\n  [bold]hctl adopt[/bold]  [dim](preview — nothing adopted)[/dim]\n")

    if not total and not mcp:
        console.print("  [green]No foreign config found. Everything is managed by holoctl.[/green]\n")
        return

    def _group(label: str, items: list[str]) -> None:
        if items:
            console.print(f"  [bold]{label}[/bold] [dim]({len(items)})[/dim]")
            for name in items:
                console.print(f"    [cyan]{name}[/cyan]")

    _group("Agents", agents)
    _group("Commands", commands)
    _group("Skills", skills)

    if mcp:
        console.print(f"  [bold]MCP servers[/bold] [dim]({len(mcp)} — external, not adoptable)[/dim]")
        for name in mcp:
            console.print(f"    [dim]{name}[/dim]")

    if total:
        console.print(
            "\n  Re-run with [bold]--all[/bold] to adopt everything, or "
            "[bold]--type {agent,skill,command}[/bold] [dim](optionally "
            "--name <x>)[/dim] to adopt selectively.\n"
        )
    else:
        console.print(
            "\n  [dim]Only external MCP servers found — those are configured "
            "in .mcp.json / .claude/settings.json, not adoptable.[/dim]\n"
        )


def _adopt_agent(root: Path, name: str, force: bool, new_entries: dict) -> bool:
    """Adopt a foreign agent. Returns True if adopted."""
    claude_path = root / ".claude" / "agents" / f"{name}.md"
    src_path = root / ".holoctl" / "agents" / f"{name}.md"
    rel = f".claude/agents/{name}.md"
    if src_path.exists() and not force:
        console.print(f"  [yellow]skip[/yellow] agent {name} — .holoctl/agents/{name}.md already exists (pass --force)")
        return False

    claude_text = claude_path.read_text(encoding="utf-8")
    source = _holoctl_agent_source(claude_text, name)
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text(source, encoding="utf-8")

    # Record the CURRENT .claude/ content as managed (text channel) so the next
    # compile owns it.
    new_entries[rel] = {
        "sha256": manifest.sha256_text(claude_text),
        "source": f".holoctl/agents/{name}.md",
        "target": "claude",
    }
    console.print(f"  [green]adopted[/green] agent {name}")
    return True


def _adopt_command(root: Path, name: str, force: bool, new_entries: dict) -> bool:
    """Adopt a foreign command (verbatim copy). Returns True if adopted."""
    claude_path = root / ".claude" / "commands" / f"{name}.md"
    src_path = root / ".holoctl" / "commands" / f"{name}.md"
    rel = f".claude/commands/{name}.md"
    if src_path.exists() and not force:
        console.print(f"  [yellow]skip[/yellow] command {name} — .holoctl/commands/{name}.md already exists (pass --force)")
        return False

    text = claude_path.read_text(encoding="utf-8")
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text(text, encoding="utf-8")

    new_entries[rel] = {
        "sha256": manifest.sha256_text(text),
        "source": f".holoctl/commands/{name}.md",
        "target": "claude",
    }
    console.print(f"  [green]adopted[/green] command {name}")
    return True


def _adopt_skill(root: Path, name: str, force: bool, new_entries: dict) -> bool:
    """Adopt a foreign skill (SKILL.md + support dirs). Returns True if adopted."""
    claude_dir = root / ".claude" / "skills" / name
    src_dir = root / ".holoctl" / "skills" / name
    if src_dir.exists() and not force:
        console.print(f"  [yellow]skip[/yellow] skill {name} — .holoctl/skills/{name}/ already exists (pass --force)")
        return False

    skill_md = claude_dir / "SKILL.md"
    if not skill_md.exists():
        console.print(f"  [yellow]skip[/yellow] skill {name} — no SKILL.md found")
        return False

    src_dir.mkdir(parents=True, exist_ok=True)
    # SKILL.md — text channel (matches how the compiler emits it).
    skill_text = skill_md.read_text(encoding="utf-8")
    (src_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")
    new_entries[f".claude/skills/{name}/SKILL.md"] = {
        "sha256": manifest.sha256_text(skill_text),
        "source": f".holoctl/skills/{name}",
        "target": "claude",
    }

    # Support files — byte channel (matches the compiler's write_bytes path).
    for support in _SKILL_SUPPORT_DIRS:
        support_src = claude_dir / support
        if not support_src.exists():
            continue
        for sf in sorted(support_src.rglob("*")):
            if not sf.is_file():
                continue
            rel_within = sf.relative_to(claude_dir)
            dest = src_dir / rel_within
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = sf.read_bytes()
            dest.write_bytes(data)
            new_entries[f".claude/skills/{name}/{rel_within.as_posix()}"] = {
                "sha256": manifest.sha256_bytes(data),
                "source": f".holoctl/skills/{name}",
                "target": "claude",
            }
    console.print(f"  [green]adopted[/green] skill {name}")
    return True


def adopt_cmd(
    adopt_all: bool = typer.Option(False, "--all", help="Adopt every unmanaged agent/skill/command."),
    type_: Optional[str] = typer.Option(None, "--type", help=f"Adopt one type: {', '.join(_VALID_TYPES)}."),
    name: Optional[str] = typer.Option(None, "--name", help="With --type, adopt only this single item."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing .holoctl/<type>/<name> source."),
):
    """Bring foreign (externally-authored) Claude config under holoctl management.

    With no args this PREVIEWS the unmanaged items and adopts nothing. Use
    ``--all`` to adopt everything, or ``--type`` (+ optional ``--name``) to
    adopt selectively. After adopting, run ``hctl compile`` to regenerate the
    adopted files under holoctl management.
    """
    root = _require_root()
    unmanaged = scan_unmanaged(root)

    # No selection → preview, adopt nothing.
    if not adopt_all and type_ is None:
        _preview(unmanaged)
        return

    if type_ is not None and type_ not in _VALID_TYPES:
        console.print(f"[red]Invalid --type:[/red] {type_}. Valid: {', '.join(_VALID_TYPES)}.")
        raise typer.Exit(1)
    if name is not None and type_ is None:
        console.print("[red]--name requires --type.[/red]")
        raise typer.Exit(1)

    # Resolve the work list per type.
    agents = list(unmanaged["agents"])
    commands = list(unmanaged["commands"])
    skills = list(unmanaged["skills"])

    if type_ is not None:
        if type_ == "agent":
            commands, skills = [], []
            agents = _filter_by_name(agents, name, "agent")
        elif type_ == "command":
            agents, skills = [], []
            commands = _filter_by_name(commands, name, "command")
        elif type_ == "skill":
            agents, commands = [], []
            skills = _filter_by_name(skills, name, "skill")

    console.print("\n  [bold]hctl adopt[/bold]\n")

    new_entries: dict[str, dict] = {}
    n_agents = sum(_adopt_agent(root, a, force, new_entries) for a in agents)
    n_commands = sum(_adopt_command(root, c, force, new_entries) for c in commands)
    n_skills = sum(_adopt_skill(root, s, force, new_entries) for s in skills)

    if new_entries:
        manifest.add_entries(root, new_entries, holoctl_version=__version__)

    console.print(
        f"\n  [bold]adopted {n_agents} agent(s), {n_skills} skill(s), "
        f"{n_commands} command(s)[/bold]"
    )
    if n_agents or n_skills or n_commands:
        console.print(
            "  [cyan]→ run 'hctl compile' to regenerate the adopted files "
            "under holoctl management[/cyan]\n"
        )
    else:
        console.print("  [dim](nothing adopted)[/dim]\n")


def _filter_by_name(items: list[str], name: str | None, kind: str) -> list[str]:
    if name is None:
        return items
    if name not in items:
        console.print(f"[yellow]No unmanaged {kind} named {name!r}.[/yellow]")
        return []
    return [name]

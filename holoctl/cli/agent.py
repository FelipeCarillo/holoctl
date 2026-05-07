from __future__ import annotations
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.agent_library import (
    list_library_agents,
    load_library_agent,
    materialize_agent,
)
from ..lib.config import find_project_root, load_config
from ..lib.markdown import parse_frontmatter

app = typer.Typer(help="Manage agent definitions")


def _require_root() -> Path:
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `hctl init` first.[/red]")
        raise typer.Exit(1)
    return root


def _active_agent_names(agents_dir: Path) -> list[str]:
    if not agents_dir.exists():
        return []
    return sorted(p.stem for p in agents_dir.glob("*.md"))


def _summary_line(name: str, body: str) -> str:
    """Return a single padded line summarizing an agent .md body."""
    data, _ = parse_frontmatter(body)
    model = str(data.get("model", "standard"))
    trigger = str(data.get("trigger", "ticket"))
    desc = str(data.get("description", "")).strip().strip('"').strip("'")
    color = (
        "magenta" if model == "reasoning"
        else "dim" if model == "fast"
        else "cyan"
    )
    return (
        f"  [bold]{name:<16}[/bold] [{color}]{model:<10}[/{color}] "
        f"[dim]{trigger:<12}[/dim] {desc}"
    )


@app.command("list")
def agent_list():
    """List active personas in the workspace and the latent library catalog."""
    root = _require_root()
    agents_dir = root / ".holoctl" / "agents"
    active = _active_agent_names(agents_dir)
    library = list_library_agents()

    console.print("\n  [bold]Active[/bold]  [dim](.holoctl/agents/)[/dim]")
    if not active:
        console.print("  [dim](none)[/dim]")
    else:
        for name in active:
            body = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
            console.print(_summary_line(name, body))

    library_only = [n for n in library if n not in active]
    console.print(
        "\n  [bold]Library[/bold]  [dim](latent — `hctl agent add <name>` to "
        "activate)[/dim]"
    )
    if not library_only:
        console.print("  [dim](all library personas already active)[/dim]")
    else:
        for name in library_only:
            body = load_library_agent(name) or ""
            console.print(_summary_line(name, body))
    console.print("")


@app.command("add")
def agent_add(
    name: str = typer.Argument(..., help="Agent name"),
    from_template: Optional[str] = typer.Option(
        None,
        "--from",
        help="Base on an existing active agent (instead of the library entry).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing .holoctl/agents/<name>.md"
    ),
):
    """Activate a persona — either from the latent library or seeded blank.

    Resolution order:
      1. ``--from <other>`` — copy from an already-active agent.
      2. Library entry matching ``<name>`` — materialized with placeholders
         resolved against current config (``board.statusesJoined`` etc).
      3. Blank scaffold — used when the name doesn't exist in the library.
    """
    root = _require_root()
    agents_dir = root / ".holoctl" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    target_path = agents_dir / f"{name}.md"

    if target_path.exists() and not force:
        console.print(
            f"[yellow]Agent {name} already exists.[/yellow] "
            f"Pass --force to overwrite."
        )
        raise typer.Exit(1)

    if from_template:
        source = agents_dir / f"{from_template}.md"
        if not source.exists():
            console.print(
                f"[red]Template agent {from_template} not found in active "
                f".holoctl/agents/.[/red]"
            )
            raise typer.Exit(1)
        import re
        content = source.read_text(encoding="utf-8")
        content = re.sub(
            r"^(name:\s*).*$", rf"\g<1>{name}", content, flags=re.MULTILINE
        )
        target_path.write_text(content, encoding="utf-8")
        console.print(
            f"[green]Activated[/green] [bold]{name}[/bold] "
            f"[dim](copied from {from_template})[/dim]"
        )
        return

    config = load_config(root)
    library_body = materialize_agent(name, config)
    if library_body is not None:
        target_path.write_text(library_body, encoding="utf-8")
        console.print(
            f"[green]Activated[/green] [bold]{name}[/bold] "
            f"[dim](from library)[/dim]"
        )
        return

    target_path.write_text(_blank_agent_scaffold(name), encoding="utf-8")
    console.print(
        f"[green]Created[/green] [bold]{name}[/bold] "
        f"[dim](blank — fill in body)[/dim]"
    )


@app.command("remove")
def agent_remove(
    name: str = typer.Argument(..., help="Agent name to deactivate"),
):
    """Remove an active persona from .holoctl/agents/.

    Refuses to remove ``boardmaster`` (always-essential — board CLI relies on
    it). Other personas can be re-activated later via ``hctl agent add``.
    """
    if name == "boardmaster":
        console.print(
            "[red]Refusing to remove `boardmaster` — it's marked "
            "always_essential.[/red]"
        )
        raise typer.Exit(1)
    root = _require_root()
    target = root / ".holoctl" / "agents" / f"{name}.md"
    if not target.exists():
        console.print(f"[yellow]Agent {name} is not active.[/yellow]")
        raise typer.Exit(1)
    target.unlink()
    console.print(
        f"[green]Removed[/green] [bold]{name}[/bold] "
        f"[dim](still available in library — `hctl agent add {name}` to "
        f"re-activate)[/dim]"
    )


def _blank_agent_scaffold(name: str) -> str:
    return f"""---
name: {name}
description: "(describe what this agent does)"
model: standard
tools: [read, search, edit, write, shell]
trigger: ticket
---

# Identity

You are the **{name}** agent. (Define identity and purpose)

# Guard Rail

(Define when this agent should refuse to work)

# Scope

(Define what this agent does and does NOT do)

# Work Order

1. (Step-by-step work process)

# Report Format

- **Done**: bullets with file:line references.
- **Definition of Done**: each Goal item marked `[x]` or `[ ]`.
- **Suggested next step**: 1 line.
"""

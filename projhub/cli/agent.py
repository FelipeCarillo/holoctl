from __future__ import annotations
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root
from ..lib.markdown import parse_frontmatter

app = typer.Typer(help="Manage agent definitions")


def _require_root() -> Path:
    root = find_project_root()
    if not root:
        console.print("[red]No .projhub/ found. Run `projhub init` first.[/red]")
        raise typer.Exit(1)
    return root


@app.command("list")
def agent_list():
    """List configured agents."""
    root = _require_root()
    agents_dir = root / ".projhub" / "agents"
    if not agents_dir.exists():
        console.print("[dim]No agents configured.[/dim]")
        return

    for f in sorted(agents_dir.glob("*.md")):
        data, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        model = data.get("model", "standard")
        trigger = data.get("trigger", "ticket")
        model_color = "magenta" if model == "reasoning" else "dim" if model == "fast" else "cyan"
        name = data.get("name", f.stem)
        console.print(
            f"  [bold]{name:<16}[/bold] [{model_color}]{model:<10}[/{model_color}] "
            f"[dim]{trigger:<16}[/dim] {data.get('description', '')}"
        )


@app.command("add")
def agent_add(
    name: str = typer.Argument(..., help="Agent name"),
    from_template: Optional[str] = typer.Option(None, "--from", help="Base on an existing agent"),
):
    """Create a new agent definition."""
    root = _require_root()
    agents_dir = root / ".projhub" / "agents"
    target_path = agents_dir / f"{name}.md"

    if target_path.exists():
        console.print(f"[yellow]Agent {name} already exists.[/yellow]")
        raise typer.Exit(1)

    if from_template:
        source = agents_dir / f"{from_template}.md"
        if not source.exists():
            console.print(f"[red]Template agent {from_template} not found.[/red]")
            raise typer.Exit(1)
        import re
        content = source.read_text(encoding="utf-8")
        content = re.sub(r"^(name:\s*).*$", rf"\g<1>{name}", content, flags=re.MULTILINE)
        target_path.write_text(content, encoding="utf-8")
    else:
        target_path.write_text(
            f"""---
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
""",
            encoding="utf-8",
        )

    console.print(f"[green]Created agent: .projhub/agents/{name}.md[/green]")

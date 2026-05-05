from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.config import get_defaults, save_config
from ..lib.templates import get_templates
from ..lib.workspace import add_to_workspace

app = typer.Typer()


@app.command("init")
def init_cmd(
    name: Optional[str] = typer.Option(None, "--name", help="Project name"),
    prefix: Optional[str] = typer.Option(None, "--prefix", help="Ticket ID prefix (e.g. MP)"),
    targets: Optional[str] = typer.Option(None, "--targets", help="Compile targets (claude,cursor,windsurf)"),
):
    """Initialize .projhub/ in the current directory."""
    cwd = Path.cwd()
    projhub_dir = cwd / ".projhub"

    if (projhub_dir / "config.json").exists():
        console.print("[yellow].projhub/ already exists in this directory.[/yellow]")
        raise typer.Exit(1)

    project_name = name or cwd.name
    project_prefix = prefix or _derive_prefix(project_name)
    target_list = [t.strip() for t in targets.split(",")] if targets else ["claude"]

    config = get_defaults()
    config["project"]["name"] = project_name
    config["project"]["prefix"] = project_prefix
    config["targets"] = target_list

    console.print(f"\n  [bold]projhub init[/bold]\n")
    console.print(f"  Project:  [green]{project_name}[/green]")
    console.print(f"  Prefix:   [green]{project_prefix}[/green] (tickets: {project_prefix}-001, {project_prefix}-002, ...)")
    console.print(f"  Targets:  [green]{', '.join(target_list)}[/green]")
    console.print("")

    dirs = [
        ".projhub",
        ".projhub/board",
        ".projhub/board/tickets",
        ".projhub/agents",
        ".projhub/commands",
        ".projhub/context",
        ".projhub/context/decisions",
        ".projhub/context/documents",
    ]
    for d in dirs:
        (cwd / d).mkdir(parents=True, exist_ok=True)

    save_config(cwd, config)

    templates = get_templates(config)
    for rel_path, content in templates.items():
        full_path = cwd / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    index_data = {
        "meta": {"version": 1, "updated": _today(), "nextId": 1, "counts": {}},
        "tickets": [],
    }
    (cwd / ".projhub" / "board" / "index.json").write_text(
        json.dumps(index_data, indent="\t") + "\n", encoding="utf-8"
    )
    (cwd / ".projhub" / "activity.jsonl").write_text("", encoding="utf-8")

    try:
        add_to_workspace(cwd, cwd.name)
    except Exception:
        pass

    console.print(f"  [green]✓ .projhub/ initialized successfully.[/green]\n")
    console.print("  Next steps:")
    console.print(f"    [dim]$[/dim] projhub board add '{{\"title\":\"My first ticket\",\"agent\":\"developer\"}}'")
    console.print(f"    [dim]$[/dim] projhub serve")
    console.print(f"    [dim]$[/dim] projhub compile --target {target_list[0]}")
    console.print("")


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _derive_prefix(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", name)
    if len(cleaned) <= 4:
        return cleaned.upper()
    words = re.split(r"[\s_-]+", name)
    words = [w for w in words if w]
    if len(words) >= 2:
        return "".join(w[0] for w in words).upper()[:4]
    return cleaned[:3].upper()

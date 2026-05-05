from __future__ import annotations
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.workspace import add_to_workspace, remove_from_workspace, list_workspace

app = typer.Typer(help="Manage registered projects across your machine")


@app.command("add")
def workspace_add(
    project_path: Optional[str] = typer.Argument(None, help="Path to the project (default: current dir)"),
    alias: Optional[str] = typer.Option(None, "--alias", help="Short name for the project"),
):
    """Register a project in the workspace."""
    resolved = Path(project_path or ".").resolve()
    if not (resolved / ".projctl" / "config.json").exists():
        console.print(f"[red]No .projctl/ found at {resolved}. Run `projctl init` first.[/red]")
        raise typer.Exit(1)
    name = alias or resolved.name
    add_to_workspace(resolved, name)
    console.print(f"[green]Added {name} → {resolved}[/green]")


@app.command("remove")
def workspace_remove(alias: str = typer.Argument(...)):
    """Unregister a project."""
    remove_from_workspace(alias)
    console.print(f"[green]Removed {alias}[/green]")


@app.command("list")
def workspace_list():
    """List all registered projects."""
    projects = list_workspace()
    if not projects:
        console.print("[dim]No projects registered. Run `projctl init` in a project directory.[/dim]")
        return
    for p in projects:
        exists = (Path(p["path"]) / ".projctl" / "config.json").exists()
        status = "[green]●[/green]" if exists else "[red]●[/red]"
        console.print(f"  {status} [bold]{p['alias']:<20}[/bold] [dim]{p['path']}[/dim]")

from __future__ import annotations
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root, load_config, save_config
from ..lib.discover import discover_repos
from ..lib.git import get_git_info

app = typer.Typer(help="Manage repos (sub-directories) within a project root")


def _require_ctx() -> tuple[Path, dict]:
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `holoctl init` first.[/red]")
        raise typer.Exit(1)
    return root, load_config(root)


@app.command("add")
def repo_add(
    repo_path: str = typer.Argument(...),
    name: Optional[str] = typer.Option(None, "--name"),
    description: str = typer.Option("", "--description"),
):
    """Register a sub-directory/repo in this project."""
    root, config = _require_ctx()
    abs_path = Path(repo_path).resolve()

    if not abs_path.exists():
        console.print(f"[red]Path does not exist: {abs_path}[/red]")
        raise typer.Exit(1)

    repo_name = name or abs_path.name
    rel = str(abs_path.relative_to(root)).replace("\\", "/")

    if any(r["name"] == repo_name for r in config["project"].get("repos", [])):
        console.print(f"[yellow]Repo \"{repo_name}\" already registered.[/yellow]")
        raise typer.Exit(1)

    config["project"].setdefault("repos", []).append(
        {"name": repo_name, "path": rel, "description": description}
    )
    save_config(root, config)

    git = get_git_info(abs_path)
    branch = f"[cyan]{git['branch']}[/cyan]" if git["isGit"] else "[dim]not a git repo[/dim]"
    console.print(f"[green]Added repo \"{repo_name}\"[/green]  [dim]{rel}[/dim]  {branch}")


@app.command("remove")
def repo_remove(name: str = typer.Argument(...)):
    """Unregister a repo from this project."""
    root, config = _require_ctx()
    repos = config["project"].get("repos", [])
    before = len(repos)
    config["project"]["repos"] = [r for r in repos if r["name"] != name]
    if len(config["project"]["repos"]) == before:
        console.print(f"[red]Repo \"{name}\" not found.[/red]")
        raise typer.Exit(1)
    save_config(root, config)
    console.print(f"[green]Removed repo \"{name}\"[/green]")


@app.command("list")
def repo_list():
    """List repos: auto-discovered subprojects merged with manual overrides."""
    root, config = _require_ctx()
    repos = discover_repos(root, include_manual=config["project"].get("repos", []))
    if not repos:
        console.print("[dim]No subprojects discovered. Add markers (.git, package.json, …) or run `holoctl repo add <path>`.[/dim]")
        return
    for r in repos:
        abs_path = root / r["path"]
        git = r.get("git") or {"isGit": False}
        exists = abs_path.exists()
        status = "[green]●[/green]" if exists else "[red]●[/red]"
        if git.get("isGit"):
            dirty = "[yellow] *[/yellow]" if git.get("dirty") else ""
            branch = f"[cyan][{git['branch']}][/cyan]{dirty}"
            if git.get("commitHash"):
                branch += f" [dim]{git['commitHash']} {git.get('lastCommit', '')[:40]}[/dim]"
        else:
            branch = "[dim][no git][/dim]"
        source = r.get("source", "auto")
        source_tag = "" if source == "auto" else f"  [dim]({source})[/dim]"
        console.print(f"  {status} [bold]{r['name']:<20}[/bold] {branch}{source_tag}")
        console.print(f"     [dim]{r['path']}[/dim]")


@app.command("info")
def repo_info(name: str = typer.Argument(...)):
    """Show git info for a repo."""
    root, config = _require_ctx()
    entry = next((r for r in config["project"].get("repos", []) if r["name"] == name), None)
    if not entry:
        console.print(f"[red]Repo \"{name}\" not found.[/red]")
        raise typer.Exit(1)

    abs_path = root / entry["path"]
    git = get_git_info(abs_path)

    console.print(f"\n  [bold]{name}[/bold]\n")
    console.print(f"  Path:    [dim]{abs_path}[/dim]")
    if not git["isGit"]:
        console.print("  Git:     [dim]not a git repository[/dim]\n")
        return

    dirty_str = "[yellow]  (dirty)[/yellow]" if git.get("dirty") else ""
    console.print(f"  Branch:  [cyan]{git['branch']}[/cyan]{dirty_str}")
    console.print(f"  Commit:  [dim]{git['commitHash']}[/dim] {git['lastCommit']}")
    console.print(f"  Date:    [dim]{git['commitDate']}[/dim]")
    if git.get("remote"):
        console.print(f"  Remote:  [dim]{git['remote']}[/dim]")
    console.print("")

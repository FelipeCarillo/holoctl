from __future__ import annotations
from datetime import date
from pathlib import Path

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from ..lib.board import Board
from ..lib.git import get_git_info
from ..lib.markdown import parse_frontmatter

app = typer.Typer()


@app.command("overview")
def overview_cmd():
    """One-screen project snapshot: board, repos, agents, commands, dashboard URL, suggested next."""
    root = find_project_root()
    if not root:
        console.print("[red]No .projhub/ found. Run `projhub init` first.[/red]")
        raise typer.Exit(1)

    config = load_config(root)
    project = config["project"]
    name = project["name"]
    prefix = project["prefix"]

    try:
        from .. import __version__ as _v
    except Exception:
        _v = "?"

    console.print()
    console.print(f"  [bold]{name}[/bold]  [dim]·[/dim]  [cyan]{prefix}[/cyan]  [dim]·[/dim]  [dim]projhub v{_v}[/dim]")
    console.print()

    # Objective
    obj = root / ".projhub" / "context" / "objective.md"
    if obj.exists():
        text = obj.read_text(encoding="utf-8")
        first_para = _first_paragraph(text)
        if first_para:
            console.print("  [bold]🎯 Objective[/bold]")
            console.print(f"     [dim]{first_para}[/dim]")
            console.print()

    # Board
    board = Board(root, config)
    stats = board.stat()
    counts = {k: v for k, v in stats.items() if k != "nextId"}
    total = sum(counts.values())
    console.print(f"  [bold]🎫 Board[/bold]  [dim]({total} ticket{'s' if total != 1 else ''})[/dim]")
    console.print(
        f"     [dim]Backlog[/dim] [bold]{counts.get('backlog',0)}[/bold]  [dim]·[/dim]  "
        f"[blue]Doing[/blue] [bold]{counts.get('doing',0)}[/bold]  [dim]·[/dim]  "
        f"[yellow]Review[/yellow] [bold]{counts.get('review',0)}[/bold]  [dim]·[/dim]  "
        f"[green]Done[/green] [bold]{counts.get('done',0)}[/bold]  [dim]·[/dim]  "
        f"[red]Cancelled[/red] [bold]{counts.get('cancelled',0)}[/bold]"
    )
    console.print()

    # Repos
    repos = project.get("repos", [])
    if repos:
        console.print("  [bold]📁 Repos[/bold]")
        all_tickets = board.ls()
        for r in repos:
            abs_path = root / r["path"]
            git = get_git_info(abs_path)
            branch = git.get("branch", "—") if git.get("isGit") else "no git"
            dirty = "[yellow] *[/yellow]" if git.get("dirty") else ""
            ticket_count = sum(1 for t in all_tickets if t.get("scope") == r["name"])
            console.print(f"     [dim]•[/dim] [bold]{r['name']:<14}[/bold] [cyan][{branch}][/cyan]{dirty}  [dim]{ticket_count} ticket{'s' if ticket_count != 1 else ''}[/dim]")
        console.print()

    # Agents
    agents_dir = root / ".projhub" / "agents"
    if agents_dir.exists():
        agents = sorted(f.stem for f in agents_dir.glob("*.md"))
        if agents:
            console.print("  [bold]🤖 Agents[/bold]")
            console.print(f"     [dim]{' · '.join(agents)}[/dim]")
            console.print()

    # Commands
    commands_dir = root / ".projhub" / "commands"
    if commands_dir.exists():
        cmds = []
        for f in sorted(commands_dir.glob("*.md")):
            fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
            cmds.append("/" + fm.get("name", f.stem))
        if cmds:
            console.print("  [bold]📋 Slash commands[/bold]")
            console.print(f"     [dim]{' · '.join(cmds)} · /projhub[/dim]")
            console.print()

    # Dashboard
    console.print("  [bold]🌐 Dashboard[/bold]")
    console.print("     [cyan]http://127.0.0.1:4242[/cyan]  [dim](run `projhub serve`)[/dim]")
    console.print()

    # Suggested next
    suggestion = _suggest_next(board, counts)
    if suggestion:
        console.print("  [bold]🎯 Suggested next[/bold]")
        console.print(f"     {suggestion}")
        console.print()


def _first_paragraph(text: str) -> str:
    body_lines: list[str] = []
    in_paragraph = False
    skip_frontmatter = False
    for line in text.splitlines():
        if line.strip() == "---":
            skip_frontmatter = not skip_frontmatter
            continue
        if skip_frontmatter:
            continue
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            if in_paragraph:
                break
            continue
        body_lines.append(stripped)
        in_paragraph = True
    return " ".join(body_lines)[:240]


def _suggest_next(board: Board, counts: dict) -> str:
    today = date.today()
    doing = board.ls({"status": "doing"})

    # Stalled tickets (>5 days in doing)
    for t in doing:
        upd = t.get("updated")
        if not upd:
            continue
        try:
            d = date.fromisoformat(upd)
            age = (today - d).days
            if age > 5:
                return f"[yellow]⚠[/yellow] [bold]{t['id']}[/bold] [dim]has been in `doing` for {age} days — review or unblock?[/dim]"
        except (ValueError, TypeError):
            pass

    if counts.get("backlog", 0) == 0 and counts.get("doing", 0) == 0:
        return "[dim]No tickets yet. Create one with[/dim] [bold]/ticket <title>[/bold]"

    # Next p1 from backlog
    backlog_p1 = [t for t in board.ls({"status": "backlog", "priority": "p1"})]
    if backlog_p1:
        t = backlog_p1[0]
        return f"[dim]Next p1:[/dim] [bold]{t['id']}[/bold] [dim]{t['title'][:50]}[/dim]"

    backlog_p0 = [t for t in board.ls({"status": "backlog", "priority": "p0"})]
    if backlog_p0:
        t = backlog_p0[0]
        return f"[red]p0:[/red] [bold]{t['id']}[/bold] [dim]{t['title'][:50]}[/dim]"

    if counts.get("doing", 0) > 0:
        return "[dim]Keep moving on tickets in[/dim] [blue]doing[/blue]"

    return "[dim]No urgent work. Review the backlog with[/dim] [bold]/board[/bold]"

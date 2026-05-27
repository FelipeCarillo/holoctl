"""`hctl memory` — manage durable cross-assistant project memory."""
from __future__ import annotations

import sys
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root
from ..lib.memory import Memory, VALID_SCOPES

app = typer.Typer(help="Manage workspace memory (durable, cross-assistant context)")


def _mem() -> Memory:
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `hctl init` first.[/red]")
        raise typer.Exit(1)
    return Memory(root)


@app.command("list")
def memory_list(
    show_archived: bool = typer.Option(
        False, "--archived", help="Include archived topics"
    ),
):
    """List memory topics with their scope and description."""
    mem = _mem()
    if not mem.dir.exists():
        console.print(
            "[dim]No memory yet. Create with `hctl memory add <name> ...`[/dim]"
        )
        return
    topics = mem.list_topics(include_archived=show_archived)
    if mem.index_path.exists():
        size = len(mem.read_index().splitlines())
        console.print(f"\n  [bold]MEMORY.md[/bold] [dim](always-on, {size} lines)[/dim]")
    if not topics:
        console.print(
            "\n  [dim]No topics yet.[/dim] "
            "Add with `hctl memory add <name> --scope lazy --description ...`\n"
        )
        return
    console.print("\n  [bold]Topics[/bold]")
    for t in topics:
        scope_color = (
            "magenta" if t.scope == "always_on"
            else "cyan" if t.scope == "glob"
            else "dim"
        )
        glob_str = f" {','.join(t.globs)}" if t.globs else ""
        desc = t.description or "[dim](no description)[/dim]"
        console.print(
            f"  [bold]{t.name:<20}[/bold] "
            f"[{scope_color}]{t.scope:<10}[/{scope_color}]{glob_str}  {desc}"
        )
    console.print("")


@app.command("get")
def memory_get(name: str = typer.Argument(..., help="Topic name (or 'index')")):
    """Print a topic's body to stdout."""
    mem = _mem()
    if name in ("index", "MEMORY", "MEMORY.md"):
        body = mem.read_index()
        if not body:
            console.print("[dim](memory index is empty)[/dim]")
            raise typer.Exit(1)
        sys.stdout.write(body)
        return
    topic = mem.get_topic(name)
    if topic is None:
        console.print(f"[red]Topic {name!r} not found.[/red]")
        raise typer.Exit(1)
    sys.stdout.write(topic.to_markdown())


@app.command("add")
def memory_add(
    name: str = typer.Argument(..., help="Topic name (lowercase-with-hyphens)"),
    scope: str = typer.Option(
        "lazy", "--scope",
        help=f"One of: {', '.join(VALID_SCOPES)}",
    ),
    description: Optional[str] = typer.Option(
        None, "--description", "-d",
        help="Required for scope=lazy. Helps the model decide when to load.",
    ),
    glob: list[str] = typer.Option(
        None, "--glob", "-g",
        help="Glob pattern(s) for scope=glob. Repeatable.",
    ),
    from_file: Optional[str] = typer.Option(
        None, "--from-file",
        help="Read body from a file (default: stdin)",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Replace if topic exists",
    ),
):
    """Create or replace a memory topic.

    Body is read from --from-file if provided, otherwise from stdin (paste +
    Ctrl+D on Unix, Ctrl+Z+Enter on Windows).
    """
    mem = _mem()
    mem.dir.mkdir(parents=True, exist_ok=True)
    mem.ensure_gitignore()

    if from_file:
        body = open(from_file, "r", encoding="utf-8").read()
    elif not sys.stdin.isatty():
        body = sys.stdin.read()
    else:
        console.print(
            "[yellow]No body source.[/yellow] Pass --from-file <path> or pipe body in stdin."
        )
        raise typer.Exit(1)

    try:
        topic = mem.add_topic(
            name,
            body=body,
            scope=scope,
            description=description or "",
            globs=glob or [],
            overwrite=overwrite,
        )
    except (ValueError, FileExistsError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(
        f"  [green]✓ added topic[/green] [bold]{topic.name}[/bold] "
        f"[dim](scope={topic.scope})[/dim]"
    )


@app.command("search")
def memory_search(query: str = typer.Argument(..., help="Substring to find")):
    """Search index + topics for a substring (case-insensitive)."""
    mem = _mem()
    hits = mem.search(query)
    if not hits:
        console.print(f"[dim]No matches for {query!r}.[/dim]")
        return
    for topic_name, line in hits:
        console.print(f"  [bold]{topic_name}[/bold]: {line}")


@app.command("archive")
def memory_archive(name: str = typer.Argument(..., help="Topic name")):
    """Move a topic to topics/_archived/ (curator can also do this for stale topics)."""
    mem = _mem()
    try:
        path = mem.archive_topic(name)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(
        f"  [green]✓ archived[/green] [bold]{name}[/bold] [dim]→ {path}[/dim]"
    )


@app.command("seed")
def memory_seed():
    """Create an empty MEMORY.md and .gitignore if absent."""
    mem = _mem()
    from ..lib.config import load_config
    config = load_config(mem.root)
    project_name = config.get("project", {}).get("name", mem.root.name)
    created = mem.ensure_seed(project_name)
    mem.ensure_gitignore()
    if created:
        console.print(
            "  [green]✓ seeded[/green] .holoctl/memory/MEMORY.md "
            "[dim](and .gitignore)[/dim]"
        )
    else:
        console.print("[dim]MEMORY.md already exists; nothing to do.[/dim]")

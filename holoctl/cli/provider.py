"""`hctl provider` — manage external-board provider catalog.

Providers map URL patterns to MCP tool names so the agent (via the
`holoctl-provider-mcp` skill) can fetch card bodies automatically when
the provider's MCP is connected in Claude Code. The transport (the MCP
itself) is the user's responsibility — configured in `.mcp.json` or via
gateway — holoctl just declares what it knows how to use.

Defaults (Linear/GitHub/Trello/Azure DevOps/Jira/Slack) are shipped and
applied additively on `load_config`. Custom providers (internal boards,
for example) are added via `hctl provider add` and persisted in
`.holoctl/config.json:providers`.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from ..lib.config import find_project_root, load_config, save_config

app = typer.Typer(help="Manage external-board provider catalog (Linear/GitHub/Trello/...)")


_VALID_ENABLED = ("auto", "always", "disabled")


def _require_root() -> Path:
    root = find_project_root()
    if not root:
        console.print("[red]No .holoctl/ found. Run `holoctl init` first.[/red]")
        raise typer.Exit(1)
    return root


@app.command("list")
def provider_list():
    """Show configured providers with their status, URL pattern, and MCP tool."""
    root = _require_root()
    config = load_config(root)
    providers = config.get("providers") or {}
    if not providers:
        console.print("[dim]No providers configured.[/dim]")
        return
    console.print("\n  [bold]Providers[/bold]  [dim](URL pattern → MCP tool)[/dim]")
    for name in sorted(providers.keys()):
        entry = providers[name]
        enabled = str(entry.get("enabled", "auto"))
        color = "green" if enabled == "auto" else "cyan" if enabled == "always" else "dim"
        fetch = entry.get("mcp_fetch_tool") or "—"
        pattern = entry.get("url_pattern") or "—"
        # Truncate pattern for display.
        display_pattern = pattern if len(pattern) <= 50 else pattern[:47] + "..."
        console.print(
            f"  [bold]{name:<16}[/bold] [{color}]{enabled:<9}[/{color}] "
            f"[dim]{display_pattern}[/dim]"
        )
        console.print(f"  {'':<16} [dim]→ {fetch}[/dim]")
    console.print("")


@app.command("add")
def provider_add(
    name: str = typer.Argument(..., help="Provider name (lowercase, no spaces)"),
    mcp_fetch: str = typer.Option(..., "--mcp-fetch", help="MCP tool name for fetching one item (e.g. mcp__acme__get_card)"),
    url_pattern: str = typer.Option(..., "--url-pattern", help="Python regex with at least named group (?P<ref>...)"),
    label_template: str = typer.Option("{ref}: {title}", "--label-template", help="Template for source_label using named groups + 'title'"),
    mcp_search: Optional[str] = typer.Option(None, "--mcp-search", help="MCP tool name for searching"),
    enabled: str = typer.Option("auto", "--enabled", help=f"One of: {', '.join(_VALID_ENABLED)}"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing entry"),
):
    """Add a custom provider (e.g. an internal company board) to the catalog.

    Defaults for Linear/GitHub/Trello/Azure DevOps/Jira/Slack already ship —
    use this command for boards holoctl doesn't know yet, or to override
    one of the defaults (with --force).
    """
    if enabled not in _VALID_ENABLED:
        console.print(f"[red]Invalid --enabled value:[/red] {enabled}. Valid: {', '.join(_VALID_ENABLED)}.")
        raise typer.Exit(1)
    # Validate regex compiles.
    try:
        compiled = re.compile(url_pattern)
    except re.error as e:
        console.print(f"[red]Invalid regex in --url-pattern:[/red] {e}")
        raise typer.Exit(1)
    if "ref" not in compiled.groupindex:
        console.print("[red]--url-pattern must include a named group `(?P<ref>...)` for the item id.[/red]")
        raise typer.Exit(1)

    root = _require_root()
    config = load_config(root)
    providers = config.setdefault("providers", {})

    if name in providers and not force:
        console.print(f"[yellow]Provider {name!r} already exists. Pass --force to overwrite.[/yellow]")
        raise typer.Exit(1)

    entry = {
        "enabled": enabled,
        "url_pattern": url_pattern,
        "mcp_fetch_tool": mcp_fetch,
        "label_template": label_template,
    }
    if mcp_search:
        entry["mcp_search_tool"] = mcp_search

    providers[name] = entry
    save_config(root, config)
    console.print(f"[green]Added provider {name}[/green] [dim](enabled: {enabled})[/dim]")


@app.command("enable")
def provider_enable(name: str = typer.Argument(...)):
    """Set a provider's `enabled` flag to `auto` (probe MCP tool at runtime)."""
    _set_enabled(name, "auto")


@app.command("disable")
def provider_disable(name: str = typer.Argument(...)):
    """Set a provider's `enabled` flag to `disabled` (skip entirely)."""
    _set_enabled(name, "disabled")


def _set_enabled(name: str, value: str) -> None:
    root = _require_root()
    config = load_config(root)
    providers = config.get("providers") or {}
    if name not in providers:
        console.print(f"[red]Provider {name!r} not found. Run `hctl provider list`.[/red]")
        raise typer.Exit(1)
    providers[name]["enabled"] = value
    config["providers"] = providers
    save_config(root, config)
    console.print(f"[green]{name}.enabled = {value}[/green]")


@app.command("test")
def provider_test(
    name: str = typer.Argument(..., help="Provider name to test against"),
    url: str = typer.Argument(..., help="URL to parse using the provider's url_pattern"),
):
    """Sanity-check a provider's URL pattern against a real URL.

    Does NOT call the MCP tool (the actual fetch happens in Claude Code).
    Just confirms the regex parses the URL and shows the named captures.
    """
    root = _require_root()
    config = load_config(root)
    providers = config.get("providers") or {}
    if name not in providers:
        console.print(f"[red]Provider {name!r} not found.[/red]")
        raise typer.Exit(1)
    entry = providers[name]
    pattern = entry.get("url_pattern")
    if not pattern:
        console.print(f"[red]Provider {name!r} has no url_pattern.[/red]")
        raise typer.Exit(1)
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        console.print(f"[red]Stored regex doesn't compile: {e}[/red]")
        raise typer.Exit(1)
    m = compiled.match(url)
    if not m:
        console.print(f"[yellow]No match.[/yellow] URL doesn't match {name!r}'s pattern.")
        console.print(f"  [dim]pattern:[/dim] {pattern}")
        raise typer.Exit(1)
    console.print(f"[green]✓ Match.[/green]")
    console.print(f"  [dim]provider:[/dim] {name}")
    console.print(f"  [dim]captures:[/dim]")
    for k, v in m.groupdict().items():
        console.print(f"    [bold]{k}[/bold] = {v!r}")
    console.print(f"  [dim]MCP tool (probe at runtime):[/dim] {entry.get('mcp_fetch_tool') or '—'}")


@app.command("remove")
def provider_remove(
    name: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", help="Required to remove a shipped default provider"),
):
    """Drop a provider from the catalog.

    Refuses to remove the shipped defaults (Linear/GitHub/Trello/Azure
    DevOps/Jira/Slack) without `--force` — `disable` is usually what you
    want. Always allowed for custom-added providers.
    """
    root = _require_root()
    config = load_config(root)
    providers = config.get("providers") or {}
    if name not in providers:
        console.print(f"[red]Provider {name!r} not found.[/red]")
        raise typer.Exit(1)
    from ..lib.config import _default_providers
    is_default = name in _default_providers()
    if is_default and not force:
        console.print(
            f"[yellow]{name!r} is a shipped default — `hctl provider disable {name}` is usually "
            f"enough. Pass --force to actually remove the entry.[/yellow]"
        )
        raise typer.Exit(1)
    del providers[name]
    config["providers"] = providers
    save_config(root, config)
    console.print(f"[green]Removed provider {name}[/green]")

from __future__ import annotations

import importlib.util

import typer
from ._console import console

app = typer.Typer()

# The HTTP dashboard needs the optional web stack. The MCP server and every
# other CLI command stay dependency-free, so these live behind the
# `holoctl[dashboard]` extra rather than the lean core.
_DASHBOARD_MODULES = ("uvicorn", "fastapi", "jinja2")


def _missing_dashboard_dep() -> str | None:
    """Return the first dashboard module that isn't importable, or None."""
    for name in _DASHBOARD_MODULES:
        if importlib.util.find_spec(name) is None:
            return name
    return None


@app.command("serve")
def serve_cmd(
    port: int = typer.Option(4242, "--port", help="Port number"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind (use 0.0.0.0 to expose on the network)"),
    mcp: bool = typer.Option(
        False, "--mcp",
        help="Run as a stdio MCP server instead of the HTTP dashboard. "
             "Used by AI assistants via mcpServers config; you typically "
             "don't invoke this directly.",
    ),
):
    """Start the web dashboard, OR run as a stdio MCP server with --mcp."""
    if mcp:
        # MCP transport is dependency-free — no web stack required.
        from ..server.mcp import serve_stdio
        serve_stdio()
        return

    missing = _missing_dashboard_dep()
    if missing:
        # Escape the [ in [dashboard] so rich doesn't treat it as a markup tag.
        console.print(
            "\n  [red]The dashboard needs the optional web extra.[/red]\n"
            "  Install it with one of:\n"
            "    [bold]pip install 'holoctl\\[dashboard]'[/bold]\n"
            "    [bold]uv tool install 'holoctl\\[dashboard]'[/bold]\n"
            f"  [dim](missing module: {missing}. The CLI, board, compile and "
            f"MCP server work without it.)[/dim]\n"
        )
        raise typer.Exit(1)

    import uvicorn
    display_host = "localhost" if host in ("127.0.0.1", "localhost") else host
    console.print(f"\n  [bold]holoctl dashboard[/bold]  →  [cyan]http://{display_host}:{port}[/cyan]\n")
    if host == "0.0.0.0":
        console.print("  [yellow]⚠ exposed on the network — anyone on this WiFi can access[/yellow]\n")
    uvicorn.run("holoctl.server.app:app", host=host, port=port, reload=False)

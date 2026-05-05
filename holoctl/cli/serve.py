from __future__ import annotations

import typer
from ._console import console

app = typer.Typer()


@app.command("serve")
def serve_cmd(
    port: int = typer.Option(4242, "--port", help="Port number"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind (use 0.0.0.0 to expose on the network)"),
):
    """Start the web platform dashboard."""
    import uvicorn
    display_host = "localhost" if host in ("127.0.0.1", "localhost") else host
    console.print(f"\n  [bold]holoctl dashboard[/bold]  →  [cyan]http://{display_host}:{port}[/cyan]\n")
    if host == "0.0.0.0":
        console.print("  [yellow]⚠ exposed on the network — anyone on this WiFi can access[/yellow]\n")
    uvicorn.run("holoctl.server.app:app", host=host, port=port, reload=False)

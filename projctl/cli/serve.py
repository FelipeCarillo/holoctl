from __future__ import annotations

import typer
from ._console import console

app = typer.Typer()


@app.command("serve")
def serve_cmd(
    port: int = typer.Option(4242, "--port", help="Port number"),
):
    """Start the web platform dashboard."""
    import uvicorn
    console.print(f"\n  [bold]projectl dashboard[/bold]  →  [cyan]http://localhost:{port}[/cyan]\n")
    uvicorn.run("projctl.server.app:app", host="0.0.0.0", port=port, reload=False)

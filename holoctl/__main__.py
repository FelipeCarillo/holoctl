from __future__ import annotations
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer

from .cli.init_ import app as _init_app, init_cmd
from .cli.board import app as _board_app
from .cli.compile_ import app as _compile_app, compile_cmd
from .cli.sync_ import app as _sync_app, sync_cmd
from .cli.upgrade_ import app as _upgrade_app, upgrade_cmd
from .cli.doctor import app as _doctor_app, doctor_cmd
from .cli.agent import app as _agent_app
from .cli.repo import app as _repo_app
from .cli.serve import app as _serve_app, serve_cmd
from .cli.overview import app as _overview_app, overview_cmd
from . import __version__

app = typer.Typer(
    name="holoctl",
    help="Universal project operating system for AI coding assistants",
    no_args_is_help=True,
)

# Sub-group commands
app.add_typer(_board_app, name="board", help="Manage the project board")
app.add_typer(_agent_app, name="agent", help="Manage agent definitions")
app.add_typer(_repo_app, name="repo", help="Manage repos within a project")

# Direct commands
app.command("init")(init_cmd)
app.command("compile")(compile_cmd)
app.command("sync")(sync_cmd)
app.command("upgrade")(upgrade_cmd)
app.command("doctor")(doctor_cmd)
app.command("serve")(serve_cmd)
app.command("overview")(overview_cmd)


def _version_callback(value: bool):
    if value:
        print(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(None, "--version", "-v", callback=_version_callback, is_eager=True),
    ctx: typer.Context = typer.Context,
):
    pass


if __name__ == "__main__":
    app()

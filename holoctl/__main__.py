from __future__ import annotations
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer

from .cli.init_ import init_cmd
from .cli.board import app as _board_app
from .cli.compile_ import compile_cmd
from .cli.sync_ import sync_cmd
from .cli.upgrade_ import upgrade_cmd
from .cli.doctor import doctor_cmd
from .cli.adopt import adopt_cmd
from .cli.agent import app as _agent_app
from .cli.memory import app as _memory_app
from .cli.journal import app as _journal_app
from .cli.repo import app as _repo_app
from .cli.provider import app as _provider_app
from .cli.serve import serve_cmd
from .cli.overview import overview_cmd
from .cli.setup import setup_cmd
from .cli.setup_global import setup_global_cmd
from .cli.boot import boot_cmd
from .cli.handoff import handoff_cmd
from .cli.coverage import coverage_cmd
from .cli.curate import app as _curate_app
from . import __version__

app = typer.Typer(
    name="holoctl",
    help="Universal project operating system for AI coding assistants",
    no_args_is_help=True,
)

# Sub-group commands
app.add_typer(_board_app, name="board", help="Manage the project board")
app.add_typer(_agent_app, name="agent", help="Manage agent definitions")
app.add_typer(_memory_app, name="memory", help="Manage workspace memory")
app.add_typer(_journal_app, name="journal", help="Record and inspect workspace events")
app.add_typer(_curate_app, name="curate", help="Run the curator + inspect/silence suggestions")
app.add_typer(_repo_app, name="repo", help="Manage repos within a project")
app.add_typer(_provider_app, name="provider", help="Manage external-board provider catalog")

# Direct commands
app.command("init")(init_cmd)
app.command("setup")(setup_cmd)
app.command("setup-global")(setup_global_cmd)
app.command("compile")(compile_cmd)
app.command("sync")(sync_cmd)
app.command("upgrade")(upgrade_cmd)
app.command("doctor")(doctor_cmd)
app.command("adopt")(adopt_cmd)
app.command("serve")(serve_cmd)
app.command("overview")(overview_cmd)
app.command("boot")(boot_cmd)
app.command("handoff")(handoff_cmd)
app.command("coverage")(coverage_cmd)


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

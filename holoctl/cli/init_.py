from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional

import typer
from ._console import console

from .. import __version__
from ..lib.config import get_defaults, save_config
from ..lib.templates import get_templates

app = typer.Typer()


@app.command("init")
def init_cmd(
    name: Optional[str] = typer.Option(None, "--name", help="Project name"),
    prefix: Optional[str] = typer.Option(None, "--prefix", help="Ticket ID prefix (e.g. MP)"),
    targets: Optional[str] = typer.Option(None, "--targets", help="Compile targets (claude,cursor,windsurf,copilot,devin)"),
    skip_compile: bool = typer.Option(False, "--skip-compile", help="Skip auto-compile after init"),
    bare: bool = typer.Option(False, "--bare", help="Create only the directory skeleton; skip compile, hooks, MCP."),
):
    """Initialize or sync .holoctl/ in the current directory.

    Idempotent. Behavior depends on existing state:
      - .holoctl/ absent → creates the full neutral skeleton + compile.
      - .holoctl/ present, version == installed → re-runs sync+compile (no destructive write).
      - .holoctl/ present, version < installed → directs the user to `hctl upgrade`.
      - .holoctl/ present, version > installed → refuses (anti auto-downgrade).
    """
    cwd = Path.cwd()
    holoctl_dir = cwd / ".holoctl"
    config_path = holoctl_dir / "config.json"

    if config_path.exists():
        from ..lib.config import load_config
        existing_config = load_config(cwd)
        existing_version = existing_config.get("holoctlVersion", "0.0.0")
        if _semver_lt(__version__, existing_version):
            console.print(
                f"\n  [red]Refusing to downgrade.[/red] Workspace is at "
                f"[cyan]{existing_version}[/cyan]; installed hctl is "
                f"[cyan]{__version__}[/cyan].\n"
                f"  Use a newer hctl, or edit "
                f".holoctl/config.json:holoctlVersion manually.\n"
            )
            raise typer.Exit(2)
        if _semver_lt(existing_version, __version__):
            console.print(
                f"\n  [yellow]Workspace is at {existing_version}; installed hctl "
                f"is {__version__}.[/yellow]\n"
                f"  Run [bold]hctl upgrade[/bold] to migrate templates and recompile.\n"
            )
            raise typer.Exit(0)
        # Same version — re-run sync+compile non-destructively.
        console.print(
            f"\n  [bold]hctl init[/bold] [dim](sync mode — workspace already at "
            f"{existing_version})[/dim]\n"
        )
        config = existing_config
        if targets:
            config["targets"] = [t.strip() for t in targets.split(",")]
        return _resync_existing(cwd, config, skip_compile=skip_compile, bare=bare)

    project_name = name or cwd.name
    project_prefix = prefix or _derive_prefix(project_name)
    target_list = [t.strip() for t in targets.split(",")] if targets else ["claude"]

    config = get_defaults()
    config["holoctlVersion"] = __version__
    config["project"]["name"] = project_name
    config["project"]["prefix"] = project_prefix
    config["targets"] = target_list

    console.print(f"\n  [bold]holoctl init[/bold]\n")
    console.print(f"  Project:  [green]{project_name}[/green]")
    console.print(f"  Prefix:   [green]{project_prefix}[/green] (tickets: {project_prefix}-001, {project_prefix}-002, ...)")
    console.print(f"  Targets:  [green]{', '.join(target_list)}[/green]")
    console.print("")

    dirs = [
        ".holoctl",
        ".holoctl/board",
        ".holoctl/board/tickets",
        ".holoctl/agents",
        ".holoctl/commands",
        ".holoctl/context",
        ".holoctl/context/decisions",
        ".holoctl/context/documents",
        ".holoctl/memory",
        ".holoctl/memory/topics",
        ".holoctl/journal",
    ]
    for d in dirs:
        (cwd / d).mkdir(parents=True, exist_ok=True)

    save_config(cwd, config)

    # Seed an empty memory index + .gitignore. Topics are added by the user
    # (`hctl memory add`) or proposed by the curator (0.14).
    from ..lib.memory import Memory
    mem = Memory(cwd)
    mem.ensure_seed(project_name)
    mem.ensure_gitignore()

    templates = get_templates(config)
    for rel_path, content in templates.items():
        full_path = cwd / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    index_data = {
        "meta": {"version": 1, "updated": _now(), "nextId": 1, "counts": {}},
        "tickets": [],
    }
    (cwd / ".holoctl" / "board" / "index.json").write_text(
        json.dumps(index_data, indent="\t") + "\n", encoding="utf-8"
    )
    (cwd / ".holoctl" / "activity.jsonl").write_text("", encoding="utf-8")

    console.print(
        f"  [green]✓ .holoctl/ initialized[/green] "
        f"[dim](neutral — only `boardmaster` active; library loaded)[/dim]\n"
    )

    if bare:
        console.print(
            "  [dim]--bare: skipping compile, hooks, MCP[/dim]\n"
        )
        return

    if not skip_compile:
        from ..lib.compiler import compile_project
        for tgt in target_list:
            try:
                result = compile_project(cwd, config, tgt, dry_run=False)
                count = len(result.get("files", []))
                console.print(f"  [green]✓ compiled[/green] [bold]{tgt}[/bold] [dim]({count} files)[/dim]")
            except Exception as e:
                console.print(f"  [red]✗ compile {tgt}:[/red] {e}")

    console.print("")
    console.print("  Next steps:")
    console.print(
        f"    [dim]$[/dim] hctl agent list                     "
        f"[dim]# see latent personas you can activate[/dim]"
    )
    console.print(
        f"    [dim]$[/dim] hctl agent add developer            "
        f"[dim]# example: activate the code-implementation persona[/dim]"
    )
    console.print(
        f"    [dim]$[/dim] hctl board add '{{\"title\":\"My first ticket\",\"agent\":\"boardmaster\"}}'"
    )
    console.print(f"    [dim]$[/dim] hctl serve")
    console.print("")


def _resync_existing(cwd: Path, config: dict, *, skip_compile: bool, bare: bool) -> None:
    """Re-run sync+compile on an existing workspace at the same version.

    Non-destructive: user-owned files (tickets, hand-edited agents/context) are
    preserved; only template-managed files are refreshed via the same allow-list
    `cli.sync_._SYNC_TARGETS` uses.
    """
    from ..lib.templates import get_templates
    templates = get_templates(config)

    # Re-emit memory seed/.gitignore (idempotent, non-destructive).
    from ..lib.memory import Memory
    mem = Memory(cwd)
    mem.ensure_seed(config.get("project", {}).get("name", cwd.name))
    mem.ensure_gitignore()

    # Materialize template-managed files but never overwrite user content.
    # The conservative default: only write essentials (matches what
    # cli.upgrade_._sync writes), not full template set.
    SYNC_TARGETS = {
        ".holoctl/commands/status.md",
        ".holoctl/commands/ticket.md",
        ".holoctl/commands/board.md",
        ".holoctl/commands/sprint.md",
        ".holoctl/commands/decision.md",
        ".holoctl/commands/close.md",
        ".holoctl/board/WORKFLOW.md",
        ".holoctl/board/tickets/_template.md",
        ".holoctl/agents/boardmaster.md",
    }
    for rel_path, content in templates.items():
        if rel_path not in SYNC_TARGETS:
            continue
        path = cwd / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    if bare or skip_compile:
        console.print("  [dim]Skipped compile.[/dim]\n")
        return

    from ..lib.compiler import compile_project
    for tgt in config.get("targets", ["claude"]):
        try:
            result = compile_project(cwd, config, tgt, dry_run=False)
            count = len(result.get("files", []))
            console.print(
                f"  [green]✓ recompiled[/green] [bold]{tgt}[/bold] "
                f"[dim]({count} files)[/dim]"
            )
        except Exception as e:
            console.print(f"  [red]✗ compile {tgt}:[/red] {e}")
    console.print("")


def _semver_lt(a: str, b: str) -> bool:
    return _semver_tuple(a) < _semver_tuple(b)


def _semver_tuple(v: str) -> tuple[int, int, int]:
    import re
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(v).strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _derive_prefix(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", name)
    if len(cleaned) <= 4:
        return cleaned.upper()
    words = re.split(r"[\s_-]+", name)
    words = [w for w in words if w]
    if len(words) >= 2:
        return "".join(w[0] for w in words).upper()[:4]
    return cleaned[:3].upper()

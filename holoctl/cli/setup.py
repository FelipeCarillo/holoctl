"""`hctl setup` — one-time global install: plant /holoctl in every detected assistant.

Run **once per machine**. After this, the user opens any folder in any
supported assistant and types `/holoctl` to bootstrap holoctl in that
folder (`hctl init` runs idempotently from inside the slash skill).

The skill body is identical across targets — what differs is where each
assistant looks for user-level skills/commands. We resolve `hctl`'s
absolute path via `shutil.which("hctl")` so the slash works even when
`hctl` was installed via `uv tool install` or `pipx` (locations not in
the default `PATH` of every shell context).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

import typer
from ._console import console

app = typer.Typer()


# ----------------------------------------------------------------------
# Per-assistant target spec.
#
# Each entry: (display_name, detect_dir, target_paths)
# - detect_dir: presence triggers detection
# - target_paths: list of absolute paths where /holoctl skill should land
# ----------------------------------------------------------------------


def _home() -> Path:
    return Path.home()


def _appdata() -> Path | None:
    """Windows %APPDATA% — None on non-Windows."""
    if sys.platform != "win32":
        return None
    val = os.environ.get("APPDATA")
    if not val:
        return None
    return Path(val)


def _targets() -> list[dict]:
    home = _home()
    return [
        {
            "name": "Claude Code",
            "key": "claude",
            "detect": [home / ".claude"],
            "skill_path": home / ".claude" / "commands" / "holoctl.md",
            "format": "claude",
        },
    ]


def _resolve_hctl_bin() -> str:
    """Find absolute path to the `hctl` executable for embedding in skills.

    Priority: $HOLOCTL_BIN > shutil.which("hctl") > sys.executable -m holoctl.
    """
    env = os.environ.get("HOLOCTL_BIN")
    if env:
        return env
    via_path = shutil.which("hctl") or shutil.which("holoctl")
    if via_path:
        return via_path
    return f"{sys.executable} -m holoctl"


def _skill_body(hctl_bin: str, fmt: str) -> str:
    """Build the skill body for a given target format.

    Body is the same across targets — only the frontmatter changes to
    match each assistant's expected schema.
    """
    body = (
        "# You are an agent operating in a workspace managed by holoctl.\n"
        "\n"
        "Holoctl is a multi-assistant project operating system. Your job in this\n"
        "skill is to detect the workspace state and route to the right flow.\n"
        "\n"
        "## Step 1 — detect the workspace state\n"
        "\n"
        f"Run `{hctl_bin} doctor`. The first line of output indicates one of:\n"
        "\n"
        "- `holoctl: not initialized` → go to **Flow A: first time**\n"
        "- `holoctl: outdated` → go to **Flow B: upgrade**\n"
        "- `holoctl: ok` → go to **Flow C: normal operation**\n"
        "\n"
        "## Flow A — first time (no .holoctl/ in this folder)\n"
        "\n"
        f"1. Run `{hctl_bin} init`. This creates `.holoctl/`, compiles for every\n"
        "   configured target, plants journal/curator hooks, and writes MCP config.\n"
        "2. Report a single line: \"Workspace ready. Targets: <list>.\"\n"
        f"3. Run `{hctl_bin} boot`. Print its output verbatim — do not paraphrase.\n"
        "4. Stop and wait for the user.\n"
        "\n"
        "## Flow B — upgrade (workspace pinned to an older release)\n"
        "\n"
        f"1. Run `{hctl_bin} upgrade --check`. Show the user the CHANGELOG slice.\n"
        "2. Ask: \"Apply upgrade?\"\n"
        f"3. If yes, run `{hctl_bin} upgrade`. Report each step's confirmation in\n"
        f"   one line. Then run `{hctl_bin} boot` and print its output.\n"
        "\n"
        "## Flow C — normal operation\n"
        "\n"
        "Pick the right command from the user's request:\n"
        "\n"
        "| User said                          | Command                          |\n"
        "|------------------------------------|----------------------------------|\n"
        f"| \"status\", \"what's pending\"        | `{hctl_bin} boot`                |\n"
        f"| \"create ticket\"                   | `{hctl_bin} board add '<json>'`  |\n"
        f"| \"close session\", \"about to /clear\" | `{hctl_bin} handoff`             |\n"
        f"| \"any suggestions?\"               | `{hctl_bin} curate show`         |\n"
        f"| \"list personas\"                   | `{hctl_bin} agent list`          |\n"
        f"| \"activate <persona>\"              | `{hctl_bin} agent add <name>`    |\n"
        f"| \"search memory\"                   | `{hctl_bin} memory search <q>`   |\n"
        "\n"
        "## Operating rules — do NOT violate\n"
        "\n"
        "- **Never** edit `.holoctl/board/index.json` or `.holoctl/memory/MEMORY.md`\n"
        f"  by hand. Use `{hctl_bin} <subcommand>` always.\n"
        "- If a command returns an error, **read the literal error**, report it to\n"
        "  the user, and stop. Do not silently try alternatives.\n"
        "- The CLI is the source of truth. Frontmatter and index.json are derived.\n"
    )
    return body


def _frontmatter(fmt: str) -> str:
    """Native frontmatter per assistant.

    The description is identical — what changes is the field schema each
    assistant expects.
    """
    desc = (
        "Holoctl router skill — detects workspace state and routes to "
        "init/upgrade/operate. Activate when the user asks for project status, "
        "ticket management, session close, or any 'holoctl' / 'hctl' question."
    )
    if fmt == "claude":
        return (
            "---\n"
            "name: holoctl\n"
            f"description: |\n  {desc}\n"
            "allowed-tools: [Bash, Read]\n"
            "---\n\n"
        )
    return ""


@app.command("setup")
def setup_cmd(
    only: Optional[list[str]] = typer.Option(
        None, "--only",
        help="Restrict to specific assistants (claude). Repeatable.",
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Overwrite existing /holoctl skill files.",
    ),
):
    """Plant the /holoctl skill in every detected AI assistant.

    Since 0.20.0, "every detected" is effectively just Claude Code — the
    other assistants self-configure via the `holoctl-foreign-bootstrap`
    skill triggered from the per-project `AGENTS.md`, so they don't need
    a user-level skill installed here.

    Idempotent — re-running updates content. Use --force to overwrite even
    when the user has hand-edited the skill (rare).
    """
    hctl_bin = _resolve_hctl_bin()
    targets = _targets()
    if only:
        keys = set(only)
        targets = [t for t in targets if t["key"] in keys]

    console.print("\n  [bold]hctl setup[/bold]\n")
    console.print(f"  Resolved hctl path: [cyan]{hctl_bin}[/cyan]\n")
    console.print("  Detecting installed AI assistants…")

    detected_count = 0
    written: list[tuple[str, Path]] = []
    skipped: list[str] = []
    for t in targets:
        is_detected = any(p.exists() for p in t["detect"])
        symbol = "[green]✓[/green]" if is_detected else "[dim]·[/dim]"
        console.print(f"  {symbol} {t['name']:<14} [dim]({t['detect'][0]})[/dim]")
        if not is_detected:
            skipped.append(t["name"])
            continue
        detected_count += 1
        path: Path = t["skill_path"]
        if path.exists() and not force:
            console.print(
                f"    [yellow]exists[/yellow] {path} "
                f"[dim](pass --force to overwrite)[/dim]"
            )
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        body = _frontmatter(t["format"]) + _skill_body(hctl_bin, t["format"])
        path.write_text(body, encoding="utf-8")
        written.append((t["name"], path))

    console.print("")
    if not written:
        console.print(
            "  [dim]No skill files written[/dim] "
            f"[yellow](detected={detected_count}, skipped={len(skipped)})[/yellow]"
        )
    else:
        console.print(f"  [bold]Installed /holoctl skill ({len(written)} target(s)):[/bold]")
        for name, path in written:
            console.print(f"  [green]✓[/green] [bold]{name}[/bold]  [dim]→ {path}[/dim]")
    console.print("")
    console.print(
        "  [bold]Next step:[/bold] open any folder in any of these assistants and "
        "type [cyan]/holoctl[/cyan] — the agent will detect the state and run "
        f"[cyan]{hctl_bin} init[/cyan] / [cyan]upgrade[/cyan] / "
        f"[cyan]boot[/cyan] for you.\n"
    )

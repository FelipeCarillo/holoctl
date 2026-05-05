from __future__ import annotations
from importlib.metadata import version as _pkg_version
from pathlib import Path

import typer
from ._console import console

app = typer.Typer()

try:
    _VERSION = _pkg_version("projhub")
except Exception:
    _VERSION = "unknown"

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "commands"

_PLATFORM_CONFIG: dict[str, dict] = {
    "claude": {
        "template": "projhub-claude.md",
        "dest_dir": Path.home() / ".claude" / "commands",
        "file_name": "projhub.md",
        "label": "Claude Code",
    },
}


def _version_file(dest_dir: Path) -> Path:
    return dest_dir / ".projhub_version"


def _check_installed_version(dest_dir: Path) -> str | None:
    vf = _version_file(dest_dir)
    return vf.read_text(encoding="utf-8").strip() if vf.exists() else None


def _write_version_stamp(dest_dir: Path) -> None:
    _version_file(dest_dir).write_text(_VERSION, encoding="utf-8")


def _refresh_all_version_stamps() -> None:
    for cfg in _PLATFORM_CONFIG.values():
        vf = _version_file(cfg["dest_dir"])
        if vf.exists():
            try:
                vf.write_text(_VERSION, encoding="utf-8")
            except Exception:
                pass


def check_installed_versions() -> list[dict]:
    results = []
    for key, cfg in _PLATFORM_CONFIG.items():
        dest = cfg["dest_dir"] / cfg["file_name"]
        if not dest.exists():
            continue
        installed = _check_installed_version(cfg["dest_dir"])
        results.append({
            "platform": key,
            "label": cfg["label"],
            "dest": dest,
            "installed": installed,
            "current": _VERSION,
        })
    return results


def setup_global(targets: list[str], dry_run: bool = False) -> list[dict]:
    results = []
    for target in targets:
        cfg = _PLATFORM_CONFIG.get(target)
        if not cfg:
            results.append({"target": target, "status": "unknown"})
            continue

        src = _TEMPLATES_DIR / cfg["template"]
        if not src.exists():
            results.append({"target": target, "label": cfg["label"], "status": "missing-template"})
            continue

        dest = cfg["dest_dir"] / cfg["file_name"]
        try:
            if not dry_run:
                cfg["dest_dir"].mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy(src, dest)
                _write_version_stamp(cfg["dest_dir"])
            results.append({"target": target, "label": cfg["label"], "dest": dest, "status": "ok"})
        except Exception as e:
            results.append({"target": target, "label": cfg["label"], "status": "error", "error": str(e)})

    if not dry_run and any(r["status"] == "ok" for r in results):
        _refresh_all_version_stamps()

    return results


@app.command("setup-global")
def setup_global_cmd(
    targets: str = typer.Option("claude", "--targets", help="Comma-separated targets (only 'claude' supported globally)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing files"),
    check: bool = typer.Option(False, "--check", help="Show installed versions without installing"),
):
    """Install /projhub slash command globally for Claude Code.

    Note: Cursor, Windsurf, and Copilot don't support globally-installed slash
    commands. Use `projhub compile` per-project to generate their integration files.
    """
    if check:
        versions = check_installed_versions()
        if not versions:
            console.print("\n  [dim]/projhub is not installed in any known location.[/dim]\n")
            return
        console.print("\n  [bold]projhub setup-global --check[/bold]\n")
        for v in versions:
            stale = v["installed"] and v["installed"] != v["current"]
            badge = (
                f"[yellow]v{v['installed']} → upgrade to v{v['current']}[/yellow]"
                if stale
                else f"[green]v{v['installed'] or 'unknown'} (up to date)[/green]"
            )
            console.print(f"  [bold]{v['label']:<18}[/bold] {badge}")
            console.print(f"  [dim]{v['dest']}[/dim]")
        console.print()
        return

    target_list = [t.strip() for t in targets.split(",") if t.strip()]
    unknown = [t for t in target_list if t not in _PLATFORM_CONFIG]
    if unknown:
        valid = ", ".join(_PLATFORM_CONFIG)
        console.print(f"[red]  Unknown target(s): {', '.join(unknown)}[/red]")
        console.print(f"[dim]  Valid targets: {valid}[/dim]")
        raise typer.Exit(1)

    results = setup_global(target_list, dry_run=dry_run)

    console.print("\n  [bold]projhub setup-global[/bold]\n")
    for r in results:
        if r["status"] == "ok":
            icon = "[dim][dry-run][/dim]" if dry_run else "[green]✓[/green]"
            console.print(f"  {icon} [bold]{r['label']}[/bold]")
            console.print(f"     [dim]{r['dest']}[/dim]")
        elif r["status"] == "error":
            console.print(f"  [red]✗[/red] [bold]{r.get('label', r['target'])}[/bold]: {r['error']}")
        elif r["status"] == "missing-template":
            console.print(f"  [yellow]?[/yellow] [bold]{r.get('label', r['target'])}[/bold]: template not found — reinstall projhub")
        else:
            console.print(f"  [dim]?[/dim] {r['target']}: unknown target")

    ok_count = sum(1 for r in results if r["status"] == "ok")
    if ok_count > 0 and not dry_run:
        s = "s" if ok_count != 1 else ""
        console.print(f"\n  [green]/projhub is now available in {ok_count} tool{s}[/green]\n")
        if "claude" in target_list:
            console.print("[dim]  Open Claude Code and type /projhub to get started.[/dim]\n")

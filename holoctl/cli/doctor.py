from __future__ import annotations
import json
import re
from pathlib import Path

import typer
from ._console import console

from ..lib.config import find_project_root, load_config
from .. import __version__

app = typer.Typer()


_TARGET_OUTPUTS = {
    "claude": ["CLAUDE.md", ".claude/commands"],
    "agents": ["AGENTS.md"],
}


def _semver_lt(a: str, b: str) -> bool:
    def t(v):
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(v).strip())
        return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)
    return t(a) < t(b)


# JSON configs holoctl *merges* into (they legitimately carry user content),
# so they can't be byte-compared for compile drift.
_MERGE_OUTPUTS = frozenset({
    ".claude/settings.json",
})

# Top-level files the `agents` compiler reads to build AGENTS.md's Build/Test
# sections (see `compiler.agents._detect_commands`). The drift check copies
# them into the scratch workspace so AGENTS.md compiles identically.
_BUILD_MARKERS = (
    "package.json", "pyproject.toml", "uv.lock",
    "Cargo.toml", "go.mod", "Makefile", "Justfile", "justfile",
)


@app.command("doctor")
def doctor_cmd(
    global_check: bool = typer.Option(
        False,
        "--global",
        help="Check global router installation drift (Claude Code).",
    ),
    compile_drift: bool = typer.Option(
        False,
        "--compile-drift",
        help="Check whether compiled outputs (CLAUDE.md, AGENTS.md, ...) are "
             "stale vs .holoctl/ — i.e. you edited the source but forgot to recompile.",
    ),
):
    """Check project health.

    First line of output is router-friendly:
      - `holoctl: not initialized`  → no .holoctl/ found
      - `holoctl: outdated`         → workspace below installed hctl version
      - `holoctl: ok`               → workspace healthy

    The Claude `/holoctl` slash router parses this line to choose
    init / upgrade / operate flow.

    Pass `--global` to check ~/.claude router install drift instead of
    project-level health. Pass `--compile-drift` to detect compiled outputs
    that are out of date with their `.holoctl/` source.
    """
    if global_check:
        _doctor_global()
        return

    if compile_drift:
        _doctor_compile_drift()
        return

    root = find_project_root()
    if not root:
        # Router-friendly first line.
        print("holoctl: not initialized")
        console.print(
            "[dim]No .holoctl/ found at or above the current directory. "
            "Run `hctl init` to start.[/dim]"
        )
        raise typer.Exit(1)

    # Detect outdated / ok before any other check (so router gets it fast).
    try:
        config_pre = load_config(root)
        ws_version = config_pre.get("holoctlVersion", "0.0.0")
    except Exception:
        ws_version = "0.0.0"
    if _semver_lt(ws_version, __version__):
        print("holoctl: outdated")
    else:
        print("holoctl: ok")

    console.print("\n  [bold]holoctl doctor[/bold]\n")
    issues = 0
    config = None

    try:
        config = load_config(root)
        _check("Config", ".holoctl/config.json is valid", True)
    except Exception as e:
        _check("Config", f".holoctl/config.json: {e}", False)
        issues += 1

    # Index <-> .md sync
    index_path = root / ".holoctl" / "board" / "index.json"
    tickets_dir = root / ".holoctl" / "board" / "tickets"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            indexed = {t["id"] for t in data.get("tickets", [])}
            on_disk = set()
            if tickets_dir.exists():
                from ..lib.markdown import parse_frontmatter
                for f in tickets_dir.glob("*.md"):
                    if f.name.startswith("_"):
                        continue
                    fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
                    if fm.get("id"):
                        on_disk.add(fm["id"])
            drift = indexed.symmetric_difference(on_disk)
            if drift:
                _check("Board", f"index.json out of sync ({len(drift)} drift) — run `holoctl board rebuild-index`", False)
                issues += 1
            else:
                _check("Board", f"index.json valid ({len(indexed)} tickets, in sync)", True)
        except Exception as e:
            _check("Board", f"index.json parse error: {e}", False)
            issues += 1
    else:
        _check("Board", "index.json exists", False)
        issues += 1

    # Agents
    agents_dir = root / ".holoctl" / "agents"
    if agents_dir.exists():
        agent_count = len(list(agents_dir.glob("*.md")))
        ok = agent_count > 0
        _check("Agents", f"{agent_count} agent(s) defined", ok)
        if not ok:
            issues += 1
    else:
        _check("Agents", "agents/ directory exists", False)
        issues += 1

    # Commands
    commands_dir = root / ".holoctl" / "commands"
    if commands_dir.exists():
        cmd_count = len(list(commands_dir.glob("*.md")))
        ok = cmd_count > 0
        _check("Commands", f"{cmd_count} command(s) defined", ok)
        if not ok:
            issues += 1
    else:
        _check("Commands", "commands/ directory exists", False)
        issues += 1

    # Instructions
    ok = (root / ".holoctl" / "instructions.md").exists()
    _check("Instructions", "instructions.md exists", ok)
    if not ok:
        issues += 1

    # Context
    ok = (root / ".holoctl" / "context").exists()
    _check("Context", "context/ directory exists", ok)
    if not ok:
        issues += 1

    # Compile targets
    if config:
        targets = config.get("targets", [])
        for tgt in targets:
            outputs = _TARGET_OUTPUTS.get(tgt, [])
            missing = [o for o in outputs if not (root / o).exists()]
            if missing:
                _check("Compile", f"target '{tgt}' missing: {', '.join(missing)} — run `holoctl compile`", False)
                issues += 1
            else:
                _check("Compile", f"target '{tgt}' compiled", True)

    console.print("")
    if issues == 0:
        console.print("[green]  All checks passed. Project is healthy.[/green]\n")
    else:
        console.print(f"[yellow]  {issues} issue(s) found.[/yellow]\n")


def _check(category: str, message: str, ok: bool) -> None:
    icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
    console.print(f"  {icon} [dim]{category:<14}[/dim] {message}")


def _doctor_compile_drift() -> None:
    """Detect compiled outputs that are stale vs `.holoctl/`.

    Compiles into a throwaway copy of the workspace, then classifies each
    generated file using the manifest (the header is gone):

      - on-disk missing                          → stale (missing)
      - tracked in the real manifest but its
        on-disk hash != the manifest hash        → hand-edited (intentional;
                                                    NOT drift)
      - on-disk content != freshly-compiled
        content                                  → stale (source changed,
                                                    recompile needed)
      - otherwise                                → up to date

    Merge-based configs (settings.json) are skipped: they carry user content
    and aren't manifest-tracked.
    """
    import shutil
    import tempfile

    from ..lib.compiler import _COMPILERS, compile_project, manifest

    root = find_project_root()
    if not root:
        print("holoctl: not initialized")
        console.print("[red]No .holoctl/ found.[/red]")
        raise typer.Exit(1)
    config = load_config(root)
    targets = [t for t in config.get("targets", []) if t in _COMPILERS]

    # The real (on-disk) manifest: rel -> {"sha256", ...}. Used to tell apart a
    # hand-edit (tracked, hash drifted) from a stale source (source changed).
    real = manifest.load(root)["files"]

    stale: list[str] = []
    hand_edited: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        shutil.copytree(root / ".holoctl", scratch / ".holoctl")
        # Copy build markers so the `agents` target's Build/Test detection
        # matches the real repo (else AGENTS.md would falsely look stale).
        for marker in _BUILD_MARKERS:
            src = root / marker
            if src.is_file():
                shutil.copy2(src, scratch / marker)

        generated: set[str] = set()
        for tgt in targets:
            result = compile_project(scratch, config, tgt, dry_run=False)
            generated.update(result.get("files", []))

        for rel in sorted(generated):
            if rel in _MERGE_OUTPUTS:
                continue
            canonical = scratch / rel
            on_disk = root / rel
            if not canonical.is_file():
                continue
            if not on_disk.exists():
                stale.append(f"{rel} (missing)")
                continue
            try:
                disk_text = on_disk.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # Unreadable as text — fall back to byte compare vs scratch.
                if on_disk.read_bytes() != canonical.read_bytes():
                    stale.append(rel)
                continue
            disk_sha = manifest.sha256_text(disk_text)
            entry = real.get(rel)
            if entry is not None and disk_sha != entry.get("sha256"):
                # Tracked by holoctl but the on-disk content diverged from what
                # we recorded → a deliberate hand-edit, not stale source.
                hand_edited.append(rel)
            elif disk_text != canonical.read_text(encoding="utf-8"):
                # Either untracked-but-present, or tracked-and-matching-manifest
                # while the freshly-compiled content differs → source moved on.
                stale.append(rel)

    if stale:
        print("holoctl: compile-drift")
    else:
        print("holoctl: ok")

    console.print("\n  [bold]hctl doctor --compile-drift[/bold]\n")
    console.print(f"  [dim]targets: {', '.join(targets) or '(none)'}[/dim]\n")
    if stale:
        for rel in stale:
            _check("Drift", f"{rel} is stale — run `holoctl compile`", False)
    if hand_edited:
        for rel in hand_edited:
            _check("Hand-edited", f"{rel} (no holoctl header; left as-is)", True)
    if not stale and not hand_edited:
        _check("Compile", "all outputs up to date with .holoctl/", True)

    console.print("")
    if stale:
        console.print(
            f"[yellow]  {len(stale)} stale output(s). Run "
            f"[bold]hctl compile[/bold] to regenerate.[/yellow]\n"
        )
        raise typer.Exit(1)
    console.print("[green]  Compiled outputs are in sync with .holoctl/.[/green]\n")


def _doctor_global() -> None:
    """Check that the Claude Code global router is installed and current."""
    print("holoctl: global-check")
    console.print("\n  [bold]hctl doctor --global[/bold]\n")

    from ..lib.compiler.template import load_bootstrap

    issues = 0

    # Claude
    claude_path = Path.home() / ".claude" / "commands" / "holoctl.md"
    template = load_bootstrap("holoctl-claude.md")
    if not claude_path.exists():
        _check("Claude", "router missing — run `hctl setup-global --target claude`", False)
        issues += 1
    elif template and claude_path.read_text(encoding="utf-8") != template:
        _check("Claude", "router stale (drift) — run `hctl setup-global --target claude`", False)
        issues += 1
    else:
        _check("Claude", f"router up-to-date ({claude_path})", True)

    console.print("")
    if issues == 0:
        console.print("[green]  Global router up-to-date.[/green]\n")
    else:
        console.print(
            f"[yellow]  {issues} issue(s). Run "
            f"[bold]hctl setup-global --target claude[/bold] to fix.[/yellow]\n"
        )

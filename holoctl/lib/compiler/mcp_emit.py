"""Per-target MCP config emission.

Each function writes the assistant's native MCP config so the holoctl
stdio server is auto-spawned at session start. We resolve the absolute
path to `hctl` via `shutil.which()` to handle uv-tool / pipx / pip-venv
installs uniformly.

Decision (item 1 of the multi-assistant plan): stdio transport, NOT
HTTP daemon. Each assistant spawns its own short-lived `hctl serve --mcp`
process when it needs to call a tool. No PID files, no daemon, works on
Windows trivially.

Coexists with user-managed MCP servers (item 2A): we merge into the
existing config without overwriting other servers. If the user has their
own `mcpServers.foo` we leave it alone and only add/update
`mcpServers.holoctl`.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


SERVER_KEY = "holoctl"


def _resolve_hctl_bin() -> str:
    env = os.environ.get("HOLOCTL_BIN")
    if env:
        return env
    via_path = shutil.which("hctl") or shutil.which("holoctl")
    if via_path:
        return via_path
    return f"{sys.executable} -m holoctl"


def _holoctl_server_entry() -> dict:
    return {
        "command": _resolve_hctl_bin(),
        "args": ["serve", "--mcp"],
    }


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _merge_mcp_server(existing: dict, server_key: str, entry: dict) -> dict:
    """Set `mcpServers.<server_key> = entry` non-destructively."""
    out = dict(existing)
    servers = dict(out.get("mcpServers") or {})
    servers[server_key] = entry
    out["mcpServers"] = servers
    return out


# ----------------------------------------------------------------------
# Per-target emitters
# ----------------------------------------------------------------------


def emit_claude(project_root: Path, dry_run: bool = False) -> list[str]:
    """Merge into `.claude/settings.json:mcpServers.holoctl`."""
    path = project_root / ".claude" / "settings.json"
    existing = _read_json(path)
    merged = _merge_mcp_server(existing, SERVER_KEY, _holoctl_server_entry())
    if not dry_run:
        _write_json(path, merged)
    return [".claude/settings.json"]


def emit_cursor(project_root: Path, dry_run: bool = False) -> list[str]:
    """Write `.cursor/mcp.json:mcpServers.holoctl`."""
    path = project_root / ".cursor" / "mcp.json"
    existing = _read_json(path)
    merged = _merge_mcp_server(existing, SERVER_KEY, _holoctl_server_entry())
    if not dry_run:
        _write_json(path, merged)
    return [".cursor/mcp.json"]


def emit_copilot(project_root: Path, dry_run: bool = False) -> list[str]:
    """Write `.vscode/mcp.json:servers.holoctl` (Copilot-in-VSCode)."""
    path = project_root / ".vscode" / "mcp.json"
    existing = _read_json(path)
    out = dict(existing)
    servers = dict(out.get("servers") or {})
    servers[SERVER_KEY] = _holoctl_server_entry()
    out["servers"] = servers
    if not dry_run:
        _write_json(path, out)
    return [".vscode/mcp.json"]


def emit_windsurf(project_root: Path, dry_run: bool = False) -> list[str]:
    """Write `.windsurf/mcp.json` (workspace-level; user-level whitelist may apply)."""
    path = project_root / ".windsurf" / "mcp.json"
    existing = _read_json(path)
    merged = _merge_mcp_server(existing, SERVER_KEY, _holoctl_server_entry())
    if not dry_run:
        _write_json(path, merged)
    return [".windsurf/mcp.json"]


def emit_devin(project_root: Path, dry_run: bool = False) -> list[str]:
    """Write `.devin/mcp.json` (best-effort given doc sparseness)."""
    path = project_root / ".devin" / "mcp.json"
    existing = _read_json(path)
    merged = _merge_mcp_server(existing, SERVER_KEY, _holoctl_server_entry())
    if not dry_run:
        _write_json(path, merged)
    return [".devin/mcp.json"]

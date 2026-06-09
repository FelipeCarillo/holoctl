"""Per-target MCP config emission.

Each function writes the assistant's native MCP config so the holoctl
stdio server is auto-spawned at session start. We emit the generalist
`hctl` command (PATH-resolved) rather than an absolute exe path, so the
committed config stays portable across machines / users / assistants.
Set `HOLOCTL_BIN` to override for installs where `hctl` isn't on PATH.

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
from pathlib import Path


SERVER_KEY = "holoctl"


def _resolve_hctl_bin() -> str:
    # Bare command name, not an absolute exe path — see module docstring.
    return os.environ.get("HOLOCTL_BIN") or "hctl"


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
# Emitter (Claude Code only — other assistants self-configure via the
# holoctl-foreign-bootstrap skill).
# ----------------------------------------------------------------------


def emit_claude(project_root: Path, dry_run: bool = False) -> list[str]:
    """Merge into `.claude/settings.json:mcpServers.holoctl`."""
    path = project_root / ".claude" / "settings.json"
    existing = _read_json(path)
    merged = _merge_mcp_server(existing, SERVER_KEY, _holoctl_server_entry())
    # Incremental skip: setting the same server entry is idempotent, so on an
    # unchanged re-compile ``merged == existing``. Skip the write to preserve
    # mtime / avoid git churn. Still report the file as emitted.
    if not dry_run and merged != existing:
        _write_json(path, merged)
    return [".claude/settings.json"]

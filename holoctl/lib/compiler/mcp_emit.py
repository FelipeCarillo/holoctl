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


def emit_codex(project_root: Path, dry_run: bool = False) -> list[str]:
    """Merge into `.codex/config.toml:[mcp_servers.holoctl]`.

    Codex (OpenAI CLI) reads project-scoped config from `.codex/config.toml`
    when the project is trusted. The `[mcp_servers.<id>]` table is the
    canonical place to declare stdio MCP servers per the Codex spec
    (`command`, `args`, optional `enabled`).

    TOML is round-tripped via a tolerant line-based merge — we don't pull a
    full TOML parser; we just rewrite the `[mcp_servers.holoctl]` table.
    """
    entry = _holoctl_server_entry()
    path = project_root / ".codex" / "config.toml"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    block_lines = [
        "[mcp_servers.holoctl]",
        f'command = "{_toml_escape(entry["command"])}"',
        "args = [" + ", ".join(f'"{_toml_escape(a)}"' for a in entry["args"]) + "]",
    ]
    new_block = "\n".join(block_lines) + "\n"

    merged = _replace_or_append_toml_table(
        existing, "mcp_servers.holoctl", new_block
    )

    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(merged, encoding="utf-8")
    return [".codex/config.toml"]


def _toml_escape(s: str) -> str:
    """Escape a TOML basic string (double-quoted)."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _replace_or_append_toml_table(text: str, table_path: str, new_block: str) -> str:
    """Replace `[table_path]` ... block in `text` with `new_block`.

    A 'table block' is `[table_path]` plus following lines until the next
    `[...]` header or EOF. If `[table_path]` is not present, append the block
    with a separating blank line.
    """
    header = f"[{table_path}]"
    lines = text.splitlines(keepends=False)
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        sep = "" if (not text or text.endswith("\n\n")) else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + new_block
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].lstrip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = i
            break
    new_lines = lines[:start] + new_block.rstrip("\n").splitlines() + lines[end:]
    result = "\n".join(new_lines)
    if not result.endswith("\n"):
        result += "\n"
    return result

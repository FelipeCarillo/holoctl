"""MCP configuration introspection helpers.

Reads the MCP servers configured for the project from the two canonical
sources Claude Code uses:

  - ``<root>/.mcp.json``           — project-level MCP config
  - ``<root>/.claude/settings.json`` — Claude Code settings (holoctl itself
                                        registers ``mcpServers.holoctl`` here)

The read helpers are intentionally robust: missing, empty, or corrupt files
contribute nothing and never raise.

These functions allow the provider catalog to annotate each provider with
whether its MCP server is currently configured in the project — enabling
``hctl provider list`` to show connection status and ``hctl provider doctor``
to cross-check the whole catalog.
"""
from __future__ import annotations

import json
from pathlib import Path


def _read_json_safe(path: Path) -> dict:
    """Return parsed JSON dict from *path*, or empty dict on any error."""
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def read_mcp_servers(root: Path) -> set[str]:
    """Return the set of MCP server names configured for the project.

    Reads ``mcpServers`` keys from BOTH ``<root>/.mcp.json`` and
    ``<root>/.claude/settings.json`` and returns their union.  Missing,
    empty, or corrupt files contribute nothing and never raise.
    """
    sources = [
        root / ".mcp.json",
        root / ".claude" / "settings.json",
    ]
    servers: set[str] = set()
    for path in sources:
        data = _read_json_safe(path)
        mcp_servers = data.get("mcpServers")
        if isinstance(mcp_servers, dict):
            servers.update(mcp_servers.keys())
    return servers


def server_for_tool(tool_name: str) -> str | None:
    """Extract the MCP server name from a tool name of the form ``mcp__<server>__<tool>``.

    Returns the ``<server>`` segment (the part between the leading ``mcp__``
    and the next ``__``).  Returns *None* if the string doesn't match that
    shape (e.g. it's empty, has no leading ``mcp__``, or has no second ``__``).

    Examples::

        >>> server_for_tool("mcp__linear__get_issue")
        'linear'
        >>> server_for_tool("mcp__azure_devops__get_work_item")
        'azure_devops'
        >>> server_for_tool("not_an_mcp_tool")
        None
    """
    if not tool_name or not tool_name.startswith("mcp__"):
        return None
    rest = tool_name[len("mcp__"):]  # strip leading "mcp__"
    idx = rest.find("__")
    if idx < 1:  # must have at least one char before the second __
        return None
    return rest[:idx]


def is_tool_connected(tool_name: str, servers: set[str]) -> bool:
    """Return True iff the MCP server for *tool_name* is in *servers*.

    We can only know the **server** is configured (via ``.mcp.json`` /
    ``.claude/settings.json``) — we cannot verify the exact tool exists
    without a live MCP connection.  That is the honest semantic: "the MCP
    server providing this tool is configured."

    Returns False for tool names that don't match the ``mcp__<server>__<tool>``
    pattern.
    """
    server = server_for_tool(tool_name)
    if server is None:
        return False
    return server in servers

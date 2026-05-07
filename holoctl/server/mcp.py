"""Minimal MCP (Model Context Protocol) server over stdio.

Implements just enough of the JSON-RPC over stdio protocol for the
holoctl tools to be discoverable and callable from any MCP-aware client
(Claude Code, Cursor, Copilot, Windsurf, Devin).

We don't depend on the `mcp` Python package because:
  1. Adds a 5MB+ install footprint for ~150 lines of protocol logic.
  2. The MCP spec is intentionally small — JSON-RPC 2.0 with three
     standard methods (`initialize`, `tools/list`, `tools/call`) plus
     a few notifications.
  3. Cold-start latency matters: each MCP call spawns a new Python
     process via stdio, so import-cheap matters.

Tool surface (write tools land in `permissions.ask` per item 2A of the
multi-assistant plan):

  Read tools (auto-approved by clients):
    holoctl.board_list, holoctl.board_get
    holoctl.memory_list_topics, holoctl.memory_read_topic, holoctl.memory_search
    holoctl.journal_recent
    holoctl.agent_list_available
    holoctl.curate_suggestions

  Write tools (require user approval):
    holoctl.board_create, holoctl.board_move, holoctl.board_set
    holoctl.memory_add
    holoctl.agent_add
    holoctl.curate_silence

All tool outputs are JSON-stringified per item 4 of the plan; clients
parse and render natively.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "holoctl"


# ----------------------------------------------------------------------
# Tool registry — declarative.
# Each entry: (name, description, schema, handler, write?)
# ----------------------------------------------------------------------


def _project_root() -> Path:
    from ..lib.config import find_project_root
    root = find_project_root()
    if root is None:
        raise RuntimeError(
            "No .holoctl/ found in cwd or parents. The MCP server must be "
            "started from inside a holoctl-managed workspace."
        )
    return root


def _tool_board_list(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    filters: dict[str, Any] = {}
    for key in ("status", "priority", "agent", "tag", "sprint"):
        if key in args:
            filters[key] = args[key]
    return {"tickets": board.ls(filters) if filters else board.ls()}


def _tool_board_get(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    tid = args.get("id")
    if not tid:
        raise ValueError("missing required arg: id")
    t = board.get(tid)
    if t is None:
        raise ValueError(f"ticket not found: {tid}")
    return t


def _tool_board_create(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    return board.add(args)


def _tool_board_move(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    tid = args.get("id")
    status = args.get("status")
    if not tid or not status:
        raise ValueError("missing required args: id, status")
    return board.move(tid, status)


def _tool_board_set(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    tid = args.get("id")
    field = args.get("field")
    value = args.get("value")
    if not tid or not field:
        raise ValueError("missing required args: id, field")
    return board.set(tid, field, value)


def _tool_memory_list_topics(args: dict) -> Any:
    from ..lib.memory import Memory
    mem = Memory(_project_root())
    return {
        "topics": [
            {
                "name": t.name,
                "scope": t.scope,
                "description": t.description,
                "globs": t.globs,
            }
            for t in mem.list_topics()
        ],
        "has_index": mem.index_path.exists(),
    }


def _tool_memory_read_topic(args: dict) -> Any:
    from ..lib.memory import Memory
    mem = Memory(_project_root())
    name = args.get("name")
    if not name:
        raise ValueError("missing required arg: name")
    if name in ("MEMORY", "index", "MEMORY.md"):
        return {"name": "MEMORY", "body": mem.read_index()}
    t = mem.get_topic(name)
    if t is None:
        raise ValueError(f"topic not found: {name}")
    return {
        "name": t.name,
        "scope": t.scope,
        "description": t.description,
        "globs": t.globs,
        "body": t.body,
    }


def _tool_memory_search(args: dict) -> Any:
    from ..lib.memory import Memory
    mem = Memory(_project_root())
    q = args.get("query")
    if not q:
        raise ValueError("missing required arg: query")
    return {"hits": mem.search(q)}


def _tool_memory_add(args: dict) -> Any:
    from ..lib.memory import Memory
    mem = Memory(_project_root())
    name = args.get("name")
    body = args.get("body", "")
    scope = args.get("scope", "lazy")
    description = args.get("description", "")
    globs = args.get("globs", []) or []
    if not name:
        raise ValueError("missing required arg: name")
    t = mem.add_topic(
        name,
        body=body,
        scope=scope,
        description=description,
        globs=globs,
        overwrite=bool(args.get("overwrite")),
    )
    return {"name": t.name, "scope": t.scope}


def _tool_journal_recent(args: dict) -> Any:
    from ..lib.journal import Journal
    j = Journal(_project_root())
    return {
        "records": j.recent(
            limit=int(args.get("limit", 30)),
            since=args.get("since"),
            kind=args.get("kind"),
            source=args.get("source"),
        )
    }


def _tool_agent_list_available(args: dict) -> Any:
    from ..lib.agent_library import list_library_agents
    root = _project_root()
    active = sorted(
        p.stem for p in (root / ".holoctl" / "agents").glob("*.md")
    )
    library = list_library_agents()
    return {
        "active": active,
        "library": [n for n in library if n not in active],
    }


def _tool_agent_add(args: dict) -> Any:
    from ..lib.agent_library import materialize_agent
    from ..lib.config import load_config
    root = _project_root()
    config = load_config(root)
    name = args.get("name")
    if not name:
        raise ValueError("missing required arg: name")
    body = materialize_agent(name, config)
    if body is None:
        raise ValueError(f"persona not in library: {name}")
    target = root / ".holoctl" / "agents" / f"{name}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return {"name": name, "path": str(target.relative_to(root)).replace("\\", "/")}


def _tool_curate_suggestions(args: dict) -> Any:
    """Stub until 0.14 implements the curator engine. Returns empty list."""
    return {
        "suggestions": [],
        "note": "Curator engine arrives in 0.14. Use `hctl curate show` once available.",
    }


def _tool_curate_silence(args: dict) -> Any:
    """Stub until 0.14."""
    return {"silenced": False, "note": "Curator engine arrives in 0.14."}


TOOLS: list[dict] = [
    {
        "name": "holoctl.board_list",
        "description": "List tickets on the project board with optional filters.",
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "priority": {"type": "string"},
                "agent": {"type": "string"},
                "tag": {"type": "string"},
                "sprint": {"type": "string"},
            },
        },
        "handler": _tool_board_list,
        "write": False,
    },
    {
        "name": "holoctl.board_get",
        "description": "Get a single ticket by ID.",
        "schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        "handler": _tool_board_get,
        "write": False,
    },
    {
        "name": "holoctl.board_create",
        "description": "Create a new ticket. Pass title, agent, priority, goal, etc.",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "agent": {"type": "string"},
                "priority": {"type": "string"},
                "projects": {"type": "array", "items": {"type": "string"}},
                "files": {"type": "array", "items": {"type": "string"}},
                "goal": {"type": "array", "items": {"type": "string"}},
                "context": {"type": "string"},
                "outOfScope": {"type": "string"},
                "executionNotes": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "sprint": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["title"],
        },
        "handler": _tool_board_create,
        "write": True,
    },
    {
        "name": "holoctl.board_move",
        "description": "Transition a ticket's status (e.g. backlog→doing).",
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["id", "status"],
        },
        "handler": _tool_board_move,
        "write": True,
    },
    {
        "name": "holoctl.board_set",
        "description": "Set a single field on a ticket (e.g. priority, sprint).",
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "field": {"type": "string"},
                "value": {},
            },
            "required": ["id", "field"],
        },
        "handler": _tool_board_set,
        "write": True,
    },
    {
        "name": "holoctl.memory_list_topics",
        "description": "List memory topics with their scope and description.",
        "schema": {"type": "object", "properties": {}},
        "handler": _tool_memory_list_topics,
        "write": False,
    },
    {
        "name": "holoctl.memory_read_topic",
        "description": "Read the body of a memory topic (or 'MEMORY' for the index).",
        "schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "handler": _tool_memory_read_topic,
        "write": False,
    },
    {
        "name": "holoctl.memory_search",
        "description": "Substring-search memory index + topics.",
        "schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "handler": _tool_memory_search,
        "write": False,
    },
    {
        "name": "holoctl.memory_add",
        "description": "Create a memory topic. scope: always_on | lazy | glob.",
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "body": {"type": "string"},
                "scope": {"type": "string"},
                "description": {"type": "string"},
                "globs": {"type": "array", "items": {"type": "string"}},
                "overwrite": {"type": "boolean"},
            },
            "required": ["name", "body"],
        },
        "handler": _tool_memory_add,
        "write": True,
    },
    {
        "name": "holoctl.journal_recent",
        "description": "List recent journal records (session/tool events).",
        "schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "since": {"type": "string"},
                "kind": {"type": "string"},
                "source": {"type": "string"},
            },
        },
        "handler": _tool_journal_recent,
        "write": False,
    },
    {
        "name": "holoctl.agent_list_available",
        "description": "List active personas + the latent library catalog.",
        "schema": {"type": "object", "properties": {}},
        "handler": _tool_agent_list_available,
        "write": False,
    },
    {
        "name": "holoctl.agent_add",
        "description": "Activate a persona from the library into .holoctl/agents/.",
        "schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "handler": _tool_agent_add,
        "write": True,
    },
    {
        "name": "holoctl.curate_suggestions",
        "description": "Get current curator suggestions (stubbed in 0.13; engine in 0.14).",
        "schema": {"type": "object", "properties": {}},
        "handler": _tool_curate_suggestions,
        "write": False,
    },
    {
        "name": "holoctl.curate_silence",
        "description": "Suppress a curator pattern for 14 days (stubbed in 0.13).",
        "schema": {
            "type": "object",
            "properties": {"pattern_id": {"type": "string"}},
            "required": ["pattern_id"],
        },
        "handler": _tool_curate_silence,
        "write": True,
    },
]


def list_tools(*, write: bool | None = None) -> list[dict]:
    if write is None:
        return list(TOOLS)
    return [t for t in TOOLS if t["write"] is write]


def find_tool(name: str) -> dict | None:
    for t in TOOLS:
        if t["name"] == name:
            return t
    return None


# ----------------------------------------------------------------------
# JSON-RPC plumbing
# ----------------------------------------------------------------------


def _make_response(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _make_error(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    err: dict = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _content_text(value: Any) -> dict:
    return {
        "content": [
            {"type": "text", "text": json.dumps(value, ensure_ascii=False, default=str)}
        ]
    }


def handle(message: dict) -> dict | None:
    """Dispatch a single JSON-RPC message. Returns response dict or None for notifications."""
    method = message.get("method")
    req_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _make_response(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": _version()},
        })

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _make_response(req_id, {
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["schema"],
                }
                for t in TOOLS
            ]
        })

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = find_tool(name) if name else None
        if tool is None:
            return _make_error(req_id, -32601, f"Unknown tool: {name}")
        try:
            result = tool["handler"](args)
        except Exception as exc:
            tb = traceback.format_exc()
            return _make_error(
                req_id, -32000, f"{type(exc).__name__}: {exc}", {"trace": tb}
            )
        return _make_response(req_id, _content_text(result))

    if method == "shutdown":
        return _make_response(req_id, {})

    return _make_error(req_id, -32601, f"Method not found: {method}")


def _version() -> str:
    from .. import __version__
    return __version__


def serve_stdio() -> None:
    """Read JSON-RPC messages from stdin, write responses to stdout."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(
                _make_error(None, -32700, "Parse error")
            ) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()

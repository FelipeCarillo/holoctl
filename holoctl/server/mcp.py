"""Minimal MCP (Model Context Protocol) server over stdio.

Implements just enough of the JSON-RPC over stdio protocol for the
holoctl tools to be discoverable and callable from any MCP-aware client
(Claude Code, Copilot, Codex, and other MCP-aware assistants).

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
    for key in ("status", "priority", "agent", "tag", "sprint", "kind", "parent", "project"):
        if key in args:
            filters[key] = args[key]
    return {"tickets": board.ls(filters) if filters else board.ls()}


def _tool_board_children(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    pid = args.get("id")
    if not pid:
        raise ValueError("missing required arg: id")
    return board.children(pid)


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


def _tool_board_show(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    tid = args.get("id")
    if not tid:
        raise ValueError("missing required arg: id")
    return board.show(tid)


def _tool_board_ack(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    tid = args.get("id")
    idx = args.get("idx")
    if not tid or idx is None:
        raise ValueError("missing required args: id, idx")
    return board.ack(tid, int(idx))


def _tool_board_note(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    tid = args.get("id")
    text = args.get("text")
    if not tid or not text:
        raise ValueError("missing required args: id, text")
    return board.note(tid, str(text))


def _tool_board_batch(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    shared = args.get("shared") or {}
    tickets = args.get("tickets") or []
    return board.batch_add(shared, tickets)


def _tool_board_delete(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    tid = args.get("id")
    if not tid:
        raise ValueError("missing required arg: id")
    return board.delete(tid)


def _tool_board_batch_move(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    ids = args.get("ids") or []
    status = args.get("status")
    if not ids or not status:
        raise ValueError("missing required args: ids, status")
    return board.batch_move(list(ids), status)


def _tool_board_batch_set(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    ids = args.get("ids") or []
    field = args.get("field")
    value = args.get("value")
    if not ids or not field:
        raise ValueError("missing required args: ids, field")
    return board.batch_set(list(ids), field, value)


def _tool_board_batch_delete(args: dict) -> Any:
    from ..lib.board import Board
    from ..lib.config import load_config
    root = _project_root()
    board = Board(root, load_config(root))
    ids = args.get("ids") or []
    if not ids:
        raise ValueError("missing required arg: ids")
    return board.batch_delete(list(ids))


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


def _tool_agent_create(args: dict) -> Any:
    """Create a NEW custom persona (one not in the library) from a designed body.

    Used by the /agent-new workflow after the agent-designer persona has
    drafted the body. Writes to .holoctl/agents/<name>.md directly; user
    has already approved via permissions.ask gating on the MCP call.
    """
    from ..lib.markdown import parse_frontmatter
    root = _project_root()
    name = args.get("name")
    body = args.get("body")
    if not name or not body:
        raise ValueError("missing required args: name, body")
    # Validate name: kebab-case, no path separators.
    import re as _re
    if not _re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError(f"invalid name {name!r}: must be lowercase kebab-case")
    # Validate body has parseable frontmatter with at least `name` and `description`.
    fm, body_md = parse_frontmatter(body)
    if not fm.get("name"):
        raise ValueError("body's frontmatter is missing `name:` field")
    if not fm.get("description"):
        raise ValueError("body's frontmatter is missing `description:` field")
    if str(fm["name"]) != name:
        raise ValueError(
            f"frontmatter name {fm['name']!r} doesn't match arg name {name!r}"
        )
    if not body_md.strip():
        raise ValueError("body markdown is empty (no content after frontmatter)")
    # Refuse to clobber an existing active persona.
    agents_dir = root / ".holoctl" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    target = agents_dir / f"{name}.md"
    if target.exists() and not args.get("force"):
        raise ValueError(
            f"persona {name!r} already active at .holoctl/agents/{name}.md — "
            f"pass `force: true` to overwrite"
        )
    target.write_text(body, encoding="utf-8")
    return {
        "name": name,
        "path": str(target.relative_to(root)).replace("\\", "/"),
        "model": fm.get("model", "standard"),
        "paths": fm.get("paths", []),
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
    from ..lib.curator import _load_ticket_meta
    import json as _json
    root = _project_root()
    index_path = root / ".holoctl" / "board" / "index.json"
    if not index_path.exists():
        return {"suggestions": []}
    data = _json.loads(index_path.read_text(encoding="utf-8"))
    out = []
    for t in data.get("tickets", []) or []:
        if "meta:curate" not in (t.get("tags") or []):
            continue
        if t.get("status") in ("done", "cancelled"):
            continue
        meta = _load_ticket_meta(root, t.get("id", "")) or {}
        out.append({
            "id": t.get("id"),
            "title": t.get("title"),
            "pattern_id": meta.get("curator_pattern_id"),
            "action": meta.get("curator_action"),
            "rule": meta.get("curator_rule"),
        })
    return {"suggestions": out}


def _tool_config_show(args: dict) -> Any:
    """Return the resolved workspace config (defaults merged with .holoctl/config.json)."""
    from ..lib.config import load_config
    root = _project_root()
    return load_config(root)


def _tool_curate_silence(args: dict) -> Any:
    from ..lib.curator import silence_pattern, SUPPRESSION_DAYS
    pid = args.get("pattern_id")
    if not pid:
        raise ValueError("missing required arg: pattern_id")
    days = int(args.get("days", SUPPRESSION_DAYS))
    silence_pattern(_project_root(), pid, days=days)
    return {"silenced": True, "pattern_id": pid, "days": days}


TOOLS: list[dict] = [
    {
        "name": "holoctl.board_list",
        "description": "List work items on the project board with optional filters.",
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "priority": {"type": "string"},
                "agent": {"type": "string"},
                "tag": {"type": "string"},
                "sprint": {"type": "string"},
                "kind": {
                    "type": "string",
                    "description": "Filter by kind: task | story | bug | spec | epic | rfc | ...",
                },
                "parent": {
                    "type": "string",
                    "description": "Filter by parent ID — children of a spec/story/epic",
                },
                "project": {"type": "string"},
            },
        },
        "handler": _tool_board_list,
        "write": False,
    },
    {
        "name": "holoctl.board_children",
        "description": (
            "Return direct children of a work item plus aggregate DoD progress. "
            "Use to inspect how a spec/story/epic is doing — list of child tasks, "
            "their statuses, and total/acked DoD counts."
        ),
        "schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        "handler": _tool_board_children,
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
        "description": (
            "Create a new work item. The CLI generates id, status, created, "
            "updated, completed automatically — never pass those. Required: "
            "title. Recommended: agent, priority, acceptance, files. The `kind` "
            "field (default 'task') marks story/bug/spec/epic; `parent` links "
            "to a containing item (e.g. a task whose parent is a spec). "
            "`source_*` fields preserve the external-board origin (Trello, "
            "Linear, Azure DevOps, GitHub, Slack)."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "verb + object"},
                "kind": {
                    "type": "string",
                    "description": "task (default) | story | bug | spec | epic | rfc | incident | ...",
                },
                "parent": {
                    "type": "string",
                    "description": "ID of the containing work item, if any (e.g. spec ID for tasks).",
                },
                "agent": {"type": "string", "description": "one of the personas in .holoctl/agents/"},
                "priority": {"type": "string", "enum": ["p0", "p1", "p2", "p3"]},
                "acceptance": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "DoD criteria (preferred name; goal is a legacy alias)",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "paths this ticket touches; recommended for parallel decomposition",
                },
                "projects": {"type": "array", "items": {"type": "string"}},
                "context": {"type": "string", "description": "why this ticket exists"},
                "out_of_scope": {"type": "string", "description": "what NOT to do (preferred name)"},
                "depends": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source_provider": {
                    "type": "string",
                    "description": "trello | linear | azure_devops | jira | github | slack | shortcut | manual",
                },
                "source_ref": {"type": "string", "description": "Native ID on the source board (e.g. ENG-123, #4567)"},
                "source_url": {"type": "string", "description": "Canonical URL of the source item"},
                "source_label": {"type": "string", "description": "Short human label for the source ('Card ABC: Add JWT')"},
                "goal": {"type": "array", "items": {"type": "string"}, "description": "DEPRECATED: use `acceptance`"},
                "outOfScope": {"type": "string", "description": "DEPRECATED: use `out_of_scope`"},
            },
            "required": ["title"],
        },
        "handler": _tool_board_create,
        "write": True,
    },
    {
        "name": "holoctl.board_batch",
        "description": (
            "Create N parallel-safe tickets atomically. Each ticket MUST declare "
            "`files` and the file sets MUST be disjoint between siblings — the "
            "CLI rejects overlap before creating anything. Prefer this over "
            "board_create when work can be split into independent pieces."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "shared": {
                    "type": "object",
                    "description": "Fields merged into every ticket (tags, projects, sprint).",
                },
                "tickets": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Each item is a ticket spec — same shape as board_create.",
                },
            },
            "required": ["tickets"],
        },
        "handler": _tool_board_batch,
        "write": True,
    },
    {
        "name": "holoctl.board_show",
        "description": (
            "Read a ticket's full content (frontmatter + body) — the single "
            "source of truth for inspection. Use this instead of reading the "
            ".md file directly (which is blocked by permissions.deny)."
        ),
        "schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        "handler": _tool_board_show,
        "write": False,
    },
    {
        "name": "holoctl.board_ack",
        "description": (
            "Toggle a Definition-of-Done checkbox by zero-based index. "
            "Counts checkboxes in document order. Use this instead of editing "
            "the .md file by hand."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "idx": {"type": "integer", "description": "zero-based DoD index"},
            },
            "required": ["id", "idx"],
        },
        "handler": _tool_board_ack,
        "write": True,
    },
    {
        "name": "holoctl.board_note",
        "description": (
            "Append a timestamped note to the ticket's # Notes section. "
            "Append-only — never rewrites existing notes."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["id", "text"],
        },
        "handler": _tool_board_note,
        "write": True,
    },
    {
        "name": "holoctl.board_delete",
        "description": (
            "Hard-delete a ticket: removes the .md file AND the index entry. "
            "Irreversible. For soft-delete use board_move with status='cancelled'."
        ),
        "schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        "handler": _tool_board_delete,
        "write": True,
    },
    {
        "name": "holoctl.board_batch_move",
        "description": (
            "Move N tickets to the same status in one call. Atomic per-ticket; "
            "returns {moved: [...], errors: [...]} so partial success is visible."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string"},
            },
            "required": ["ids", "status"],
        },
        "handler": _tool_board_batch_move,
        "write": True,
    },
    {
        "name": "holoctl.board_batch_set",
        "description": (
            "Set the same field=value on N tickets. Atomic per-ticket; "
            "returns {updated: [...], errors: [...]}."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"}},
                "field": {"type": "string"},
                "value": {},
            },
            "required": ["ids", "field"],
        },
        "handler": _tool_board_batch_set,
        "write": True,
    },
    {
        "name": "holoctl.board_batch_delete",
        "description": (
            "Hard-delete N tickets in one call. Atomic per-ticket; "
            "returns {deleted: [...], errors: [...]}. Irreversible."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["ids"],
        },
        "handler": _tool_board_batch_delete,
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
        "name": "holoctl.agent_create",
        "description": (
            "Create a NEW custom persona — one not in the library — by writing "
            "a pre-designed body to .holoctl/agents/<name>.md. The body must "
            "have valid frontmatter (name, description) and non-empty content. "
            "Used by /agent-new after agent-designer drafts the persona."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "kebab-case persona name"},
                "body": {
                    "type": "string",
                    "description": "Complete .md content — frontmatter + markdown body, designed by agent-designer.",
                },
                "force": {
                    "type": "boolean",
                    "description": "Overwrite if persona already active (default: false — refuse to clobber).",
                },
            },
            "required": ["name", "body"],
        },
        "handler": _tool_agent_create,
        "write": True,
    },
    {
        "name": "holoctl.config_show",
        "description": (
            "Return the resolved workspace config — defaults merged with "
            ".holoctl/config.json. Read-only. Use to discover provider catalog "
            "(`providers.<name>.url_pattern` / `.mcp_fetch_tool`), board "
            "config (statuses/priorities), and project metadata without "
            "parsing the file directly."
        ),
        "schema": {"type": "object", "properties": {}},
        "handler": _tool_config_show,
        "write": False,
    },
    {
        "name": "holoctl.curate_suggestions",
        "description": "Get current curator suggestions (open meta:curate tickets on the board).",
        "schema": {"type": "object", "properties": {}},
        "handler": _tool_curate_suggestions,
        "write": False,
    },
    {
        "name": "holoctl.curate_silence",
        "description": "Suppress a curator pattern for 14 days.",
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

    if method == "ping":
        # MCP keep-alive. Spec: empty result object.
        return _make_response(req_id, {})

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

    # Unknown method. A JSON-RPC notification (no `id`) must never receive a
    # response — returning an error here would violate the protocol and can
    # confuse strict clients that send `notifications/cancelled` et al.
    if req_id is None:
        return None
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

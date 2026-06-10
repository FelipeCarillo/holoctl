"""Pure validation helpers for the board.

Extracted from the former ``holoctl/lib/board.py`` god module (item 5.3).
Every function here is side-effect free with respect to board state: the only
I/O is ``valid_agents`` listing ``.holoctl/agents/*.md`` to resolve the set of
defined personas. Raises ``ValueError`` / ``KeyError`` with the exact messages
the monolith raised — callers (CLI, MCP server) surface them verbatim.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..ticket import Ticket


def _normalize_array(val) -> list:
    if not val or val == "null":
        return []
    if isinstance(val, list):
        return val
    return [s.strip() for s in str(val).split(",") if s.strip()]


def _parse_set_value(value: str):
    """Parse a CLI-supplied value into a Python type. Falls back to string."""
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def valid_agents(project_root: Path) -> set[str]:
    """Names of agents the agent file system has defined.

    Returns the stems of `.holoctl/agents/*.md`. Used for validating that
    a ticket's `agent:` value refers to a real persona.
    """
    agents_dir = project_root / ".holoctl" / "agents"
    if not agents_dir.exists():
        return set()
    return {f.stem for f in agents_dir.glob("*.md")}


def validate_status(status: str, valid: list[str]) -> None:
    if status not in valid:
        raise ValueError(f"Invalid status: {status!r}. Valid: {', '.join(valid)}")


def validate_priority(priority: str, valid: list[str]) -> None:
    if priority not in valid:
        raise ValueError(f"Invalid priority: {priority!r}. Valid: {', '.join(valid)}")


def validate_agents(agents: list[str], project_root: Path) -> None:
    if not agents:
        return
    defined = valid_agents(project_root)
    if not defined:
        raise ValueError(
            "No agents defined in .holoctl/agents/. "
            "Run `holoctl agent add <name>` (or restore the templates with `holoctl sync --agents`) before assigning a ticket."
        )
    unknown = [a for a in agents if a not in defined]
    if unknown:
        raise ValueError(
            f"Unknown agent(s): {', '.join(unknown)}. "
            f"Defined: {', '.join(sorted(defined))}"
        )


def validate_parent_change(
    tickets: list[Ticket], child_id: str, new_parent: object
) -> str | None:
    """Reject self-parenting, missing parents, and cycles.

    Walks the proposed ancestor chain; if it loops back to ``child_id``
    the move would close a cycle in the hierarchy. Empty/None clears
    the parent (orphan-by-design).
    """
    if new_parent is None or new_parent == "":
        return None
    parent_id = str(new_parent).strip()
    if not parent_id:
        return None
    if parent_id == child_id:
        raise ValueError(
            f"Refusing to set parent: ticket {child_id} cannot be its own parent (cycle)."
        )
    by_id: dict[str, Ticket] = {t["id"]: t for t in tickets}
    if parent_id not in by_id:
        raise KeyError(
            f"Parent ticket {parent_id} not found. "
            "Create it first or pass an existing ID."
        )
    # Walk up: if we ever land on child_id, the new parent is actually
    # a descendant — would close a cycle. Cap depth as a belt-and-braces
    # guard against any pre-existing corruption.
    seen: set[str] = set()
    cursor: str | None = parent_id
    for _ in range(len(tickets) + 1):
        if cursor is None or cursor == "":
            return parent_id
        if cursor == child_id:
            raise ValueError(
                f"Refusing to set parent: {parent_id} is a descendant of "
                f"{child_id} — would create a cycle in the hierarchy."
            )
        if cursor in seen:
            # Pre-existing cycle upstream — refuse rather than loop forever.
            raise ValueError(
                f"Hierarchy is already cyclic at {cursor}; refusing to extend it."
            )
        seen.add(cursor)
        cursor = (by_id.get(cursor) or {}).get("parent")
    return parent_id


def validate_batch_parallelism(tickets: list[dict]) -> None:
    """Enforce the file-overlap and intra-batch-dependency invariants."""
    file_owner: dict[str, str] = {}
    titles_in_batch = {(t.get("title") or "").strip() for t in tickets}

    for t in tickets:
        title = (t.get("title") or "<untitled>").strip()
        files = _normalize_array(t.get("files"))
        if not files:
            raise ValueError(
                f"Ticket {title!r} has no `files` field. Parallel-safe "
                "tickets must declare which files they touch so the batch "
                "can prove non-overlap. Pass `files: [\"path/a\", ...]`."
            )
        for raw in files:
            norm = raw.strip().rstrip("/")
            if not norm:
                continue
            if norm in file_owner and file_owner[norm] != title:
                raise ValueError(
                    f"File overlap in batch: {norm!r} is claimed by both "
                    f"{file_owner[norm]!r} and {title!r}. Parallel-safe "
                    "tickets must touch disjoint files. Either merge them "
                    "into one ticket or create one with `add` (serial)."
                )
            file_owner[norm] = title

        for dep in _normalize_array(t.get("depends")):
            if dep.strip() in titles_in_batch:
                raise ValueError(
                    f"Ticket {title!r} depends on sibling {dep!r} in the "
                    "same batch. Sibling-by-title dependency means serial "
                    "execution — create those tickets with `add`, not in "
                    "a batch. (External deps to already-existing IDs are fine.)"
                )

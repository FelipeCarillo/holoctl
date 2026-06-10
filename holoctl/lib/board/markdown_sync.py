"""Ticket ``.md`` synchronization: create / patch frontmatter, DoD counts.

Extracted from the former ``holoctl/lib/board.py`` god module (item 5.3).
The index (``index.json``) and the per-ticket markdown files must stay in
sync; these helpers own the markdown side. All functions are stateless and
take the relevant directories explicitly so they stay trivially testable.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..markdown import parse_frontmatter, serialize_frontmatter
from ..ticket import Ticket

# Acceptance-checkbox pattern: `- [ ]` / `- [x]` under any heading.
_CHECKBOX_RE = re.compile(r"^(\s*-\s*\[)([ xX])(\]\s*)(.*)$", re.MULTILINE)


def _count_acceptance(body: str | None) -> tuple[int, int]:
    """Return ``(total, done)`` DoD checkboxes in a ticket body."""
    if not body:
        return 0, 0
    total = 0
    done = 0
    for m in _CHECKBOX_RE.finditer(body):
        total += 1
        if m.group(2).lower() == "x":
            done += 1
    return total, done


def _yaml_format(val) -> str:
    """Format a Python value as a YAML scalar for ticket frontmatter."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else "null"
    return str(val)


def patch_ticket_md(board_dir: Path, file_path: str, patches: dict) -> None:
    """Apply frontmatter field patches to a ticket .md.

    Parses the frontmatter into a dict, mutates the requested fields, then
    re-serializes — rather than running a per-field ``re.sub`` (which
    silently no-ops when a field is absent and can clobber a body line that
    happens to start with ``key:``). Adding an absent field works (it's
    appended). The body is preserved byte-for-byte: ``parse_frontmatter``
    returns the body untouched and ``serialize_frontmatter`` re-emits it
    verbatim.
    """
    full_path = board_dir / file_path
    if not full_path.exists():
        return
    content = full_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)
    if not fm:
        # No parseable frontmatter — nothing to patch safely. Leave as-is.
        return
    # `serialize_frontmatter` re-inserts exactly one blank-line separator
    # between the frontmatter block and the body. `parse_frontmatter`
    # captures that separator as a leading newline on `body`, so we strip
    # leading newlines here to keep a patch idempotent — otherwise the body
    # would grow one blank line per mutation. (Mirrors memory.to_markdown.)
    body = body.lstrip("\n")
    for key, val in patches.items():
        # Store list-typed fields (agent/projects/files/depends/tags) in the
        # same comma-joined string shape `create_ticket_md` writes, so the
        # on-disk form stays consistent and `rebuild_index` reads it back.
        if isinstance(val, list):
            fm[key] = ", ".join(str(v) for v in val) if val else "null"
        elif val is None:
            fm[key] = "null"
        else:
            fm[key] = val
    full_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")


def resolve_body(tickets_dir: Path, body: str | None) -> str:
    """Resolve the body actually written for a new ticket.

    Mirrors ``create_ticket_md``'s fallback so callers (e.g. ``Board.add``)
    can compute denormalized acceptance counts from the same text that lands
    on disk. When ``body`` is None, falls back to ``_template.md`` (if
    present) or the built-in placeholder.
    """
    if body is not None:
        return body
    template_path = tickets_dir / "_template.md"
    if template_path.exists():
        _, tpl_body = parse_frontmatter(template_path.read_text(encoding="utf-8"))
        return tpl_body
    return (
        "\n# Start\n\n(Current state before starting)\n\n"
        "# Goal — Definition of Done\n\n- [ ] (criteria)\n\n"
        "# Context\n\n(Why this ticket exists)\n\n"
        "# Out of scope\n\n(What NOT to do)\n\n"
        "# Execution notes\n\n(Agent fills during work)\n"
    )


def create_ticket_md(
    board_dir: Path, tickets_dir: Path, ticket: Ticket, body: str | None = None
) -> None:
    md_path = board_dir / ticket["file"]
    md_path.parent.mkdir(parents=True, exist_ok=True)

    body = resolve_body(tickets_dir, body)

    agents_val = ticket["agent"]
    projects_val = ticket.get("projects") or []
    files_val = ticket.get("files") or []
    frontmatter = {
        "id": ticket["id"],
        "title": ticket["title"],
        "kind": ticket.get("kind") or "task",
        "parent": ticket.get("parent") or "null",
        "source_provider": ticket.get("source_provider") or "null",
        "source_ref": ticket.get("source_ref") or "null",
        "source_url": ticket.get("source_url") or "null",
        "source_label": ticket.get("source_label") or "null",
        "agent": ", ".join(agents_val) if agents_val else "null",
        "projects": ", ".join(projects_val) if projects_val else "null",
        "files": ", ".join(files_val) if files_val else "null",
        "status": ticket["status"],
        "priority": ticket["priority"],
        "sprint": ticket["sprint"],
        "created": ticket["created"],
        "updated": ticket["updated"],
        "completed": ticket["completed"],
        "depends": ", ".join(ticket["depends"]) if ticket["depends"] else "null",
        "tags": ", ".join(ticket["tags"]) if ticket["tags"] else "null",
    }

    md_path.write_text(serialize_frontmatter(frontmatter, body), encoding="utf-8")

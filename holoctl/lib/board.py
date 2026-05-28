from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .board_body import build_body
from .board_tree import render_tree
from .markdown import parse_frontmatter, serialize_frontmatter


def _now() -> str:
    """ISO 8601 UTC timestamp with `Z` suffix, e.g. `2026-05-06T13:42:18Z`.

    Used for `created`, `updated`, `completed`, and the activity log.
    Older tickets that still have date-only values (`2026-05-04`) are read
    transparently — `datetime.fromisoformat` accepts both forms in 3.11+.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Board:
    def __init__(self, project_root: Path, config: dict) -> None:
        self._root = project_root
        self._config = config
        self._board_dir = project_root / ".holoctl" / "board"
        self._index_path = self._board_dir / "index.json"
        self._tickets_dir = self._board_dir / "tickets"

    def _load(self) -> dict:
        if not self._index_path.exists():
            return {
                "meta": {"version": 1, "updated": _now(), "nextId": 1, "counts": {}},
                "tickets": [],
            }
        return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self._board_dir.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps(data, indent="\t") + "\n", encoding="utf-8"
        )

    def _recount(self, tickets: list[dict]) -> dict:
        counts: dict = {s: 0 for s in self._config["board"]["statuses"]}
        for t in tickets:
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        return counts

    def _generate_id(self, num: int) -> str:
        padding = self._config["board"]["idPadding"]
        return f"{self._config['project']['prefix']}-{str(num).zfill(padding)}"

    @staticmethod
    def _slugify(title: str) -> str:
        slug = re.sub(r"[^a-z0-9\s-]", "", title.lower())
        slug = re.sub(r"\s+", "-", slug)
        return slug[:40]

    def _patch_ticket_md(self, file_path: str, patches: dict) -> None:
        full_path = self._board_dir / file_path
        if not full_path.exists():
            return
        content = full_path.read_text(encoding="utf-8")
        for key, val in patches.items():
            str_val = _yaml_format(val)
            content = re.sub(
                rf"^({re.escape(key)}:\s*)(.*)$",
                lambda m, v=str_val: f"{m.group(1)}{v}",  # type: ignore[misc]
                content,
                flags=re.MULTILINE,
            )
        full_path.write_text(content, encoding="utf-8")

    def _valid_agents(self) -> set[str]:
        """Names of agents the agent file system has defined.

        Returns the stems of `.holoctl/agents/*.md`. Used for validating that
        a ticket's `agent:` value refers to a real persona.
        """
        agents_dir = self._root / ".holoctl" / "agents"
        if not agents_dir.exists():
            return set()
        return {f.stem for f in agents_dir.glob("*.md")}

    def _validate_status(self, status: str) -> None:
        valid = self._config["board"]["statuses"]
        if status not in valid:
            raise ValueError(f"Invalid status: {status!r}. Valid: {', '.join(valid)}")

    def _validate_priority(self, priority: str) -> None:
        valid = self._config["board"]["priorities"]
        if priority not in valid:
            raise ValueError(f"Invalid priority: {priority!r}. Valid: {', '.join(valid)}")

    def _validate_agents(self, agents: list[str]) -> None:
        if not agents:
            return
        defined = self._valid_agents()
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

    def _validate_parent_change(
        self, tickets: list[dict], child_id: str, new_parent: object
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
        by_id = {t["id"]: t for t in tickets}
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

    def stat(self) -> dict:
        data = self._load()
        return {**data["meta"]["counts"], "nextId": data["meta"]["nextId"]}

    def get(self, ticket_id: str) -> dict | None:
        data = self._load()
        return next((t for t in data["tickets"] if t["id"] == ticket_id), None)

    def ls(self, filters: dict | None = None) -> list[dict]:
        data = self._load()
        tickets = data["tickets"]
        f = filters or {}

        if f.get("sprint"):
            tickets = [t for t in tickets if t.get("sprint") == f["sprint"]]
        if f.get("status"):
            tickets = [t for t in tickets if t.get("status") == f["status"]]
        if f.get("agent"):
            tickets = [t for t in tickets if f["agent"] in (t.get("agent") or [])]
        if f.get("tag"):
            tickets = [t for t in tickets if f["tag"] in (t.get("tags") or [])]
        if f.get("priority"):
            tickets = [t for t in tickets if t.get("priority") == f["priority"]]
        if f.get("project"):
            tickets = [t for t in tickets if f["project"] in (t.get("projects") or [])]
        if f.get("kind"):
            tickets = [t for t in tickets if (t.get("kind") or "task") == f["kind"]]
        if f.get("parent"):
            tickets = [t for t in tickets if t.get("parent") == f["parent"]]

        return tickets

    def tree(
        self,
        filters: dict | None = None,
        root: str | None = None,
    ) -> list[dict]:
        """Return tickets as a flat list pre-annotated for tree rendering.

        Each row is ``{"ticket": <ticket dict>, "depth": int, "prefix": str}``.
        ``prefix`` is the pre-baked ASCII glyph string the CLI prints before
        the ticket id (e.g. ``"│  └─ "``); empty for roots.

        ``filters`` accepts the same keys as :meth:`ls`. When filters drop a
        descendant whose parent is kept, the parent still shows so the
        hierarchy reads correctly. Conversely, an ancestor that doesn't match
        is *kept* if at least one of its descendants matches — pruning a tree
        from the middle would lie about the structure.

        ``root`` restricts the result to the subtree rooted at that id.
        """
        data = self._load()
        all_tickets: list[dict] = data["tickets"]
        if filters:
            matched_ids = {t["id"] for t in self.ls(filters)}
        else:
            matched_ids = {t["id"] for t in all_tickets}
        return render_tree(all_tickets, matched_ids, root)

    def children(self, parent_id: str) -> dict:
        """Return direct children of a work item plus aggregate progress.

        Used to inspect a spec/story/epic and see how its child tasks are
        doing. Computes:
          - children: list of direct descendants (one level)
          - total_acceptance: total DoD checkboxes across all children
          - acked: total `[x]` checkboxes across all children
          - by_status: counts of children per status
        """
        data = self._load()
        parent = next((t for t in data["tickets"] if t["id"] == parent_id), None)
        if not parent:
            raise KeyError(f"Ticket {parent_id} not found")
        children = [t for t in data["tickets"] if t.get("parent") == parent_id]
        # Aggregate DoD progress by reading each child's body.
        total = 0
        acked = 0
        for c in children:
            if not c.get("file"):
                continue
            md_path = self._board_dir / c["file"]
            if not md_path.exists():
                continue
            content = md_path.read_text(encoding="utf-8")
            _, body = parse_frontmatter(content)
            for m in re.finditer(r"^(\s*-\s*\[)([ xX])(\]\s*)(.*)$", body, re.MULTILINE):
                total += 1
                if m.group(2).lower() == "x":
                    acked += 1
        by_status: dict[str, int] = {}
        for c in children:
            s = c.get("status", "?")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "parent": parent,
            "children": children,
            "total_acceptance": total,
            "acked": acked,
            "by_status": by_status,
        }

    def _apply_status_change(
        self,
        ticket: dict,
        old_status: str,
        new_status: str,
        now: str,
    ) -> dict:
        """Apply a status transition on a ticket dict in-place.

        Sets ``status``, ``updated``, and ``completed`` (set when entering
        ``done``, cleared when leaving ``done``).  Also appends a
        ``"ticket.moved"`` event to ``activity.jsonl`` — but only when the
        status actually changes (no-op moves are skipped).

        Returns a patches dict suitable for ``_patch_ticket_md``.
        """
        ticket["status"] = new_status
        ticket["updated"] = now

        patches: dict = {"status": new_status, "updated": now}

        if new_status == "done":
            ticket["completed"] = now
            patches["completed"] = now
        elif old_status == "done":
            # Leaving done — clear the stale completion timestamp.
            ticket["completed"] = None
            patches["completed"] = None

        _log_activity(
            self._root,
            {
                "type": "ticket.moved",
                "ticket": ticket["id"],
                "from": old_status,
                "to": new_status,
                "actor": "cli",
            },
        )

        return patches

    def move(self, ticket_id: str, new_status: str) -> dict:
        valid = self._config["board"]["statuses"]
        if new_status not in valid:
            raise ValueError(f"Invalid status: {new_status}. Valid: {'|'.join(valid)}")

        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")

        old_status = ticket["status"]
        now = _now()

        if old_status != new_status:
            patches = self._apply_status_change(ticket, old_status, new_status, now)
        else:
            # No-op move: still update the timestamp, but don't log.
            ticket["updated"] = now
            patches = {"updated": now}

        data["meta"]["counts"] = self._recount(data["tickets"])
        data["meta"]["updated"] = now
        self._save(data)

        if ticket.get("file"):
            self._patch_ticket_md(ticket["file"], patches)

        # Curator auto-execute (item 8A): when a meta:curate ticket transitions
        # to `done`, the curator action stored in the parallel metadata file
        # is applied. Reversible (e.g. `hctl agent remove` undoes agent_add).
        # Soft-import so curator is not a hard dependency of the board.
        result = {"id": ticket_id, "from": old_status, "to": new_status}
        if (
            new_status == "done"
            and old_status != new_status
            and "meta:curate" in (ticket.get("tags") or [])
        ):
            try:
                from .curator import apply_curator_action
                applied = apply_curator_action(self._root, ticket)
                if applied is not None:
                    result["curator_applied"] = applied
            except Exception as exc:
                result["curator_error"] = str(exc)

        return result

    _EDITABLE_FIELDS = {
        "title", "agent", "projects", "status", "priority",
        "sprint", "depends", "tags", "completed",
        "kind", "parent",
        "source_provider", "source_ref", "source_url", "source_label",
    }

    def set(self, ticket_id: str, field: str, value: str) -> dict:
        if field not in self._EDITABLE_FIELDS:
            allowed = ", ".join(sorted(self._EDITABLE_FIELDS))
            raise ValueError(f"Field '{field}' is not editable. Allowed: {allowed}")

        if field == "status":
            self._validate_status(value)
        elif field == "priority":
            self._validate_priority(value)

        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")

        parsed = _parse_set_value(value)
        if field in ("agent", "depends", "tags", "projects"):
            parsed = _normalize_array(parsed if isinstance(parsed, (list, str)) else value)
            if field == "agent":
                self._validate_agents(parsed)
        elif field == "parent":
            # Empty string / null → orphan the item (allowed). Otherwise
            # the target must exist AND not be a descendant of this ticket,
            # else we'd close a cycle in the hierarchy.
            parsed = self._validate_parent_change(data["tickets"], ticket_id, parsed)

        now = _now()

        if field == "status":
            old_status = ticket["status"]
            new_status = str(parsed)
            if old_status != new_status:
                md_patches = self._apply_status_change(ticket, old_status, new_status, now)
            else:
                # No-op status set: update timestamp only, no logging.
                ticket["updated"] = now
                md_patches = {"status": new_status, "updated": now}
            data["meta"]["counts"] = self._recount(data["tickets"])
        else:
            ticket[field] = parsed
            ticket["updated"] = now
            md_patches = {field: parsed, "updated": now}

        data["meta"]["updated"] = now
        self._save(data)

        if ticket.get("file"):
            self._patch_ticket_md(ticket["file"], md_patches)

        return {"id": ticket_id, "field": field, "value": parsed}

    def add(self, patch: dict) -> dict:
        title = (patch.get("title") or "").strip()
        if not title:
            raise ValueError(
                "Ticket title is required. Pass `title` in the JSON, e.g. "
                '`holoctl board add \'{"title":"Add auth flow","agent":"developer"}\'`.'
            )

        # Defaults are the first valid value from config; reject anything else.
        # The agent must pass valid status / priority / agent names — no silent
        # coercion, so malformed tickets fail loud and the agent retries.
        statuses = self._config["board"]["statuses"]
        status = patch.get("status", statuses[0])
        priority = patch.get("priority") or "p2"
        self._validate_status(status)
        self._validate_priority(priority)

        agents = patch.get("agent", [])
        if isinstance(agents, str):
            agents = [agents]
        self._validate_agents(agents)

        tags = patch.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        depends = patch.get("depends", [])
        if isinstance(depends, str):
            depends = [d.strip() for d in depends.split(",") if d.strip()]

        # Accept new `projects` (array) or legacy `scope` (string).
        projects = patch.get("projects")
        if projects is None and patch.get("scope"):
            projects = [patch["scope"]]
        projects = _normalize_array(projects)

        # Files this ticket touches. Used by `batch_add` to detect overlap
        # between siblings; also useful for the developer agent to confirm
        # `Start` matches reality. Optional on regular `add`.
        files = _normalize_array(patch.get("files"))

        data = self._load()
        next_num = data["meta"]["nextId"]
        ticket_id = self._generate_id(next_num)
        slug = self._slugify(title)
        now = _now()

        kind = patch.get("kind") or "task"
        parent = patch.get("parent")
        if parent is not None and not isinstance(parent, str):
            parent = str(parent)
        if parent:
            # Existence check: a new ticket can't reference a parent that
            # isn't on the board yet. (Cycle isn't possible — this row's
            # ID doesn't exist yet, so no descendant can point back.)
            if not any(t["id"] == parent for t in data["tickets"]):
                raise KeyError(
                    f"Parent ticket {parent} not found. "
                    "Create the parent first, or omit `parent`."
                )
        elif parent == "":
            parent = None

        # External source linkage — when the work item came from a board
        # outside holoctl (Trello card, Linear issue, Azure DevOps PBI,
        # GitHub Issue, Slack thread, …) we store the reference so the
        # round-trip is traceable. All optional; children inherit from parent
        # when not explicitly set (handled in batch_add).
        source_provider = patch.get("source_provider")
        source_ref = patch.get("source_ref")
        source_url = patch.get("source_url")
        source_label = patch.get("source_label")

        ticket: dict = {
            "id": ticket_id,
            "title": title,
            "kind": kind,
            "parent": parent,
            "source_provider": source_provider,
            "source_ref": source_ref,
            "source_url": source_url,
            "source_label": source_label,
            "agent": agents,
            "projects": projects,
            "files": files,
            "status": status,
            "priority": priority,
            "sprint": patch.get("sprint"),
            "created": now,
            "updated": now,
            "completed": None,
            "depends": depends,
            "tags": tags,
            "file": f"tickets/{ticket_id}-{slug}.md",
        }

        data["tickets"].append(ticket)
        data["meta"]["nextId"] = next_num + 1
        data["meta"]["counts"] = self._recount(data["tickets"])
        data["meta"]["updated"] = now
        self._save(data)

        body = build_body(patch)
        self._create_ticket_md(ticket, body=body)
        _log_activity(self._root, {"type": "ticket.created", "ticket": ticket_id, "actor": "cli"})

        return ticket

    def delete(self, ticket_id: str) -> dict:
        """Hard-delete a ticket: removes the .md file AND the index entry.

        Different from `move <ID> cancelled`, which is soft-delete (keeps the
        record). Use `delete` only when the ticket was created by mistake or
        is truly stale. The id is **not** reused — `nextId` keeps incrementing.
        """
        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")

        # Remove the .md file if it exists.
        if ticket.get("file"):
            md_path = self._board_dir / ticket["file"]
            if md_path.exists():
                md_path.unlink()

        # Drop from index, recount.
        data["tickets"] = [t for t in data["tickets"] if t["id"] != ticket_id]
        data["meta"]["counts"] = self._recount(data["tickets"])
        data["meta"]["updated"] = _now()
        self._save(data)

        _log_activity(self._root, {"type": "ticket.deleted", "ticket": ticket_id, "actor": "cli"})
        return {"id": ticket_id, "deleted": True}

    def batch_move(self, ticket_ids: list[str], new_status: str) -> dict:
        """Move N tickets to the same status in one call. Atomic per-ticket; reports per-id success/failure."""
        results = []
        errors = []
        for tid in ticket_ids:
            try:
                results.append(self.move(tid, new_status))
            except (KeyError, ValueError) as e:
                errors.append({"id": tid, "error": str(e)})
        return {"moved": results, "errors": errors, "count": len(results)}

    def batch_set(self, ticket_ids: list[str], field: str, value: str) -> dict:
        """Set the same field=value on N tickets. Atomic per-ticket; reports per-id success/failure."""
        results = []
        errors = []
        for tid in ticket_ids:
            try:
                results.append(self.set(tid, field, value))
            except (KeyError, ValueError) as e:
                errors.append({"id": tid, "error": str(e)})
        return {"updated": results, "errors": errors, "count": len(results)}

    def batch_delete(self, ticket_ids: list[str]) -> dict:
        """Hard-delete N tickets. Atomic per-ticket; reports per-id success/failure."""
        results = []
        errors = []
        for tid in ticket_ids:
            try:
                results.append(self.delete(tid))
            except (KeyError, ValueError) as e:
                errors.append({"id": tid, "error": str(e)})
        return {"deleted": results, "errors": errors, "count": len(results)}

    def show(self, ticket_id: str) -> dict:
        """Return frontmatter + body of a ticket as a single record.

        Replaces the anti-pattern of agents reading
        `.holoctl/board/tickets/<ID>-*.md` directly. Single source of truth
        for ticket inspection — used by `/board <ID>` and `mcp__holoctl__board_show`.
        """
        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")
        if not ticket.get("file"):
            raise ValueError(f"Ticket {ticket_id} has no file path")
        full_path = self._board_dir / ticket["file"]
        if not full_path.exists():
            raise FileNotFoundError(f"Ticket file missing: {full_path}")
        content = full_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        return {
            "id": ticket_id,
            "frontmatter": fm,
            "body": body,
            "raw": content,
        }

    def ack(self, ticket_id: str, idx: int) -> dict:
        """Toggle DoD checkbox at zero-indexed position `idx` from [ ] to [x].

        Operates on lines in the body that match the checkbox pattern (`- [ ]`
        or `- [x]`) under any heading. Index is zero-based across all
        checkboxes in the file in document order.
        """
        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")
        if not ticket.get("file"):
            raise ValueError(f"Ticket {ticket_id} has no file path")
        full_path = self._board_dir / ticket["file"]
        if not full_path.exists():
            raise FileNotFoundError(f"Ticket file missing: {full_path}")

        content = full_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)

        checkbox_re = re.compile(r"^(\s*-\s*\[)([ xX])(\]\s*)(.*)$", re.MULTILINE)
        matches = list(checkbox_re.finditer(body))
        if not matches:
            raise ValueError(f"Ticket {ticket_id} has no DoD checkboxes")
        if idx < 0 or idx >= len(matches):
            raise ValueError(
                f"DoD index {idx} out of range; ticket has {len(matches)} checkbox(es)"
            )

        m = matches[idx]
        was_checked = m.group(2).lower() == "x"
        new_state = " " if was_checked else "x"
        new_body = body[:m.start()] + m.group(1) + new_state + m.group(3) + m.group(4) + body[m.end():]

        now = _now()
        fm["updated"] = now
        full_path.write_text(serialize_frontmatter(fm, new_body), encoding="utf-8")

        ticket["updated"] = now
        data["meta"]["updated"] = now
        self._save(data)

        _log_activity(self._root, {"type": "ticket.ack", "ticket": ticket_id, "idx": idx, "checked": not was_checked, "actor": "cli"})
        return {"id": ticket_id, "idx": idx, "checked": not was_checked, "text": m.group(4).strip()}

    def note(self, ticket_id: str, text: str) -> dict:
        """Append a timestamped note line to the ticket's # Notes section.

        Creates the section if absent. Notes are append-only: this command
        never rewrites existing notes, only adds a new line at the end.
        """
        if not text or not text.strip():
            raise ValueError("Note text is empty.")
        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")
        if not ticket.get("file"):
            raise ValueError(f"Ticket {ticket_id} has no file path")
        full_path = self._board_dir / ticket["file"]
        if not full_path.exists():
            raise FileNotFoundError(f"Ticket file missing: {full_path}")

        content = full_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        now = _now()
        clean = text.strip().replace("\n", " ")
        new_entry = f"- **{now}** — {clean}"

        if re.search(r"^#\s+Notes\s*$", body, re.MULTILINE):
            new_body = re.sub(
                r"(^#\s+Notes\s*$\n)((?:.*\n?)*)",
                lambda m: m.group(1) + (m.group(2).rstrip("\n") + "\n" if m.group(2).strip() else "") + new_entry + "\n",
                body,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            new_body = body.rstrip("\n") + f"\n\n# Notes\n\n{new_entry}\n"

        fm["updated"] = now
        full_path.write_text(serialize_frontmatter(fm, new_body), encoding="utf-8")

        ticket["updated"] = now
        data["meta"]["updated"] = now
        self._save(data)

        _log_activity(self._root, {"type": "ticket.note", "ticket": ticket_id, "actor": "cli"})
        return {"id": ticket_id, "note": clean, "ts": now}

    def set_body(self, ticket_id: str, body: str) -> dict:
        """Replace the body of a ticket .md, preserving frontmatter."""
        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")

        if not ticket.get("file"):
            raise ValueError(f"Ticket {ticket_id} has no file path; cannot edit body")

        full_path = self._board_dir / ticket["file"]
        if not full_path.exists():
            raise FileNotFoundError(f"Ticket file missing: {full_path}")

        existing = full_path.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(existing)
        now = _now()
        fm["updated"] = now
        full_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")

        ticket["updated"] = now
        data["meta"]["updated"] = now
        self._save(data)
        _log_activity(self._root, {"type": "ticket.body_updated", "ticket": ticket_id, "actor": "cli"})

        return {"id": ticket_id, "bytes": len(body)}

    def next_id(self) -> str:
        data = self._load()
        return self._generate_id(data["meta"]["nextId"])

    def batch_add(self, shared: dict, tickets: list[dict]) -> dict:
        """Create N tickets in one call after validating parallelism invariants.

        `shared` fields (e.g. `tags`, `sprint`, `projects`) are merged into
        each ticket; per-ticket fields override shared ones. The whole batch
        is validated UP-FRONT — if any check fails, no ticket is created.

        Parallelism invariants enforced:
        1. Each ticket must declare `files: list[str]`. Without it the batch
           cannot prove non-overlap.
        2. No two tickets in the batch may declare the same file path.
        3. No ticket in the batch may have a sibling-by-title in its
           `depends`. (Inter-batch deps mean serial execution; create those
           with regular `add` instead.)
        4. Standard `add` validation (title, status, priority, agent) is
           applied to each ticket. First failure aborts the whole batch.

        On success, returns `{"count": N, "tickets": [...]}`.
        """
        if not tickets:
            raise ValueError("Batch is empty. Pass at least one ticket.")
        if not isinstance(tickets, list):
            raise ValueError("`tickets` must be a JSON array.")

        merged: list[dict] = []
        for i, t in enumerate(tickets):
            if not isinstance(t, dict):
                raise ValueError(f"tickets[{i}] is not an object.")
            m = {**(shared or {})}
            # Per-ticket fields win over shared.
            m.update(t)
            # Merge array fields (tags / projects / depends / files / agent)
            # additively — shared defaults + per-ticket extras.
            for key in ("tags", "projects", "depends", "files", "agent"):
                shared_val = _normalize_array((shared or {}).get(key))
                ticket_val = _normalize_array(t.get(key))
                merged_arr = list(dict.fromkeys(shared_val + ticket_val))  # dedupe, keep order
                if merged_arr:
                    m[key] = merged_arr
            # Scalar inherits: parent, kind, source_* propagate from shared
            # to each child UNLESS the child overrides. This is the mechanic
            # that makes "boardmaster decomposes a spec into N tasks" — the
            # shared.parent = SPEC_ID + shared.source_* = spec's origin
            # gets inherited by all children for free.
            for key in (
                "parent", "kind",
                "source_provider", "source_ref", "source_url", "source_label",
            ):
                if key not in t and (shared or {}).get(key) is not None:
                    m[key] = (shared or {})[key]
            merged.append(m)

        self._validate_batch_parallelism(merged)

        # Pre-flight: validate every ticket through the same rules `add` uses,
        # without creating anything yet.
        statuses = self._config["board"]["statuses"]
        for i, m in enumerate(merged):
            if not (m.get("title") or "").strip():
                raise ValueError(f"tickets[{i}]: title is required.")
            self._validate_status(m.get("status", statuses[0]))
            self._validate_priority(m.get("priority") or "p2")
            agents = m.get("agent") or []
            if isinstance(agents, str):
                agents = [agents]
            self._validate_agents(agents)

        # All clear — create.
        created = [self.add(m) for m in merged]
        return {"count": len(created), "tickets": created}

    def _validate_batch_parallelism(self, tickets: list[dict]) -> None:
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

    def rebuild_index(self) -> dict:
        self._tickets_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self._tickets_dir.glob("*.md"))
        tickets = []
        now = _now()

        for f in files:
            if f.name.startswith("_"):
                continue
            data_fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
            if not data_fm.get("id"):
                continue
            # Migration: legacy `scope: "X"` → `projects: ["X"]`.
            projects_fm = data_fm.get("projects")
            if projects_fm is None and data_fm.get("scope"):
                projects_fm = data_fm["scope"]

            def _scalar(v):
                return v if v not in (None, "null", "") else None
            tickets.append({
                "id": data_fm["id"],
                "title": data_fm.get("title", ""),
                "kind": data_fm.get("kind") or "task",
                "parent": _scalar(data_fm.get("parent")),
                "source_provider": _scalar(data_fm.get("source_provider")),
                "source_ref": _scalar(data_fm.get("source_ref")),
                "source_url": _scalar(data_fm.get("source_url")),
                "source_label": _scalar(data_fm.get("source_label")),
                "agent": _normalize_array(data_fm.get("agent")),
                "files": _normalize_array(data_fm.get("files")),
                "projects": _normalize_array(projects_fm),
                "status": data_fm.get("status", "backlog"),
                "priority": data_fm.get("priority", "p2"),
                "sprint": data_fm.get("sprint"),
                "created": data_fm.get("created", now),
                "updated": data_fm.get("updated", now),
                "completed": data_fm.get("completed"),
                "depends": _normalize_array(data_fm.get("depends")),
                "tags": _normalize_array(data_fm.get("tags")),
                "file": f"tickets/{f.name}",
            })

        tickets.sort(key=lambda t: int(t["id"].split("-")[-1]))
        max_num = max((int(t["id"].split("-")[-1]) for t in tickets), default=0)

        index = {
            "meta": {
                "version": 1,
                "updated": now,
                "nextId": max_num + 1,
                "counts": self._recount(tickets),
            },
            "tickets": tickets,
        }
        self._save(index)
        return {"ticketCount": len(tickets), "nextId": max_num + 1}

    def _create_ticket_md(self, ticket: dict, body: str | None = None) -> None:
        md_path = self._board_dir / ticket["file"]
        md_path.parent.mkdir(parents=True, exist_ok=True)

        if body is None:
            template_path = self._tickets_dir / "_template.md"
            if template_path.exists():
                _, body = parse_frontmatter(template_path.read_text(encoding="utf-8"))
            else:
                body = (
                    "\n# Start\n\n(Current state before starting)\n\n"
                    "# Goal — Definition of Done\n\n- [ ] (criteria)\n\n"
                    "# Context\n\n(Why this ticket exists)\n\n"
                    "# Out of scope\n\n(What NOT to do)\n\n"
                    "# Execution notes\n\n(Agent fills during work)\n"
                )

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


def _normalize_array(val) -> list:
    if not val or val == "null":
        return []
    if isinstance(val, list):
        return val
    return [s.strip() for s in str(val).split(",") if s.strip()]


def _yaml_format(val) -> str:
    """Format a Python value as a YAML scalar for ticket frontmatter."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else "null"
    return str(val)


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


def _log_activity(project_root: Path, event: dict) -> None:
    """Append a board mutation to ``.holoctl/activity.jsonl``.

    This is a *separate* store from the event journal (``.holoctl/journal/``):
    it has a ticket-scoped schema (``{ts, type, ticket, ...}``) and feeds the
    dashboard's per-ticket activity timeline, whereas the journal has a
    session-event schema and feeds the curator. They share the same locked
    append primitive so neither interleaves a half-written line under
    concurrent writers.
    """
    from .jsonl import append_jsonl_line
    log_path = project_root / ".holoctl" / "activity.jsonl"
    entry = {"ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), **event}
    append_jsonl_line(log_path, json.dumps(entry) + "\n")

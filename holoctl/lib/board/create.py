"""Ticket creation: ``add`` and the parallel-safe ``batch_add``.

Extracted from the former ``holoctl/lib/board.py`` god module (item 5.3).
``BoardCreateOps`` is a mixin over :class:`.store.BoardIndexStore`; the
public :class:`holoctl.lib.board.Board` facade composes it.
"""
from __future__ import annotations

import re

from ..board_body import build_body
from ..ticket import TICKET_LIST_FIELDS, TICKET_SOURCE_FIELDS, Ticket
from .markdown_sync import _count_acceptance, create_ticket_md, resolve_body
from .store import BoardIndexStore, _log_activity, _now
from .validate import (
    _normalize_array,
    validate_agents,
    validate_batch_parallelism,
    validate_priority,
    validate_status,
)


class BoardCreateOps(BoardIndexStore):
    """Mixin owning ticket creation (single + batch)."""

    def _generate_id(self, num: int) -> str:
        padding = self._config["board"]["idPadding"]
        return f"{self._config['project']['prefix']}-{str(num).zfill(padding)}"

    @staticmethod
    def _slugify(title: str) -> str:
        slug = re.sub(r"[^a-z0-9\s-]", "", title.lower())
        slug = re.sub(r"\s+", "-", slug)
        return slug[:40]

    def add(self, patch: dict) -> Ticket:
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
        validate_status(status, statuses)
        validate_priority(priority, self._config["board"]["priorities"])

        agents = patch.get("agent", [])
        if isinstance(agents, str):
            agents = [agents]
        validate_agents(agents, self._root)

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

        body = build_body(patch)
        # Count DoD checkboxes against the body that will actually be written
        # (build_body may return None → template/placeholder fallback), so the
        # denormalized counts match the .md.
        acc_total, acc_done = _count_acceptance(resolve_body(self._tickets_dir, body))

        with self._locked():
            data = self._load_mut()
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
            # round-trip is traceable. All optional; children inherit from
            # parent when not explicitly set (handled in batch_add).
            source_provider = patch.get("source_provider")
            source_ref = patch.get("source_ref")
            source_url = patch.get("source_url")
            source_label = patch.get("source_label")

            ticket: Ticket = {
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
                # Denormalized DoD progress so `children()`/detail views don't
                # have to re-read every child .md (see task 4.3).
                "acceptance_total": acc_total,
                "acceptance_done": acc_done,
                "file": f"tickets/{ticket_id}-{slug}.md",
            }

            data["tickets"].append(ticket)
            data["meta"]["nextId"] = next_num + 1
            data["meta"]["counts"] = self._recount(data["tickets"])
            data["meta"]["updated"] = now
            self._save(data)

            create_ticket_md(self._board_dir, self._tickets_dir, ticket, body=body)

        _log_activity(self._root, {"type": "ticket.created", "ticket": ticket_id, "actor": "cli"})

        return ticket

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
            # Merge array fields (agent / projects / files / depends / tags)
            # additively — shared defaults + per-ticket extras.
            for key in TICKET_LIST_FIELDS:
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
            for key in ("parent", "kind", *TICKET_SOURCE_FIELDS):
                if key not in t and (shared or {}).get(key) is not None:
                    m[key] = (shared or {})[key]
            merged.append(m)

        validate_batch_parallelism(merged)

        # Pre-flight: validate every ticket through the same rules `add` uses,
        # without creating anything yet.
        statuses = self._config["board"]["statuses"]
        for i, m in enumerate(merged):
            if not (m.get("title") or "").strip():
                raise ValueError(f"tickets[{i}]: title is required.")
            validate_status(m.get("status", statuses[0]), statuses)
            validate_priority(m.get("priority") or "p2", self._config["board"]["priorities"])
            agents = m.get("agent") or []
            if isinstance(agents, str):
                agents = [agents]
            validate_agents(agents, self._root)

        # All clear — create.
        created: list[Ticket] = [self.add(m) for m in merged]
        return {"count": len(created), "tickets": created}

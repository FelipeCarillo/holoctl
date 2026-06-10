"""Ticket mutations: status moves, field sets, deletes, DoD/notes/body edits.

Extracted from the former ``holoctl/lib/board.py`` god module (item 5.3).
``BoardTicketOps`` is a mixin over :class:`.store.BoardIndexStore`; the
public :class:`holoctl.lib.board.Board` facade composes it.

The curator done-hook coupling lives here: ``move`` calls the injectable
``self._on_meta_curate_done`` callback (constructor arg on ``Board``), whose
default — :func:`_default_meta_curate_done` — preserves the original lazy
soft-import of ``holoctl.lib.curator.apply_curator_action``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, cast

from ..markdown import parse_frontmatter, serialize_frontmatter
from ..ticket import Ticket
from .markdown_sync import _CHECKBOX_RE, _count_acceptance, patch_ticket_md
from .store import BoardIndexStore, _log_activity, _now
from .validate import (
    _normalize_array,
    _parse_set_value,
    validate_agents,
    validate_parent_change,
    validate_priority,
    validate_status,
)


def _default_meta_curate_done(project_root: Path, ticket: Ticket) -> dict | None:
    """Default curator done-hook: apply the stored curator action.

    Soft-import so curator is not a hard dependency of the board. Kept lazy
    inside the function — exactly the original ``Board.move`` behavior.
    """
    from ..curator import apply_curator_action
    # cast: apply_curator_action takes a plain dict; a Ticket IS one
    # at runtime (TypedDict), the cast only bridges the annotation.
    return apply_curator_action(project_root, cast(dict, ticket))


class BoardTicketOps(BoardIndexStore):
    """Mixin owning mutations of existing tickets (index + .md kept in sync)."""

    # Curator done-hook; Board.__init__ assigns it (injectable, defaults to
    # `_default_meta_curate_done`).
    _on_meta_curate_done: Callable[[Path, Ticket], dict | None]

    _EDITABLE_FIELDS = {
        "title", "agent", "projects", "status", "priority",
        "sprint", "depends", "tags", "completed",
        "kind", "parent",
        "source_provider", "source_ref", "source_url", "source_label",
    }

    def _apply_status_change(
        self,
        ticket: Ticket,
        old_status: str,
        new_status: str,
        now: str,
    ) -> dict:
        """Apply a status transition on a ticket dict in-place.

        Sets ``status``, ``updated``, and ``completed`` (set when entering
        ``done``, cleared when leaving ``done``).

        The ``"ticket.moved"`` activity log entry is intentionally NOT emitted
        here — callers (``move`` and ``set``) emit it AFTER ``_save`` and
        ``patch_ticket_md`` have both completed, so the log never records a
        transition that failed to persist (no partial-write window).

        Returns a patches dict suitable for ``patch_ticket_md``.
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

        return patches

    def move(self, ticket_id: str, new_status: str) -> dict:
        # NOTE: returns a result envelope (id/from/to[/curator_*]), not a Ticket.
        valid = self._config["board"]["statuses"]
        if new_status not in valid:
            raise ValueError(f"Invalid status: {new_status}. Valid: {'|'.join(valid)}")

        # Hold the board lock across load→mutate→save so a concurrent CLI +
        # MCP-server writer can't clobber this mutation (last-write-wins).
        with self._locked():
            data = self._load_mut()
            ticket: Ticket | None = next(
                (t for t in data["tickets"] if t["id"] == ticket_id), None
            )
            if not ticket:
                raise KeyError(f"Ticket {ticket_id} not found")

            old_status = ticket["status"]
            now = _now()

            if old_status != new_status:
                patches = self._apply_status_change(ticket, old_status, new_status, now)
            else:
                # No-op move: touch `updated` so the mutation is acknowledged
                # even when status is unchanged, but don't log a ticket.moved.
                ticket["updated"] = now
                patches = {"updated": now}

            data["meta"]["counts"] = self._recount(data["tickets"])
            data["meta"]["updated"] = now
            self._save(data)

            if ticket.get("file"):
                patch_ticket_md(self._board_dir, ticket["file"], patches)

        # Log status change AFTER both _save and patch_ticket_md have
        # completed — this prevents a phantom activity entry in the rare case
        # the process dies between persist and log.
        if old_status != new_status:
            _log_activity(
                self._root,
                {
                    "type": "ticket.moved",
                    "ticket": ticket_id,
                    "from": old_status,
                    "to": new_status,
                    "actor": "cli",
                },
            )

        # Curator auto-execute (item 8A): when a meta:curate ticket transitions
        # to `done`, the curator action stored in the parallel metadata file
        # is applied. Reversible (e.g. `hctl agent remove` undoes agent_add).
        # The hook is injectable (Board constructor arg `on_meta_curate_done`);
        # the default preserves the original soft-import of the curator.
        result: dict = {"id": ticket_id, "from": old_status, "to": new_status}
        if (
            new_status == "done"
            and old_status != new_status
            and "meta:curate" in (ticket.get("tags") or [])
        ):
            try:
                applied = self._on_meta_curate_done(self._root, ticket)
                if applied is not None:
                    result["curator_applied"] = applied
            except Exception as exc:
                result["curator_error"] = str(exc)

        return result

    def set(self, ticket_id: str, field: str, value: str) -> dict:
        if field not in self._EDITABLE_FIELDS:
            allowed = ", ".join(sorted(self._EDITABLE_FIELDS))
            raise ValueError(f"Field '{field}' is not editable. Allowed: {allowed}")

        if field == "status":
            validate_status(value, self._config["board"]["statuses"])
        elif field == "priority":
            validate_priority(value, self._config["board"]["priorities"])

        with self._locked():
            data = self._load_mut()
            ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
            if not ticket:
                raise KeyError(f"Ticket {ticket_id} not found")

            parsed = _parse_set_value(value)
            if field in ("agent", "depends", "tags", "projects"):
                parsed = _normalize_array(parsed if isinstance(parsed, (list, str)) else value)
                if field == "agent":
                    validate_agents(parsed, self._root)
            elif field == "parent":
                # Empty string / null → orphan the item (allowed). Otherwise
                # the target must exist AND not be a descendant of this ticket,
                # else we'd close a cycle in the hierarchy.
                parsed = validate_parent_change(data["tickets"], ticket_id, parsed)

            now = _now()

            if field == "status":
                old_status = ticket["status"]
                new_status = str(parsed)
                if old_status != new_status:
                    md_patches = self._apply_status_change(ticket, old_status, new_status, now)
                else:
                    # No-op status set: touch `updated` so the mutation is
                    # acknowledged even when status is unchanged, but don't log.
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
                patch_ticket_md(self._board_dir, ticket["file"], md_patches)

        # Log status change AFTER both _save and patch_ticket_md have
        # completed — mirrors the ordering in move() (no partial-write window).
        if field == "status" and old_status != new_status:  # type: ignore[possibly-undefined]
            _log_activity(
                self._root,
                {
                    "type": "ticket.moved",
                    "ticket": ticket_id,
                    "from": old_status,
                    "to": new_status,
                    "actor": "cli",
                },
            )

        return {"id": ticket_id, "field": field, "value": parsed}

    def delete(self, ticket_id: str) -> dict:
        """Hard-delete a ticket: removes the .md file AND the index entry.

        Different from `move <ID> cancelled`, which is soft-delete (keeps the
        record). Use `delete` only when the ticket was created by mistake or
        is truly stale. The id is **not** reused — `nextId` keeps incrementing.
        """
        with self._locked():
            data = self._load_mut()
            ticket: Ticket | None = next(
                (t for t in data["tickets"] if t["id"] == ticket_id), None
            )
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

    def ack(self, ticket_id: str, idx: int) -> dict:
        """Toggle DoD checkbox at zero-indexed position `idx` from [ ] to [x].

        Operates on lines in the body that match the checkbox pattern (`- [ ]`
        or `- [x]`) under any heading. Index is zero-based across all
        checkboxes in the file in document order.
        """
        with self._locked():
            data = self._load_mut()
            ticket: Ticket | None = next(
                (t for t in data["tickets"] if t["id"] == ticket_id), None
            )
            if not ticket:
                raise KeyError(f"Ticket {ticket_id} not found")
            if not ticket.get("file"):
                raise ValueError(f"Ticket {ticket_id} has no file path")
            full_path = self._board_dir / ticket["file"]
            if not full_path.exists():
                raise FileNotFoundError(f"Ticket file missing: {full_path}")

            content = full_path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(content)

            matches = list(_CHECKBOX_RE.finditer(body))
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

            # Refresh denormalized DoD counts in the index from the new body.
            acc_total, acc_done = _count_acceptance(new_body)
            ticket["acceptance_total"] = acc_total
            ticket["acceptance_done"] = acc_done
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
        with self._locked():
            data = self._load_mut()
            ticket: Ticket | None = next(
                (t for t in data["tickets"] if t["id"] == ticket_id), None
            )
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
        with self._locked():
            data = self._load_mut()
            ticket: Ticket | None = next(
                (t for t in data["tickets"] if t["id"] == ticket_id), None
            )
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

            # Replacing the body can change the DoD checkbox set — refresh the
            # denormalized counts in the index.
            acc_total, acc_done = _count_acceptance(body)
            ticket["acceptance_total"] = acc_total
            ticket["acceptance_done"] = acc_done
            ticket["updated"] = now
            data["meta"]["updated"] = now
            self._save(data)
        _log_activity(self._root, {"type": "ticket.body_updated", "ticket": ticket_id, "actor": "cli"})

        return {"id": ticket_id, "bytes": len(body)}

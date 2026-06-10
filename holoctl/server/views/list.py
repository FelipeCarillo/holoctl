"""List view presenter: groups tickets by status into rows ready for the
dense table template."""
from __future__ import annotations

from ...lib.ticket import Ticket
from .card import card_context
from .dates import format_relative_date


def _row_context(t: Ticket, alias: str) -> dict:
    """Card context + the list-specific updated-date display string."""
    c = card_context(t, alias)
    upd_disp, upd_full = format_relative_date(t.get("updated", ""))
    c["upd_display"] = upd_disp
    c["upd_full"] = upd_full
    return c


def list_context(tickets: list[Ticket], statuses: list[str], alias: str) -> dict:
    """Group tickets by status, in config order. Anything off-config sinks
    into an `(unsorted)` bucket so it still renders."""
    grouped: dict[str, list[Ticket]] = {s: [] for s in statuses}
    extras: list[Ticket] = []
    for t in tickets:
        s = t.get("status", "")
        (grouped[s] if s in grouped else extras).append(t)
    if extras:
        grouped["(unsorted)"] = extras

    groups = []
    for status, rows in grouped.items():
        groups.append({
            "status": status,
            "count": len(rows),
            "rows": [_row_context(t, alias) for t in rows],
        })
    return {"groups": groups}

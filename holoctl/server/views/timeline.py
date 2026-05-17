"""Timeline view presenter: groups tickets into lanes (sprint or agent)."""
from __future__ import annotations

from .card import card_context


def _lane_key(ticket: dict, group_by: str) -> tuple[str, str]:
    """(bucket-id, display-label) for a ticket given the lane axis."""
    if group_by == "agent":
        agents = [a for a in (ticket.get("agent") or []) if a]
        if not agents:
            return ("(no agent)", "(no agent)")
        return (agents[0], agents[0])
    sprint = ticket.get("sprint") or ""
    if not sprint:
        return ("(backlog)", "(no sprint)")
    return (sprint, sprint)


def _lane_sort_key(b: str) -> tuple[int, str]:
    # Empty / "(no ...)" buckets last.
    return (1 if b.startswith("(") else 0, b.lower())


def timeline_context(tickets: list[dict], alias: str,
                     group_by: str = "sprint") -> dict:
    """Group tickets into lanes; each lane's tickets sorted by created date."""
    if group_by not in ("sprint", "agent"):
        group_by = "sprint"

    lanes: dict[str, list[dict]] = {}
    labels: dict[str, str] = {}
    for t in tickets:
        bucket, label = _lane_key(t, group_by)
        lanes.setdefault(bucket, []).append(t)
        labels[bucket] = label

    lane_keys = sorted(lanes.keys(), key=_lane_sort_key)

    lane_rows = []
    for bucket in lane_keys:
        lane_tickets = lanes[bucket]
        lane_tickets.sort(key=lambda t: t.get("created", ""))
        rows = []
        for t in lane_tickets:
            c = card_context(t, alias)
            c["completed"] = t.get("completed") or ""
            rows.append(c)
        lane_rows.append({
            "bucket": bucket,
            "label": labels[bucket],
            "count": len(rows),
            "rows": rows,
        })

    return {
        "group_by": group_by,
        "lanes": lane_rows,
        "is_empty": not tickets,
    }

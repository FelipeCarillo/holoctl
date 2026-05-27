"""Detail page presenter: builds the full ticket detail context.

Combines the ticket itself, the rendered markdown body, the linked
relationships (parent / children / depends / blocks), and the activity
timeline (derived events + activity.jsonl entries).
"""
from __future__ import annotations
from pathlib import Path

from .dates import format_iso_datetime
from ..markdown import render_markdown


_TYPE_RANK = {
    "ticket.completed": 0,
    "ticket.body_updated": 1,
    "ticket.updated": 2,
    "ticket.created": 3,
}


def detail_context(ticket: dict, body: str, alias: str,
                   *,
                   all_tickets: list[dict] | None = None,
                   project_root: Path | None = None,
                   statuses: list[str] | None = None) -> dict:
    # Lazy: activity log reader still lives in app.py until cleanup.
    from ..app import _read_ticket_activity

    agents_list = [a for a in (ticket.get("agent") or []) if a]
    tags_list = [t for t in (ticket.get("tags") or []) if t]
    projects_list = [p for p in (ticket.get("projects") or []) if p]
    depends_list = [d for d in (ticket.get("depends") or []) if d]

    parent_id = ticket.get("parent") or ""
    kind = ticket.get("kind") or "task"

    children_list: list[dict] = []
    blocks_list: list[str] = []
    if all_tickets is not None:
        ours = ticket.get("id")
        children_list = [t for t in all_tickets
                         if t.get("parent") == ours and t.get("id") != ours]
        for t in all_tickets:
            if t.get("id") == ours:
                continue
            if ours in (t.get("depends") or []):
                blocks_list.append(t.get("id", ""))

    created = ticket.get("created", "")
    updated = ticket.get("updated", "")
    completed = ticket.get("completed", "")

    body_html = render_markdown(body)

    # Activity: derived events + activity.jsonl, newest first.
    derived: list[dict] = []
    if created:
        derived.append({"ts": created, "label": "Created", "type": "ticket.created"})
    if updated and updated != created:
        derived.append({"ts": updated, "label": "Updated", "type": "ticket.updated"})
    if completed:
        derived.append({"ts": completed, "label": "Marked done", "type": "ticket.completed"})
    if project_root is not None:
        for ev in _read_ticket_activity(project_root, ticket.get("id", "")):
            tp = ev.get("type", "")
            if tp == "ticket.created":  # mirrors `created`, would dedup
                continue
            label = {
                "ticket.body_updated": "Body edited",
            }.get(tp, tp.replace("ticket.", "").replace("_", " ").capitalize())
            derived.append({"ts": ev.get("ts", ""), "label": label, "type": tp})

    derived.sort(
        key=lambda x: (x["ts"], -_TYPE_RANK.get(x["type"], 99)),
        reverse=True,
    )
    activity_items = [
        {**ev, "ts_display": format_iso_datetime(ev["ts"]) or ev["ts"]}
        for ev in derived
    ]

    return {
        "ticket": ticket,
        "body_html": body_html,
        "alias": alias,
        "status": ticket.get("status", "backlog"),
        "priority": ticket.get("priority", "p2"),
        "sprint": ticket.get("sprint") or "",
        "kind": kind,
        "parent_id": parent_id,
        "src_provider": ticket.get("source_provider") or "",
        "src_ref": ticket.get("source_ref") or "",
        "src_url": ticket.get("source_url") or "",
        "src_label": ticket.get("source_label") or "",
        "agents": agents_list,
        "agents_csv": ",".join(agents_list),
        "tags": tags_list,
        "tags_csv": ",".join(tags_list),
        "projects": projects_list,
        "projects_csv": ",".join(projects_list),
        "depends": depends_list,
        "children": children_list,
        "blocks": blocks_list,
        "created": created,
        "updated": updated,
        "completed": completed,
        "created_display": format_iso_datetime(created) or "—",
        "updated_display": format_iso_datetime(updated) or "—",
        "activity": activity_items,
        "statuses_csv": ",".join(statuses or []),
    }

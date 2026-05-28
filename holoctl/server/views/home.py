from __future__ import annotations

from .workspace_summary import workspace_summary


def home_context(projects: list[dict]) -> dict:
    """Shape the project list for the home grid template."""
    summary = workspace_summary(projects)
    if not projects:
        return {"is_empty": True, "cards": [], **summary}
    cards = []
    for p in projects:
        counts = p.get("counts") or {}
        doing = int(counts.get("doing", 0))
        backlog = int(counts.get("backlog", 0))
        done = int(counts.get("done", 0))
        total = max(int(p.get("ticketCount", 0)), 1)
        prefix = p.get("prefix") or ""
        cards.append({
            "alias": p["alias"],
            "name": p["name"],
            "prefix2": prefix[:2],
            "doing": doing,
            "backlog": backlog,
            "done": done,
            "done_pct": f"{done / total * 100:.0f}",
            "doing_pct": f"{doing / total * 100:.0f}",
            "backlog_pct": f"{backlog / total * 100:.0f}",
            "targets": list(p.get("targets") or []),
        })
    return {"is_empty": False, "cards": cards, **summary}

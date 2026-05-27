"""Presenters for the per-project meta pages (agents, commands, context, repos)
and the global agent registry."""
from __future__ import annotations


def agents_context(agents: list[dict], alias: str = "") -> dict:
    cards = []
    for a in agents:
        name = a.get("name", a.get("file", "?").replace(".md", ""))
        tools = a.get("tools") or []
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",")]
        link = (f"/project/{alias}/agents/{a.get('file','').replace('.md','')}"
                if alias else "#")
        cards.append({
            "name": name,
            "model": a.get("model", "standard"),
            "trigger": a.get("trigger", "ticket"),
            "desc": a.get("description", ""),
            "tools": list(tools),
            "link": link,
        })
    return {"cards": cards, "is_empty": not agents}


def commands_context(commands: list[dict], alias: str) -> dict:
    items = []
    for c in commands:
        name = c.get("name", c.get("file", "?").replace(".md", ""))
        items.append({
            "name": name,
            "desc": c.get("description", ""),
            "link": f"/project/{alias}/commands/{c.get('file','').replace('.md','')}",
        })
    return {"items": items, "is_empty": not commands}


_CONTEXT_ICON_MAP = {
    "objective": "objective",
    "architecture": "architecture",
    "conventions": "conventions",
    "decisions": "folder",
    "documents": "folder",
}


def context_context(docs: list[dict], alias: str) -> dict:
    items = []
    for d in docs:
        stem = d["name"].replace(".md", "").lower()
        is_dir = d["isDir"]
        icon_cls = _CONTEXT_ICON_MAP.get(stem, "folder" if is_dir else "doc")
        link = "#" if is_dir else f"/project/{alias}/context/{d['name']}"
        items.append({
            "name": d["name"],
            "desc": d["description"],
            "is_dir": is_dir,
            "icon_cls": icon_cls,
            "link": link,
        })
    return {"items": items, "is_empty": not docs}


def repos_context(repos: list[dict], alias: str) -> dict:
    items = []
    for r in repos:
        git = r.get("git") or {}
        branch = git.get("branch", "—") if git.get("isGit") else "no git"
        dirty = " *" if git.get("dirty") else ""
        items.append({
            "name": r["name"],
            "path": r.get("path", ""),
            "branch_display": f"{branch}{dirty}",
            "ticket_count": int(r.get("ticketCount", 0)),
        })
    return {"items": items, "is_empty": not repos}

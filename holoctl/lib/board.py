from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path

from .markdown import parse_frontmatter, serialize_frontmatter


def _today() -> str:
    return date.today().isoformat()


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
                "meta": {"version": 1, "updated": _today(), "nextId": 1, "counts": {}},
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
                lambda m, v=str_val: f"{m.group(1)}{v}",
                content,
                flags=re.MULTILINE,
            )
        full_path.write_text(content, encoding="utf-8")

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

        return tickets

    def move(self, ticket_id: str, new_status: str) -> dict:
        valid = self._config["board"]["statuses"]
        if new_status not in valid:
            raise ValueError(f"Invalid status: {new_status}. Valid: {'|'.join(valid)}")

        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")

        old_status = ticket["status"]
        today = _today()
        ticket["status"] = new_status
        ticket["updated"] = today
        if new_status == "done":
            ticket["completed"] = today

        data["meta"]["counts"] = self._recount(data["tickets"])
        data["meta"]["updated"] = today
        self._save(data)

        patches = {"status": new_status, "updated": today}
        if new_status == "done":
            patches["completed"] = today
        if ticket.get("file"):
            self._patch_ticket_md(ticket["file"], patches)

        return {"id": ticket_id, "from": old_status, "to": new_status}

    _EDITABLE_FIELDS = {
        "title", "agent", "projects", "status", "priority",
        "sprint", "depends", "tags", "completed",
    }

    def set(self, ticket_id: str, field: str, value: str) -> dict:
        if field not in self._EDITABLE_FIELDS:
            allowed = ", ".join(sorted(self._EDITABLE_FIELDS))
            raise ValueError(f"Field '{field}' is not editable. Allowed: {allowed}")

        if field == "status":
            valid = self._config["board"]["statuses"]
            if value not in valid:
                raise ValueError(f"Invalid status: {value}. Valid: {'|'.join(valid)}")

        data = self._load()
        ticket = next((t for t in data["tickets"] if t["id"] == ticket_id), None)
        if not ticket:
            raise KeyError(f"Ticket {ticket_id} not found")

        parsed = _parse_set_value(value)
        if field in ("agent", "depends", "tags", "projects"):
            parsed = _normalize_array(parsed if isinstance(parsed, (list, str)) else value)

        today = _today()
        ticket[field] = parsed
        ticket["updated"] = today
        data["meta"]["updated"] = today
        if field == "status":
            data["meta"]["counts"] = self._recount(data["tickets"])
        self._save(data)

        if ticket.get("file"):
            self._patch_ticket_md(ticket["file"], {field: parsed, "updated": today})

        return {"id": ticket_id, "field": field, "value": parsed}

    def add(self, patch: dict) -> dict:
        data = self._load()
        next_num = data["meta"]["nextId"]
        ticket_id = self._generate_id(next_num)
        slug = self._slugify(patch.get("title", ""))
        today = _today()

        agents = patch.get("agent", [])
        if isinstance(agents, str):
            agents = [agents]

        tags = patch.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]

        depends = patch.get("depends", [])
        if isinstance(depends, str):
            depends = [d.strip() for d in depends.split(",") if d.strip()]

        # Accept new `projects` (array) or legacy `scope` (string).
        projects = patch.get("projects")
        if projects is None and patch.get("scope"):
            projects = [patch["scope"]]
        projects = _normalize_array(projects)

        ticket: dict = {
            "id": ticket_id,
            "title": patch.get("title", ""),
            "agent": agents,
            "projects": projects,
            "status": patch.get("status", "backlog"),
            "priority": patch.get("priority", "p2"),
            "sprint": patch.get("sprint"),
            "created": today,
            "updated": today,
            "completed": None,
            "depends": depends,
            "tags": tags,
            "file": f"tickets/{ticket_id}-{slug}.md",
        }

        data["tickets"].append(ticket)
        data["meta"]["nextId"] = next_num + 1
        data["meta"]["counts"] = self._recount(data["tickets"])
        data["meta"]["updated"] = today
        self._save(data)

        self._create_ticket_md(ticket)
        _log_activity(self._root, {"type": "ticket.created", "ticket": ticket_id, "actor": "cli"})

        return ticket

    def next_id(self) -> str:
        data = self._load()
        return self._generate_id(data["meta"]["nextId"])

    def rebuild_index(self) -> dict:
        self._tickets_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self._tickets_dir.glob("*.md"))
        tickets = []
        today = _today()

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

            tickets.append({
                "id": data_fm["id"],
                "title": data_fm.get("title", ""),
                "agent": _normalize_array(data_fm.get("agent")),
                "projects": _normalize_array(projects_fm),
                "status": data_fm.get("status", "backlog"),
                "priority": data_fm.get("priority", "p2"),
                "sprint": data_fm.get("sprint"),
                "created": data_fm.get("created", today),
                "updated": data_fm.get("updated", today),
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
                "updated": today,
                "nextId": max_num + 1,
                "counts": self._recount(tickets),
            },
            "tickets": tickets,
        }
        self._save(index)
        return {"ticketCount": len(tickets), "nextId": index["meta"]["nextId"]}

    def _create_ticket_md(self, ticket: dict) -> None:
        md_path = self._board_dir / ticket["file"]
        md_path.parent.mkdir(parents=True, exist_ok=True)

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
        frontmatter = {
            "id": ticket["id"],
            "title": ticket["title"],
            "agent": ", ".join(agents_val) if agents_val else "null",
            "projects": ", ".join(projects_val) if projects_val else "null",
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
    from datetime import datetime, timezone
    log_path = project_root / ".holoctl" / "activity.jsonl"
    entry = {"ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), **event}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

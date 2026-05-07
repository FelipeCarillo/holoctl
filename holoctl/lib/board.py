from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path

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
                lambda m, v=str_val: f"{m.group(1)}{v}",
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
        now = _now()
        ticket["status"] = new_status
        ticket["updated"] = now
        if new_status == "done":
            ticket["completed"] = now

        data["meta"]["counts"] = self._recount(data["tickets"])
        data["meta"]["updated"] = now
        self._save(data)

        patches = {"status": new_status, "updated": now}
        if new_status == "done":
            patches["completed"] = now
        if ticket.get("file"):
            self._patch_ticket_md(ticket["file"], patches)

        # Curator auto-execute (item 8A): when a meta:curate ticket transitions
        # to `done`, the curator action stored in the parallel metadata file
        # is applied. Reversible (e.g. `hctl agent remove` undoes agent_add).
        # Soft-import so curator is not a hard dependency of the board.
        result = {"id": ticket_id, "from": old_status, "to": new_status}
        if (
            new_status == "done"
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

        now = _now()
        ticket[field] = parsed
        ticket["updated"] = now
        data["meta"]["updated"] = now
        if field == "status":
            data["meta"]["counts"] = self._recount(data["tickets"])
        self._save(data)

        if ticket.get("file"):
            self._patch_ticket_md(ticket["file"], {field: parsed, "updated": now})

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
        priorities = self._config["board"]["priorities"]
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

        ticket: dict = {
            "id": ticket_id,
            "title": title,
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

        body = _build_body(patch)
        self._create_ticket_md(ticket, body=body)
        _log_activity(self._root, {"type": "ticket.created", "ticket": ticket_id, "actor": "cli"})

        return ticket

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
            merged.append(m)

        self._validate_batch_parallelism(merged)

        # Pre-flight: validate every ticket through the same rules `add` uses,
        # without creating anything yet.
        statuses = self._config["board"]["statuses"]
        priorities = self._config["board"]["priorities"]
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

            tickets.append({
                "id": data_fm["id"],
                "title": data_fm.get("title", ""),
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
        return {"ticketCount": len(tickets), "nextId": index["meta"]["nextId"]}

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


_BODY_SECTIONS = (
    ("start", "Start"),
    ("context", "Context"),
    ("outOfScope", "Out of scope"),
    ("executionNotes", "Execution notes"),
)


def _build_body(patch: dict) -> str | None:
    """Assemble a ticket body from structured fields in the create patch.

    If `patch["body"]` is set, it wins (raw markdown override). Otherwise
    each of the optional structured fields (`goal`, `start`, `context`,
    `outOfScope`, `executionNotes`) is rendered into a `# Section` block
    and concatenated. Sections without content are omitted entirely.

    Returns None when no structured/body fields are present, signalling to
    the caller that it should fall back to the `_template.md` placeholder.
    """
    raw = patch.get("body")
    if raw is not None and str(raw).strip():
        return str(raw)

    sections: list[str] = []

    goal = patch.get("goal")
    if goal:
        if isinstance(goal, str):
            goal = [g.strip() for g in goal.split("\n") if g.strip()]
        items = "\n".join(f"- [ ] {g}" for g in goal if str(g).strip())
        if items:
            sections.append(f"# Goal — Definition of Done\n\n{items}")

    for key, header in _BODY_SECTIONS:
        val = patch.get(key)
        if val and str(val).strip():
            sections.append(f"# {header}\n\n{str(val).strip()}")

    return "\n\n".join(sections) + "\n" if sections else None


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

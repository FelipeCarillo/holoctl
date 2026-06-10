"""Curator engine — proposes extractions/activations from journal patterns.

The curator never mutates files directly. It emits proposals as ``meta:curate``
tickets on the board, with structured ``metadata`` describing the action the
boardmaster should run if the user approves (moves the ticket to ``done``).

Architecture:

    journal events  ────┐
    library personas    │
    memory state        ├──> curator_rules/* ──> Suggestion ──> board ticket
    open curate state   │                                       (meta:curate)
                        └

Each rule is a small module exposing ``run(context) -> list[Suggestion]``.
The engine collects suggestions, deduplicates against open tickets and
silenced patterns, applies the day-civil rate limit (1 new suggestion per
calendar day per workspace), and persists state in
``.holoctl/curator/state.json``.

Key plan decisions implemented here:
  - item 5A: trigger is the Claude `Stop` hook with a 30-minute cooldown.
  - item 6: default detection is hash-based; embeddings are opt-in via the
    ``[ml]`` extra and `fastembed` import.
  - item 7: PyYAML now in core deps — used to parse `when_to_suggest:` in
    library persona frontmatter.
  - item 8A: when a ``meta:curate`` ticket moves to ``done`` and has
    ``metadata.curator_action``, the boardmaster auto-executes the action.
  - item 9: rate limit is per calendar day (UTC), supression is 14 days
    on `wontfix` or explicit `silence`.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

from .config import load_config
from .journal import Journal
from .memory import Memory


COOLDOWN_MINUTES = 30
SUGGESTIONS_PER_DAY = 1
SUPPRESSION_DAYS = 14


@dataclass
class Suggestion:
    pattern_id: str
    rule: str
    title: str
    rationale: str
    action: str  # "agent_add" | "rule_extract" | "topic_archive" | "memory_promote"
    args: dict[str, Any] = field(default_factory=dict)
    priority: str = "p2"
    files: list[str] = field(default_factory=list)


@dataclass
class CuratorContext:
    project_root: Path
    config: dict
    journal: Journal
    memory: Memory
    state: "CuratorState"


@dataclass
class CuratorState:
    last_run: str | None = None
    suggestions_today: int = 0
    today: str = ""
    silenced: dict[str, str] = field(default_factory=dict)  # pattern_id -> ISO date until
    history: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, root: Path) -> "CuratorState":
        path = root / ".holoctl" / "curator" / "state.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(
            last_run=data.get("last_run"),
            suggestions_today=int(data.get("suggestions_today", 0) or 0),
            today=str(data.get("today") or ""),
            silenced=dict(data.get("silenced") or {}),
            history=list(data.get("history") or []),
        )

    def save(self, root: Path) -> None:
        path = root / ".holoctl" / "curator" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def is_silenced(self, pattern_id: str, *, now: datetime) -> bool:
        until = self.silenced.get(pattern_id)
        if not until:
            return False
        try:
            d = datetime.fromisoformat(until.replace("Z", "+00:00"))
        except ValueError:
            return False
        return now < d

    def silence(self, pattern_id: str, *, days: int = SUPPRESSION_DAYS, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        until = (now + timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
        self.silenced[pattern_id] = until


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_str(*, now: datetime | None = None) -> str:
    return (now or _now()).strftime("%Y-%m-%d")


def _within_cooldown(state: CuratorState, *, now: datetime) -> bool:
    if state.last_run is None:
        return False
    try:
        last = datetime.fromisoformat(state.last_run.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (now - last).total_seconds() < COOLDOWN_MINUTES * 60


def _curator_ticket_meta_dir(project_root: Path) -> Path:
    return project_root / ".holoctl" / "curator" / "tickets"


def _save_ticket_meta(project_root: Path, ticket_id: str, meta: dict) -> None:
    d = _curator_ticket_meta_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ticket_id}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_ticket_meta(project_root: Path, ticket_id: str) -> dict | None:
    path = _curator_ticket_meta_dir(project_root) / f"{ticket_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _open_curate_pattern_ids(project_root: Path) -> set[str]:
    """Pattern IDs that already have an open meta:curate ticket — skip dedup."""
    index_path = project_root / ".holoctl" / "board" / "index.json"
    if not index_path.exists():
        return set()
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    out: set[str] = set()
    for t in data.get("tickets", []) or []:
        if t.get("status") in ("done", "cancelled"):
            continue
        tags = t.get("tags") or []
        if not isinstance(tags, list) or "meta:curate" not in tags:
            continue
        meta = _load_ticket_meta(project_root, t.get("id", ""))
        if meta and meta.get("curator_pattern_id"):
            out.add(meta["curator_pattern_id"])
    return out


def hash_pattern(*parts: str) -> str:
    """Stable hash for deduplication. First 12 hex chars."""
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:12]


# ----------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------


def run_curator(
    project_root: Path,
    *,
    rules: list[Callable[[CuratorContext], list[Suggestion]]] | None = None,
    auto: bool = False,
    bypass_cooldown: bool = False,
    now: datetime | None = None,
) -> list[Suggestion]:
    """Run all rules against the workspace and return new suggestions.

    Side effects:
      - Persists `.holoctl/curator/state.json`.
      - When `auto=True` and a board exists, creates ``meta:curate`` tickets
        for the new suggestions.

    Returns the list of *new* suggestions (after dedup, suppression, rate limit).
    """
    now = now or _now()
    config = load_config(project_root)
    journal = Journal(project_root)
    memory = Memory(project_root)
    state = CuratorState.load(project_root)

    # Day-civil rate limit reset.
    today = _today_str(now=now)
    if state.today != today:
        state.today = today
        state.suggestions_today = 0

    if not bypass_cooldown and _within_cooldown(state, now=now):
        # Still mark last_run? No — cooldown means we explicitly chose not to run.
        return []

    state.last_run = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    # Load rules lazily so curator runs cheap when no rules are passed.
    if rules is None:
        from . import curator_rules
        rules = curator_rules.builtin_rules()

    ctx = CuratorContext(
        project_root=project_root,
        config=config,
        journal=journal,
        memory=memory,
        state=state,
    )

    raw: list[Suggestion] = []
    for rule in rules:
        try:
            raw.extend(rule(ctx))
        except Exception:
            # A rule failure must not crash the whole curator run, but it must
            # be observable — a silently-swallowed exception here means a rule
            # quietly stops producing suggestions with no signal.
            logging.getLogger(__name__).warning(
                "curator rule %r failed; skipping",
                getattr(rule, "__name__", rule),
                exc_info=True,
            )
            continue

    # Deduplicate against silenced + open tickets.
    open_ids = _open_curate_pattern_ids(project_root)
    new: list[Suggestion] = []
    for s in raw:
        if s.pattern_id in open_ids:
            continue
        if state.is_silenced(s.pattern_id, now=now):
            continue
        new.append(s)

    # Apply per-day rate limit on NEW (not yet seen) suggestions.
    budget = max(0, SUGGESTIONS_PER_DAY - state.suggestions_today)
    new = new[:budget]

    if auto and new:
        _materialize_tickets(project_root, config, new)
        state.suggestions_today += len(new)
        for s in new:
            state.history.append({
                "ts": state.last_run,
                "pattern_id": s.pattern_id,
                "rule": s.rule,
                "title": s.title,
            })

    state.save(project_root)
    return new


def _materialize_tickets(project_root: Path, config: dict, suggestions: list[Suggestion]) -> None:
    """Create one meta:curate ticket per suggestion via the Board API.

    Curator-specific metadata (pattern_id, action, args) is stored in a
    parallel file at ``.holoctl/curator/tickets/<ticket_id>.json`` rather
    than in the ticket frontmatter — keeps Board.add() schema clean and
    lets us evolve curator metadata without versioning the board schema.
    """
    from .board import Board
    board = Board(project_root, config)
    for s in suggestions:
        patch = {
            "title": s.title,
            "agent": "boardmaster",
            "priority": s.priority,
            "tags": ["meta:curate"],
            "files": s.files,
            "context": (
                f"{s.rationale}\n\n"
                f"To approve this suggestion, move this ticket to **done** — "
                f"the boardmaster will then execute the proposed action.\n\n"
                f"To reject, move to **cancelled** or run "
                f"`hctl curate silence {s.pattern_id}` (suppresses for "
                f"{SUPPRESSION_DAYS} days)."
            ),
        }
        try:
            ticket = board.add(patch)
        except Exception:
            continue
        _save_ticket_meta(project_root, ticket["id"], {
            "curator_pattern_id": s.pattern_id,
            "curator_action": s.action,
            "curator_args": s.args,
            "curator_rule": s.rule,
        })


def apply_curator_action(project_root: Path, ticket: dict) -> dict | None:
    """Execute the curator action stored in the parallel metadata file.

    Called when a meta:curate ticket transitions to ``done``. Returns a
    small dict describing what was done, or None if the ticket has no
    curator metadata file.
    """
    ticket_id = ticket.get("id")
    if not ticket_id:
        return None
    meta = _load_ticket_meta(project_root, ticket_id)
    if meta is None:
        return None
    action = meta.get("curator_action")
    if not action:
        return None
    args = meta.get("curator_args") or {}
    if action == "agent_add":
        from .agent_library import materialize_agent
        from .config import load_config
        name = args.get("name")
        if not name:
            return {"action": action, "ok": False, "reason": "missing name"}
        body = materialize_agent(name, load_config(project_root))
        if body is None:
            return {"action": action, "ok": False, "reason": f"persona '{name}' not in library"}
        target = project_root / ".holoctl" / "agents" / f"{name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return {"action": action, "ok": True, "result": {"name": name, "path": str(target.relative_to(project_root))}}
    if action == "topic_archive":
        from .memory import Memory
        mem = Memory(project_root)
        name = args.get("name")
        if not name:
            return {"action": action, "ok": False, "reason": "missing name"}
        try:
            mem.archive_topic(name)
            return {"action": action, "ok": True, "result": {"name": name}}
        except FileNotFoundError:
            return {"action": action, "ok": False, "reason": "not found"}
    if action == "memory_promote":
        from .memory import Memory
        mem = Memory(project_root)
        name = args.get("name")
        body = args.get("body", "")
        description = args.get("description", "Promoted from native auto-memory")
        if not name:
            return {"action": action, "ok": False, "reason": "missing name"}
        try:
            mem.add_topic(name, body=body, scope="lazy", description=description)
            return {"action": action, "ok": True, "result": {"name": name}}
        except (ValueError, FileExistsError) as e:
            return {"action": action, "ok": False, "reason": str(e)}
    if action == "rule_extract":
        # rule_extract just produces a topic with scope=glob — same shape as
        # memory_promote but with `globs:`.
        from .memory import Memory
        mem = Memory(project_root)
        name = args.get("name")
        body = args.get("body", "")
        globs = args.get("globs", []) or []
        description = args.get("description") or f"Path-scoped rule for {','.join(globs)}"
        if not name or not globs:
            return {"action": action, "ok": False, "reason": "missing name or globs"}
        try:
            mem.add_topic(name, body=body, scope="glob", globs=globs, description=description)
            return {"action": action, "ok": True, "result": {"name": name, "globs": globs}}
        except (ValueError, FileExistsError) as e:
            return {"action": action, "ok": False, "reason": str(e)}
    return {"action": action, "ok": False, "reason": "unknown action"}


def silence_pattern(project_root: Path, pattern_id: str, *, days: int = SUPPRESSION_DAYS) -> None:
    state = CuratorState.load(project_root)
    state.silence(pattern_id, days=days)
    state.save(project_root)

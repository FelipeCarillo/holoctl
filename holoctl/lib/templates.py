"""Workspace scaffolding templates, loaded from disk.

The Markdown bodies materialized by ``hctl init`` live as real files under
``holoctl/templates/`` (shipped via ``[tool.setuptools.package-data]``, same
mechanism as the agent library):

    templates/commands/<name>.md   → .holoctl/commands/<name>.md
    templates/board/WORKFLOW.md    → .holoctl/board/WORKFLOW.md
    templates/board/_template.md   → .holoctl/board/tickets/_template.md
    templates/context/<name>.md    → .holoctl/context/<name>.md
    templates/instructions.md      → .holoctl/instructions.md

Config interpolation uses the same ``{{dotted.key}}`` placeholder mechanism as
the compiler and the agent library (``resolve_template``), resolved in strict
mode so a typo'd placeholder fails loudly at init instead of leaking literal
``{{...}}`` into a generated file. Beyond raw config keys, templates may use
the computed fields added by :func:`_enrich_for_templates`.
"""
from __future__ import annotations

import copy
from pathlib import Path

from .agent_library import materialize_agent
from .compiler.template import resolve_template


# Files that `get_templates()` produces but which are **user-authored** after
# init and must therefore NOT be refreshed by `hctl sync` / `upgrade` / re-init.
# Everything else `get_templates()` emits is template-managed and belongs in the
# sync allow-list. Agent personas are synced separately (opt-in on
# `sync --agents`, always on `upgrade`), so they are excluded here too.
#   - `.holoctl/context/*`        → user fills these in (objective/arch/conventions)
#   - `.holoctl/instructions.md`  → user-editable project memory (CLAUDE.md source)
#   - `.holoctl/agents/*`         → personas, synced via the agent path
_SYNC_EXCLUDE_PREFIXES = (
    ".holoctl/context/",
    ".holoctl/agents/",
)
_SYNC_EXCLUDE_FILES = frozenset({
    ".holoctl/instructions.md",
})


# Workspace-relative output path → template file path under holoctl/templates/.
_TEMPLATE_SOURCES: dict[str, str] = {
    ".holoctl/board/WORKFLOW.md": "board/WORKFLOW.md",
    ".holoctl/board/tickets/_template.md": "board/_template.md",
    ".holoctl/commands/status.md": "commands/status.md",
    ".holoctl/commands/ticket.md": "commands/ticket.md",
    ".holoctl/commands/spec.md": "commands/spec.md",
    ".holoctl/commands/agent-new.md": "commands/agent-new.md",
    ".holoctl/commands/board.md": "commands/board.md",
    ".holoctl/commands/sprint.md": "commands/sprint.md",
    ".holoctl/commands/decision.md": "commands/decision.md",
    ".holoctl/commands/close.md": "commands/close.md",
    ".holoctl/context/objective.md": "context/objective.md",
    ".holoctl/context/architecture.md": "context/architecture.md",
    ".holoctl/context/conventions.md": "context/conventions.md",
    ".holoctl/instructions.md": "instructions.md",
}


def _derive_sync_targets() -> frozenset[str]:
    """Derive the sync allow-list from ``get_templates()`` keys.

    Single source of truth: a newly added template file is picked up
    automatically (no hand-maintained list to drift out of — exactly the drift
    that left `/spec` and `/agent-new` stale after an upgrade). User-authored
    outputs (context/, instructions.md) and personas (agents/) are excluded so
    sync never clobbers hand-written content.
    """
    from .config import get_defaults

    keys = get_templates(get_defaults()).keys()
    return frozenset(
        k
        for k in keys
        if k not in _SYNC_EXCLUDE_FILES
        and not k.startswith(_SYNC_EXCLUDE_PREFIXES)
    )


def _load_template(rel_path: str) -> str:
    """Read a template file shipped under ``holoctl/templates/``.

    Tries ``importlib.resources`` first (wheel installs), then falls back to a
    path relative to this file (editable / source runs) — same dual strategy as
    ``agent_library.load_library_agent`` and ``compiler.template.load_bootstrap``.
    """
    try:
        from importlib.resources import files as _files
        node = _files("holoctl") / "templates"
        for part in rel_path.split("/"):
            node = node / part
        return node.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        local = Path(__file__).resolve().parent.parent / "templates" / rel_path
        return local.read_text(encoding="utf-8")


def _enrich_for_templates(config: dict) -> dict:
    """Deep-copy *config* and add the computed fields templates rely on.

    Mirrors ``agent_library._enrich`` (statusesJoined/prioritiesJoined/
    boardCliBin) and adds the init-template-specific fields:

      - ``board.statusesBullets`` — one ``- `status``` bullet per line
      - ``project.descriptionOrHint`` — description, or a fill-me-in hint
      - ``project.descriptionOrFallback`` — description, or a neutral sentence
    """
    enriched = copy.deepcopy(config)
    enriched.setdefault("project", {})
    enriched.setdefault("board", {})
    enriched.setdefault("commands", {})

    p = enriched["project"]
    name = p.get("name", "")
    desc = p.get("description")
    p["descriptionOrHint"] = desc or f"(Describe what {name} does in 1-2 sentences)"
    p["descriptionOrFallback"] = desc or f"{name} is a software project."

    statuses = enriched["board"].get("statuses", [])
    priorities = enriched["board"].get("priorities", [])
    enriched["board"]["statusesJoined"] = " | ".join(statuses)
    enriched["board"]["prioritiesJoined"] = " | ".join(priorities)
    enriched["board"]["statusesBullets"] = "\n".join(f"- `{s}`" for s in statuses)

    cli = enriched["commands"].get("boardCli", "hctl board")
    enriched["commands"]["boardCliBin"] = cli.split()[0] if cli else "hctl"
    return enriched


def get_templates(config: dict) -> dict[str, str]:
    """Return the dict of (rel_path → content) materialized at ``hctl init``.

    Only **essential** scaffolding is included — the board's WORKFLOW, ticket
    template, slash commands, context placeholders, ``instructions.md``, and
    the single always-essential persona ``boardmaster``. Non-essential
    personas (developer, reviewer, architect, researcher, …) live latent in
    the library at ``holoctl/templates/agents/*.md`` and are activated on
    demand via ``hctl agent add <name>``.
    """
    enriched = _enrich_for_templates(config)

    out: dict[str, str] = {}
    for rel_path, source in _TEMPLATE_SOURCES.items():
        out[rel_path] = resolve_template(_load_template(source), enriched, strict=True)
        if rel_path == ".holoctl/board/tickets/_template.md":
            # Keep the historical emission order: boardmaster right after the
            # board scaffolding (cosmetic only — affects init's log order).
            out[".holoctl/agents/boardmaster.md"] = materialize_agent("boardmaster", config) or ""
    return out


# Template-managed, non-agent files refreshed by `hctl sync`, `hctl upgrade`,
# and re-`hctl init`. Single source of truth: derived from `get_templates()`
# (see `_derive_sync_targets`) so the three call sites and the template producer
# can never drift apart. Defined at module-bottom so `get_templates` exists.
SYNC_TARGETS = _derive_sync_targets()

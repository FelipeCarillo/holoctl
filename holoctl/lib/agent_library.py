"""Latent library of agent personas.

Personas live as physical .md files in ``holoctl/templates/agents/`` and are
shipped with the package via ``[tool.setuptools.package-data]``. They are
*latent* — none are materialized into a workspace's ``.holoctl/agents/`` by
default except those marked ``when_to_suggest: [{ kind: always_essential }]``
(currently just ``boardmaster``). Other personas are activated either by:

  - the user running ``hctl agent add <name>``
  - the curator (introduced in 0.14) creating a ``meta:curate`` ticket whose
    ``metadata.curator_action`` is ``agent_add`` and the user approving it.

The library is read via ``importlib.resources`` so it works both for installed
wheels and editable/source runs (mirrors ``compiler.template.load_bootstrap``).
"""
from __future__ import annotations

import copy
from pathlib import Path

from .compiler.template import resolve_template


def list_library_agents() -> list[str]:
    """Return persona names (without .md) shipped in the latent library."""
    try:
        from importlib.resources import files as _files
        d = _files("holoctl") / "templates" / "agents"
        # `importlib.resources` yields Traversable (no `.stem`); derive it from name.
        names = [Path(p.name).stem for p in d.iterdir() if p.name.endswith(".md")]
        if names:
            return sorted(names)
    except (FileNotFoundError, ModuleNotFoundError, AttributeError, NotADirectoryError):
        pass
    local = Path(__file__).resolve().parent.parent / "templates" / "agents"
    if local.exists():
        return sorted(p.stem for p in local.glob("*.md"))
    return []


def load_library_agent(name: str) -> str | None:
    """Return the raw .md body of a library persona, or None if absent."""
    try:
        from importlib.resources import files as _files
        path = _files("holoctl") / "templates" / "agents" / f"{name}.md"
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        local = (
            Path(__file__).resolve().parent.parent
            / "templates" / "agents" / f"{name}.md"
        )
        if local.exists():
            return local.read_text(encoding="utf-8")
        return None


def materialize_agent(name: str, config: dict) -> str | None:
    """Load a library persona and resolve ``{{placeholder}}`` against config.

    Adds two computed fields the templates rely on:
      - ``board.statusesJoined`` — ``"backlog | doing | review | done | …"``
      - ``board.prioritiesJoined`` — ``"p0 | p1 | p2 | p3"``
      - ``commands.boardCliBin`` — first token of ``boardCli`` (e.g. ``hctl``).
    """
    body = load_library_agent(name)
    if body is None:
        return None
    enriched = _enrich(config)
    return resolve_template(body, enriched)


def _enrich(config: dict) -> dict:
    enriched = copy.deepcopy(config)
    statuses = enriched.get("board", {}).get("statuses", [])
    priorities = enriched.get("board", {}).get("priorities", [])
    enriched.setdefault("board", {})
    enriched["board"]["statusesJoined"] = " | ".join(statuses)
    enriched["board"]["prioritiesJoined"] = " | ".join(priorities)
    cli = enriched.get("commands", {}).get("boardCli", "hctl board")
    enriched.setdefault("commands", {})
    enriched["commands"]["boardCliBin"] = cli.split()[0] if cli else "hctl"
    return enriched

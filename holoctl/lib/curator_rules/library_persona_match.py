"""Match library personas' `when_to_suggest` heuristics against the journal.

Each persona declares one or more heuristics in its frontmatter
(`when_to_suggest:`), e.g.:

    when_to_suggest:
      - kind: tool_use
        matches: [Edit, Write]
        threshold: 10
        window_sessions: 3
      - kind: file_edit
        glob: "src/**"
        threshold: 8

Supported kinds:
  - tool_use   — counts journal records of kind=tool_use whose payload.tool
                  is in `matches`.
  - file_edit  — counts records of kind=file_edit whose payload.path matches
                  `glob`.
  - prompt_match — counts records of kind=user_prompt whose text contains
                   any pattern in `patterns`.

When ANY of a persona's heuristics fires (count ≥ threshold), the persona
is suggested for activation.

Uses PyYAML to parse the nested list-of-dict structure (item 7 of the plan).
"""
from __future__ import annotations

import fnmatch
from typing import Any

import yaml

from ..agent_library import list_library_agents, load_library_agent
from ..curator import CuratorContext, Suggestion, hash_pattern
from ..markdown import parse_frontmatter


def run(ctx: CuratorContext) -> list[Suggestion]:
    out: list[Suggestion] = []
    library = list_library_agents()
    active_dir = ctx.project_root / ".holoctl" / "agents"
    active = {p.stem for p in active_dir.glob("*.md")} if active_dir.exists() else set()
    candidates = [name for name in library if name not in active]

    # Load all journal records once and let each persona scan in O(N).
    records = list(ctx.journal.iter_records())

    for name in candidates:
        body = load_library_agent(name)
        if not body:
            continue
        suggestions = _parse_when_to_suggest(body)
        if not suggestions:
            continue
        for heuristic in suggestions:
            if heuristic.get("kind") == "always_essential":
                # boardmaster — never auto-suggested; always materialized at init.
                continue
            count = _evaluate(heuristic, records)
            threshold = int(heuristic.get("threshold", 0) or 0)
            if threshold == 0 or count < threshold:
                continue
            pid = hash_pattern("library_persona_match", name, heuristic.get("kind", ""))
            out.append(Suggestion(
                pattern_id=pid,
                rule="library_persona_match",
                title=f"Curate: activate persona '{name}' ({heuristic.get('kind')} ≥{threshold})",
                rationale=(
                    f"Detected {count} signals matching the `{heuristic.get('kind')}` "
                    f"heuristic declared by `{name}` in its frontmatter. Activating "
                    f"this persona materializes it from the latent library at "
                    f"`.holoctl/agents/{name}.md`."
                ),
                action="agent_add",
                args={"name": name},
                files=[f".holoctl/agents/{name}.md"],
            ))
            # Only fire one heuristic per persona — first match wins.
            break
    return out


def _parse_when_to_suggest(body: str) -> list[dict[str, Any]]:
    """Parse just the `when_to_suggest:` list out of frontmatter via PyYAML."""
    if not body.startswith("---\n"):
        return []
    end = body.find("\n---\n", 4)
    if end < 0:
        return []
    fm_text = body[4:end]
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    val = data.get("when_to_suggest") or []
    if not isinstance(val, list):
        return []
    return [item for item in val if isinstance(item, dict)]


def _evaluate(heuristic: dict, records: list[dict]) -> int:
    kind = heuristic.get("kind")
    matches = heuristic.get("matches") or []
    if not isinstance(matches, list):
        matches = [matches]
    if kind == "tool_use":
        return sum(
            1 for r in records
            if r.get("kind") == "tool_use"
            and (r.get("payload") or {}).get("tool") in matches
        )
    if kind == "file_edit":
        glob = heuristic.get("glob")
        if not glob:
            return 0
        return sum(
            1 for r in records
            if r.get("kind") in ("file_edit", "tool_use")
            and _path_matches((r.get("payload") or {}).get("file")
                              or (r.get("payload") or {}).get("path"), glob)
        )
    if kind == "prompt_match":
        patterns = heuristic.get("patterns") or []
        return sum(
            1 for r in records
            if r.get("kind") == "user_prompt"
            and any(
                p.lower() in str((r.get("payload") or {}).get("text") or "").lower()
                for p in patterns
            )
        )
    return 0


def _path_matches(path: Any, pattern: str) -> bool:
    if not isinstance(path, str) or not pattern:
        return False
    return fnmatch.fnmatch(path.replace("\\", "/"), pattern)

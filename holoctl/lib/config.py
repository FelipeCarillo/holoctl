from __future__ import annotations
import copy
import json
from pathlib import Path

_DEFAULTS: dict = {
    "version": 1,
    "project": {
        "name": "MyProject",
        "prefix": "PRJ",
        "description": "",
        "objective": "",
        "repos": [],
    },
    "board": {
        "statuses": ["backlog", "doing", "review", "done", "cancelled"],
        "priorities": ["p0", "p1", "p2", "p3"],
        "idPadding": 3,
        "customFields": {},
    },
    "agents": {
        "defaultModel": "standard",
        "requireTicket": True,
    },
    "commands": {
        "boardCli": "holoctl board",
    },
    "git": {
        # When false (default) holoctl never spawns `git status --porcelain`.
        # The `dirty` flag in `repo list`, `repo info`, `overview`, and the
        # dashboard Repos tab is omitted. Flip to true (per workspace) to
        # restore it. Subprocess spawn is the dominant cost on Windows +
        # corporate AV; off-by-default makes the dashboard instant.
        "checkDirty": False,
    },
    "targets": ["claude"],
    "server": {
        "port": 4242,
        "theme": "dark",
    },
}


# Markers checked when locating a project root. `.holoctl` is canonical;
# `.projctl` and `.projhub` are accepted for backwards compatibility with
# pre-rename installs and are auto-renamed to `.holoctl` on the next save.
_PROJECT_DIR_MARKERS = (".holoctl", ".projctl", ".projhub")


def _existing_marker(root: Path) -> str | None:
    for marker in _PROJECT_DIR_MARKERS:
        if (root / marker / "config.json").exists():
            return marker
    return None


def _migrate_legacy_marker(project_root: Path) -> None:
    canonical = project_root / ".holoctl"
    legacy = _existing_marker(project_root)
    if legacy and legacy != ".holoctl" and not canonical.exists():
        (project_root / legacy).rename(canonical)


def find_project_root(start: Path | None = None) -> Path | None:
    current = Path(start or Path.cwd()).resolve()
    while True:
        if _existing_marker(current):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_config(project_root: Path) -> dict:
    # Migrate legacy `.projctl/` or `.projhub/` BEFORE reading so downstream
    # consumers (board, server) that hardcode `.holoctl/` don't get confused.
    _migrate_legacy_marker(project_root)
    marker = _existing_marker(project_root)
    if marker is None:
        raise FileNotFoundError(f"No .holoctl/config.json found at {project_root}")
    config_path = project_root / marker / "config.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return _deep_merge(copy.deepcopy(_DEFAULTS), raw)


def save_config(project_root: Path, config: dict) -> None:
    """Write config to .holoctl/. Auto-migrates legacy `.projctl/` or `.projhub/`."""
    _migrate_legacy_marker(project_root)
    canonical = project_root / ".holoctl"
    canonical.mkdir(parents=True, exist_ok=True)
    (canonical / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )


def get_defaults() -> dict:
    return copy.deepcopy(_DEFAULTS)


def _deep_merge(target: dict, source: dict) -> dict:
    for key, val in source.items():
        if (
            isinstance(val, dict)
            and isinstance(target.get(key), dict)
        ):
            _deep_merge(target[key], val)
        else:
            target[key] = val
    return target

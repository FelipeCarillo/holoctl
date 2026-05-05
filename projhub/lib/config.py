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
        "boardCli": "projhub board",
    },
    "targets": ["claude"],
    "server": {
        "port": 4242,
        "theme": "dark",
    },
}


def find_project_root(start: Path | None = None) -> Path | None:
    current = Path(start or Path.cwd()).resolve()
    while True:
        if (current / ".projhub" / "config.json").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_config(project_root: Path) -> dict:
    config_path = project_root / ".projhub" / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"No .projhub/config.json found at {project_root}")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return _deep_merge(copy.deepcopy(_DEFAULTS), raw)


def save_config(project_root: Path, config: dict) -> None:
    config_path = project_root / ".projhub" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


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

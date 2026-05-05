from __future__ import annotations
import json
from datetime import date
from pathlib import Path

_WORKSPACE_DIR = Path.home() / ".projhub"
_WORKSPACE_FILE = _WORKSPACE_DIR / "workspace.json"


def _load() -> dict:
    if not _WORKSPACE_FILE.exists():
        return {"version": 1, "projects": []}
    return json.loads(_WORKSPACE_FILE.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    _WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    _WORKSPACE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def add_to_workspace(project_path: Path, alias: str | None = None) -> dict:
    resolved = Path(project_path).resolve()
    today = date.today().isoformat()
    data = _load()

    existing = next((p for p in data["projects"] if p["path"] == str(resolved)), None)
    if existing:
        if alias:
            existing["alias"] = alias
        existing["lastSeen"] = today
    else:
        data["projects"].append({
            "path": str(resolved),
            "alias": alias or resolved.name,
            "added": today,
            "lastSeen": today,
        })

    _save(data)
    return data


def remove_from_workspace(alias_or_path: str) -> dict:
    resolved = str(Path(alias_or_path).resolve())
    data = _load()
    data["projects"] = [
        p for p in data["projects"]
        if p.get("alias") != alias_or_path and p.get("path") != resolved
    ]
    _save(data)
    return data


def list_workspace() -> list[dict]:
    return _load()["projects"]


def get_workspace_path() -> Path:
    return _WORKSPACE_FILE

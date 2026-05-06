from __future__ import annotations
import re
from pathlib import Path


def load_bootstrap(filename: str) -> str | None:
    """Load a `/holoctl` bootstrap template by filename.

    Templates live at `holoctl/templates/commands/<filename>` and are bundled
    via `pyproject.toml` package-data. We try `importlib.resources` first
    (works when installed from a wheel) and fall back to a path relative to
    this file (works for editable / source runs).
    """
    try:
        from importlib.resources import files as _files
        return (_files("holoctl") / "templates" / "commands" / filename).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        local = Path(__file__).resolve().parent.parent.parent / "templates" / "commands" / filename
        if local.exists():
            return local.read_text(encoding="utf-8")
        return None


def resolve_template(template: str, config: dict) -> str:
    def replace(match: re.Match) -> str:
        key = match.group(1).strip()
        val = _get_nested(config, key)
        return str(val) if val is not None else match.group(0)

    return re.sub(r"\{\{([^}]+)\}\}", replace, template)


def _get_nested(obj: dict, key: str):
    parts = key.split(".")
    current = obj
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current

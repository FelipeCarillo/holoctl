from __future__ import annotations
import re


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

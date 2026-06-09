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


class UnresolvedPlaceholderError(KeyError):
    """Raised by :func:`resolve_template` in strict mode for an unknown key.

    Carries the offending placeholder key(s) so callers can report the typo
    rather than silently shipping a literal ``{{...}}`` into a generated file.
    """


def resolve_template(template: str, config: dict, *, strict: bool = False) -> str:
    """Substitute ``{{dotted.key}}`` placeholders from *config*.

    By default an unresolved key is left as the literal ``{{key}}`` (lenient —
    safe for partial configs). In ``strict`` mode an unresolved key raises
    :class:`UnresolvedPlaceholderError` so typos surface at compile time instead
    of leaking a stray placeholder into a generated file. The compile path,
    where ``config`` should be complete, uses ``strict=True``.
    """
    unresolved: list[str] = []

    def replace(match: re.Match) -> str:
        key = match.group(1).strip()
        val = _get_nested(config, key)
        if val is None:
            unresolved.append(key)
            return match.group(0)
        return str(val)

    result = re.sub(r"\{\{([^}]+)\}\}", replace, template)
    if strict and unresolved:
        # De-dupe preserving order for a stable, readable message.
        seen: dict[str, None] = {}
        for k in unresolved:
            seen.setdefault(k, None)
        keys = ", ".join(seen)
        raise UnresolvedPlaceholderError(
            f"unresolved template placeholder(s): {keys}"
        )
    return result


def _get_nested(obj: dict, key: str) -> object:
    parts = key.split(".")
    current: object = obj
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current

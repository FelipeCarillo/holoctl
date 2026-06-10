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


# Placeholder grammar, one alternation per intent (order matters):
#   esc    — `\{{...}}`  explicit escape → emit literal `{{...}}` (backslash dropped)
#   dollar — `${{...}}`  foreign templating (GitHub Actions, shell) → untouched
#   key    — `{{dotted.key}}` a holoctl placeholder → resolved from config
_PLACEHOLDER_RE = re.compile(
    r"(?P<esc>\\\{\{[^}]*\}\})|(?P<dollar>\$\{\{[^}]*\}\})|\{\{(?P<key>[^}]+)\}\}"
)

# Sentinel distinguishing "key absent from config" from "key present with a
# null value" — both read as None through a plain dict.get chain, but they are
# different user errors and deserve different strict-mode messages.
_MISSING = object()


def resolve_template(template: str, config: dict, *, strict: bool = False) -> str:
    """Substitute ``{{dotted.key}}`` placeholders from *config*.

    By default an unresolved key is left as the literal ``{{key}}`` (lenient —
    safe for partial configs). In ``strict`` mode an unresolved key raises
    :class:`UnresolvedPlaceholderError` so typos surface at compile time instead
    of leaking a stray placeholder into a generated file. The compile path,
    where ``config`` should be complete, uses ``strict=True``.

    Two escape hatches let user-authored prose carry literal braces through
    strict mode:

    * ``${{ ... }}`` — foreign templating syntax (GitHub Actions, shell
      parameter expansion) passes through untouched in both modes.
    * ``\\{{...}}`` — explicit escape: the backslash is consumed and the
      literal ``{{...}}`` is emitted, in both modes. (Content that is resolved
      twice — e.g. library personas materialized at init and re-resolved at
      compile — loses the escape on the first pass; shipped templates carry
      no escapes, so this only matters for exotic user pipelines.)
    """
    unresolved: list[str] = []
    null_valued: list[str] = []

    def replace(match: re.Match) -> str:
        if match.group("esc"):
            return match.group(0)[1:]  # drop the backslash, keep `{{...}}`
        if match.group("dollar"):
            return match.group(0)
        key = match.group("key").strip()
        val = _get_nested(config, key)
        if val is _MISSING:
            unresolved.append(key)
            return match.group(0)
        if val is None:
            null_valued.append(key)
            return match.group(0)
        return str(val)

    result = _PLACEHOLDER_RE.sub(replace, template)
    if strict and (unresolved or null_valued):
        # De-dupe preserving order for a stable, readable message.
        def _dedupe(keys: list[str]) -> str:
            seen: dict[str, None] = {}
            for k in keys:
                seen.setdefault(k, None)
            return ", ".join(seen)

        parts: list[str] = []
        if unresolved:
            parts.append(f"unresolved template placeholder(s): {_dedupe(unresolved)}")
        if null_valued:
            parts.append(
                "placeholder(s) whose config value is null: "
                f"{_dedupe(null_valued)} (set a value in .holoctl/config.json)"
            )
        raise UnresolvedPlaceholderError(
            "; ".join(parts)
            + ". For literal braces in prose, escape as \\{{...}}; foreign "
            "templating like ${{...}} passes through untouched."
        )
    return result


def _get_nested(obj: dict, key: str) -> object:
    """Walk a dotted key through nested dicts.

    Returns ``_MISSING`` when any path segment is absent (or the path crosses
    a non-dict), and the stored value otherwise — which may legitimately be
    ``None`` for a present-but-null config key.
    """
    parts = key.split(".")
    current: object = obj
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current

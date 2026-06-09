"""Per-target hook emission — merges holoctl's hooks into existing settings.

Behavior is **merge, never overwrite**: if the user has their own hooks in
`.claude/settings.json`, we add ours alongside (under the same event key)
without removing theirs. If a duplicate of our exact command already
exists (idempotent re-run of `hctl init`/`compile`), we skip.

Resolves `{{HCTL_BIN}}` to the generalist `hctl` command (PATH-resolved), so
the emitted `.claude/settings.json` stays portable when committed and shared
across machines / users / assistants. Set `HOLOCTL_BIN` to override.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _resolve_hctl_bin() -> str:
    # Emit the bare command name, not an absolute exe path: a machine-specific
    # path (from `shutil.which`) breaks the moment the config is committed and
    # used elsewhere. `HOLOCTL_BIN` is the explicit escape hatch for installs
    # where `hctl` isn't on PATH.
    return os.environ.get("HOLOCTL_BIN") or "hctl"


def _load_template(filename: str) -> dict | None:
    text: str | None = None
    try:
        from importlib.resources import files as _files
        text = (_files("holoctl") / "templates" / "hooks" / filename).read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass
    if text is None:
        local = (
            Path(__file__).resolve().parent.parent.parent
            / "templates" / "hooks" / filename
        )
        if not local.exists():
            return None
        text = local.read_text(encoding="utf-8")
    # Parse JSON first, then substitute placeholders in string values. This
    # avoids the Windows-path-vs-JSON-escape problem (backslashes in C:\… get
    # interpreted as JSON escapes if you string-replace pre-parse).
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return _substitute_placeholders(data, {"{{HCTL_BIN}}": _resolve_hctl_bin()})


def _substitute_placeholders(node: Any, mapping: dict[str, str]) -> Any:
    if isinstance(node, str):
        out = node
        for k, v in mapping.items():
            out = out.replace(k, v)
        return out
    if isinstance(node, list):
        return [_substitute_placeholders(x, mapping) for x in node]
    if isinstance(node, dict):
        return {k: _substitute_placeholders(v, mapping) for k, v in node.items()}
    return node


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _merge_lists_dedup(existing: list[Any], incoming: list[Any]) -> list[Any]:
    """Append incoming items that aren't already present (by deep equality)."""
    out = list(existing)
    for item in incoming:
        if item not in out:
            out.append(item)
    return out


def _deep_merge_hooks(target: dict, incoming: dict) -> dict:
    """Merge `incoming` into `target` non-destructively for the
    dict-of-list-of-dict shape used by Claude (.claude/settings.json:hooks)."""
    out = dict(target)
    for key, val in incoming.items():
        if key == "hooks" and isinstance(val, dict):
            existing_hooks = dict(out.get("hooks", {}))
            for event, items in val.items():
                if isinstance(items, list):
                    existing_hooks[event] = _merge_lists_dedup(
                        existing_hooks.get(event, []) if isinstance(existing_hooks.get(event), list) else [],
                        items,
                    )
                else:
                    existing_hooks[event] = items
            out["hooks"] = existing_hooks
        elif key == "permissions" and isinstance(val, dict):
            existing_perms = dict(out.get("permissions", {}))
            for bucket, names in val.items():
                if isinstance(names, list):
                    existing_perms[bucket] = _merge_lists_dedup(
                        existing_perms.get(bucket, []) if isinstance(existing_perms.get(bucket), list) else [],
                        names,
                    )
                else:
                    existing_perms[bucket] = names
            out["permissions"] = existing_perms
        else:
            if key not in out:
                out[key] = val
    return out


def emit_claude(project_root: Path, dry_run: bool = False) -> list[str]:
    """Merge holoctl's hooks + permissions into `.claude/settings.json`."""
    incoming = _load_template("claude_settings.json")
    if incoming is None:
        return []
    path = project_root / ".claude" / "settings.json"
    existing = _read_json(path)
    merged = _deep_merge_hooks(existing, incoming)
    # Incremental skip: the merge is idempotent (dedup), so on an unchanged
    # re-compile ``merged == existing``. Skip the disk write to preserve mtime
    # and avoid churning the git diff. Still report the file as emitted.
    if not dry_run and merged != existing:
        _write_json(path, merged)
    return [".claude/settings.json"]



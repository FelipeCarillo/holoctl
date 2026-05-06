from __future__ import annotations
import re
from pathlib import Path

_HEADER_RE = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\]", re.MULTILINE)


def load_changelog() -> str | None:
    """Load CHANGELOG.md bundled with the package. Mirrors `load_bootstrap`
    in `lib/compiler/template.py` so it works both as wheel and editable."""
    try:
        from importlib.resources import files as _files
        return (_files("holoctl") / "CHANGELOG.md").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        local = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
        if local.exists():
            return local.read_text(encoding="utf-8")
        return None


def _parse(version: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def slice_between(text: str, old: str, new: str) -> str:
    """Return CHANGELOG sections with version > old and <= new.

    Sections are delimited by `## [X.Y.Z]` headers. Anything before the first
    matching header (e.g. the document title) is dropped. Returns empty string
    if no sections fall in the range.
    """
    old_t = _parse(old) or (0, 0, 0)
    new_t = _parse(new)
    if new_t is None:
        return ""

    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        return ""

    out: list[str] = []
    for i, m in enumerate(matches):
        ver = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if not (old_t < ver <= new_t):
            continue
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append(text[start:end].rstrip())

    return "\n\n".join(out).rstrip() + ("\n" if out else "")

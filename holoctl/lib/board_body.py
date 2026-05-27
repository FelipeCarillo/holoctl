"""Assemble a ticket's markdown body from structured create-patch fields.

Extracted from ``Board`` — it's a pure ``dict -> str | None`` transform with
no I/O or ``Board`` coupling, so it reads (and tests) cleanly on its own.
"""
from __future__ import annotations

# Body sections rendered from structured patch fields. Order is the canonical
# document order. Each entry: (preferred_key, legacy_key_or_None, header).
_BODY_SECTIONS = (
    ("context", "start", "Context"),       # `start` is legacy; merges into Context
    ("out_of_scope", "outOfScope", "Out of scope"),
    ("notes", "executionNotes", "Notes"),  # `executionNotes` legacy; lives as `notes` now
)


def build_body(patch: dict) -> str | None:
    """Assemble a ticket body from structured fields in the create patch.

    If `patch["body"]` is set, it wins (raw markdown override). Otherwise:
      - `acceptance` (preferred) or `goal` (legacy) → `# Acceptance — Definition of Done`
      - `context` (preferred) — accepts content from legacy `start` merged in
      - `out_of_scope` (preferred) or legacy `outOfScope`
      - `notes` (preferred) or legacy `executionNotes`

    Returns None when no structured/body fields are present, signalling to
    the caller that it should fall back to the `_template.md` placeholder.
    """
    raw = patch.get("body")
    if raw is not None and str(raw).strip():
        return str(raw)

    sections: list[str] = []

    acceptance = patch.get("acceptance") or patch.get("goal")
    if acceptance:
        if isinstance(acceptance, str):
            acceptance = [g.strip() for g in acceptance.split("\n") if g.strip()]
        items = "\n".join(f"- [ ] {g}" for g in acceptance if str(g).strip())
        if items:
            sections.append(f"# Acceptance — Definition of Done\n\n{items}")

    for preferred, legacy, header in _BODY_SECTIONS:
        val = patch.get(preferred)
        if not val and legacy:
            val = patch.get(legacy)
        # Legacy `start` content merges into `context` (M8 design)
        if preferred == "context":
            extra = patch.get("start")
            if extra and val and str(val).strip() != str(extra).strip():
                val = f"{str(val).strip()}\n\n{str(extra).strip()}"
            elif extra and not val:
                val = extra
        if val and str(val).strip():
            sections.append(f"# {header}\n\n{str(val).strip()}")

    return "\n\n".join(sections) + "\n" if sections else None

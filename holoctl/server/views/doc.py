"""Doc detail presenter: agent / command / context markdown viewer."""
from __future__ import annotations


def doc_context(title: str, body: str, alias: str, kind: str,
                meta: dict | None = None) -> dict:
    from ..app import _render_markdown, _strip_empty_sections

    body_html = _render_markdown(_strip_empty_sections(body))
    meta_rows = []
    if meta:
        for k, v in meta.items():
            if v is None or v == "":
                continue
            meta_rows.append({"label": k, "value": v})
    return {
        "title": title,
        "body_html": body_html,
        "alias": alias,
        "kind": kind,
        "kind_label": kind.capitalize(),
        "meta_rows": meta_rows,
    }

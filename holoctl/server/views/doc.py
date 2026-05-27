"""Doc detail presenter: agent / command / context markdown viewer."""
from __future__ import annotations

from ..markdown import render_markdown


def doc_context(title: str, body: str, alias: str, kind: str,
                meta: dict | None = None) -> dict:
    body_html = render_markdown(body)
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

"""Markdown rendering for the dashboard.

Replaces the hand-rolled `_render_markdown` that used to live in `app.py`.
`strip_empty_sections` drops `# Header` blocks whose body is only
placeholder hints (parenthetical text, empty checklist items, HTML
comments) so template-only tickets render clean.
"""
from __future__ import annotations

import re

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.renderer import RendererHTML
from mdit_py_plugins.tasklists import tasklists_plugin

_PLACEHOLDER_PATTERNS = (
    re.compile(r"^\([^)]*\)\s*$"),                            # `(some hint)`
    re.compile(r"^[-*]\s*\[\s*[xX ]?\s*\]\s+\([^)]*\)\s*$"),  # `- [ ] (criteria)`
    re.compile(r"^<!--.*-->\s*$"),                            # `<!-- HTML comment hint -->`
)

# `html: False` is a security control, not a style choice: ticket bodies can
# come from external/untrusted sources (e.g. `/spec` imports) and the rendered
# HTML is injected into templates with `| safe`, so raw HTML in the source must
# be escaped rather than passed through (otherwise `<img src=x onerror=...>`
# executes — a confirmed XSS). Disabling it makes markdown_it escape any raw
# HTML tags while still rendering all normal markdown (headings, lists, tables,
# code, task lists). See tests/test_markdown_xss.py.
_md = MarkdownIt("gfm-like", {"html": False, "linkify": False}).use(tasklists_plugin, enabled=True)


def _render_fence(self, tokens, idx, options, env):
    """Emit ```mermaid fences as `<pre class="mermaid">` for client-side rendering.

    The diagram source is HTML-escaped, extending the `html: False` guarantee
    above to this custom path: no raw HTML from the fence ever reaches the
    DOM. mermaid.js reads the node's textContent (the browser decodes the
    entities back), so escaping is lossless for the diagram itself.
    Non-mermaid fences keep the default `<pre><code>` rendering.
    """
    token = tokens[idx]
    lang = (token.info or "").strip().split(maxsplit=1)
    if lang and lang[0].lower() == "mermaid":
        return f'<pre class="mermaid">{escapeHtml(token.content)}</pre>\n'
    return RendererHTML.fence(self, tokens, idx, options, env)


_md.add_render_rule("fence", _render_fence)


def _is_placeholder_only(content: str) -> bool:
    real = [line.strip() for line in content.splitlines() if line.strip()]
    if not real:
        return False  # empty body is not a placeholder hint — keep lone headings
    return all(any(p.match(line) for p in _PLACEHOLDER_PATTERNS) for line in real)


def strip_empty_sections(body: str) -> str:
    """Remove heading sections whose content is only placeholder hints."""
    parts = re.split(r"^(# .+)$", body, flags=re.MULTILINE)
    if len(parts) <= 1:
        return body
    out = [parts[0]]
    i = 1
    while i < len(parts):
        header = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""
        if not _is_placeholder_only(content):
            out.append(header)
            out.append(content)
        i += 2
    return "".join(out)


def render_markdown(body: str) -> str:
    """Render a markdown string to HTML, stripping placeholder-only sections."""
    body = strip_empty_sections(body)
    if not body.strip():
        return '<span class="detail-empty">No description</span>'
    return _md.render(body)

"""XSS regression tests for dashboard markdown rendering (review item 1.1).

`render_markdown` output is injected into templates with `| safe`, and ticket
bodies can originate from untrusted sources (`/spec` imports) on a server that
may bind 0.0.0.0. The parser must therefore escape raw HTML in the source
rather than passing it through — otherwise `<img src=x onerror=alert(1)>`
executes in the viewer's browser.

These tests assert that:
  * raw HTML / event-handler payloads are neutralized (escaped, not emitted
    as live tags), and
  * normal markdown (headings, lists, code, task lists, tables, links) still
    renders correctly so the fix doesn't regress legitimate content.
"""
from __future__ import annotations

import pytest

pytest.importorskip("markdown_it")

from holoctl.server.markdown import render_markdown


class TestRawHtmlNeutralized:
    def test_img_onerror_is_escaped(self):
        out = render_markdown("<img src=x onerror=alert(1)>")
        # The live tag must NOT appear; it should be HTML-escaped instead.
        assert "<img" not in out
        assert "&lt;img" in out
        # The handler text may survive as inert escaped text, but never as a
        # real attribute on a real tag.
        assert "<img src=x onerror=alert(1)>" not in out

    def test_script_tag_is_escaped(self):
        out = render_markdown("<script>alert(document.cookie)</script>")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_inline_event_handler_in_anchor_escaped(self):
        out = render_markdown('<a href="#" onclick="alert(1)">click</a>')
        # No live anchor injected from raw HTML.
        assert "<a href=\"#\" onclick=" not in out
        assert "&lt;a" in out

    def test_svg_onload_escaped(self):
        out = render_markdown("<svg onload=alert(1)>")
        assert "<svg" not in out
        assert "&lt;svg" in out

    def test_iframe_escaped(self):
        out = render_markdown('<iframe src="javascript:alert(1)"></iframe>')
        assert "<iframe" not in out
        assert "&lt;iframe" in out

    def test_html_mixed_with_markdown_only_escapes_html(self):
        out = render_markdown("# Title\n\nText <img src=x onerror=alert(1)> more **bold**\n")
        # Markdown still renders…
        assert "<h1>Title</h1>" in out
        assert "<strong>bold</strong>" in out
        # …but the embedded tag is escaped.
        assert "<img" not in out
        assert "&lt;img" in out


class TestNormalMarkdownStillRenders:
    def test_heading(self):
        assert "<h1>" in render_markdown("# Title")

    def test_unordered_list(self):
        html = render_markdown("- one\n- two\n")
        assert "<ul>" in html and "<li>" in html

    def test_ordered_list(self):
        html = render_markdown("1. first\n2. second\n")
        assert "<ol>" in html

    def test_inline_code(self):
        assert "<code>" in render_markdown("call `foo()`")

    def test_fenced_code_block(self):
        html = render_markdown("```\nprint('hi')\n```")
        assert "<pre>" in html and "<code>" in html
        # Content inside a code block is escaped too, never executed.
        html2 = render_markdown("```\n<script>alert(1)</script>\n```")
        assert "<script>" not in html2
        assert "&lt;script&gt;" in html2

    def test_task_list(self):
        html = render_markdown("- [x] done\n- [ ] todo\n")
        assert "checkbox" in html or 'type="checkbox"' in html

    def test_table(self):
        html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |\n")
        assert "<table>" in html and "<td>" in html

    def test_link(self):
        html = render_markdown("see [docs](https://example.com)")
        assert '<a href="https://example.com"' in html

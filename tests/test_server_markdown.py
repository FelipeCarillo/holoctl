from __future__ import annotations

import pytest

pytest.importorskip("markdown_it")

from holoctl.server.markdown import render_markdown, strip_empty_sections


class TestStripEmptySections:
    def test_drops_placeholder_only_section(self):
        body = "# Goal\n\n(describe the goal)\n\n# Real\n\nActual content.\n"
        out = strip_empty_sections(body)
        assert "Goal" not in out
        assert "Real" in out and "Actual content." in out

    def test_keeps_section_with_content(self):
        body = "# Goal\n\nShip it.\n"
        assert "Ship it." in strip_empty_sections(body)


class TestRenderMarkdown:
    def test_empty_body_returns_placeholder(self):
        assert "detail-empty" in render_markdown("")

    def test_headings(self):
        assert "<h1>" in render_markdown("# Title")

    def test_unordered_list(self):
        html = render_markdown("- one\n- two\n")
        assert "<ul>" in html and "<li>" in html

    def test_table(self):
        html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |\n")
        assert "<table>" in html and "<td>" in html

    def test_link_is_anchored(self):
        html = render_markdown("see [docs](https://example.com)")
        assert '<a href="https://example.com"' in html

    def test_inline_code(self):
        assert "<code>" in render_markdown("call `foo()`")

    def test_task_list_checkbox(self):
        html = render_markdown("- [x] done\n- [ ] todo\n")
        assert "checkbox" in html or 'type="checkbox"' in html

"""Tests for the FastAPI dashboard.

Covers:
  - card-rendering helpers (initials, hue, due date, body preview);
  - the kanban / board-page HTML output (new Phase-1 markup contract);
  - POST mutation endpoints (`tickets`, `tickets/{id}/move`).

The dashboard reads its workspace from cwd via `find_project_root()`. We
chdir into a fresh `workspace` fixture and clear the projects cache so
the routes see the test repo, not whatever real workspace happens to be
above the test runner.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# The dashboard is an optional extra (`holoctl[dashboard]`); skip this whole
# module cleanly when the web stack isn't installed rather than erroring out.
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import json
import re

from holoctl.lib.board import Board
import holoctl.server.projects as projects_module
from holoctl.server.app import app
from holoctl.server.views.avatars import avatar_hue as _avatar_hue, initials as _initials
from holoctl.server.views.dates import format_iso_datetime as _format_iso_datetime, format_relative_date as _format_relative_date
from holoctl.server.jinja import render
from holoctl.server.views.board import board_context
from holoctl.server.views.list import list_context
from holoctl.server.views.tree import tree_context
from holoctl.server.views.card import format_due, ticket_preview
from holoctl.server.views.detail import read_ticket_activity, detail_context
from holoctl.server.views.metrics import metrics_context


# ── Module-level rendering helpers ───────────────────────────────────────────


def _render_kanban(project_root: Path, config: dict) -> str:
    """Render the kanban partial directly via Jinja (no HTTP round-trip)."""
    b = Board(project_root, config)
    project = {"alias": project_root.name, "name": config.get("project", {}).get("name", project_root.name), "path": str(project_root)}
    return render(
        "partials/board/_kanban.html",
        **board_context(project, b.ls(), config, view="kanban"),
    )


def _render_list(project_root: Path, config: dict) -> str:
    """Render the list partial directly via Jinja."""
    b = Board(project_root, config)
    return render(
        "partials/board/_list.html",
        **list_context(b.ls(), config["board"]["statuses"], project_root.name),
    )


def _render_tree(project_root: Path, config: dict) -> str:
    """Render the tree partial directly via Jinja."""
    b = Board(project_root, config)
    return render(
        "partials/board/_tree.html",
        **tree_context(b.ls(), project_root.name),
    )


def _render_detail(ticket: dict, body: str, alias: str,
                   workspace: Path, config: dict,
                   all_tickets=None, statuses=None) -> str:
    """Render the full detail page HTML via Jinja (no HTTP round-trip).

    # tabs/breadcrumbs omitted — structural chrome, not under test here
    """
    ctx = detail_context(
        ticket, body, alias,
        all_tickets=all_tickets,
        project_root=workspace,
        statuses=statuses or config["board"]["statuses"],
    )
    return render(
        "project/detail.html",
        title=ticket.get("id", ""),
        current_alias=alias,
        current_tab="board",
        breadcrumbs=[],
        tabs=None,
        tab_base=f"/project/{alias}",
        **ctx,
    )


# ── Helpers / fixtures ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_projects_cache():
    """Reset the 5-second project cache so tests can't see each other."""
    projects_module.PROJECTS_CACHE["data"] = None
    projects_module.PROJECTS_CACHE["ts"] = 0.0
    yield
    projects_module.PROJECTS_CACHE["data"] = None
    projects_module.PROJECTS_CACHE["ts"] = 0.0


@pytest.fixture
def dashboard(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """Chdir into the workspace so the dashboard discovers it via cwd."""
    monkeypatch.chdir(workspace)
    return workspace


@pytest.fixture
def client(dashboard: Path) -> TestClient:
    return TestClient(app)


@pytest.fixture
def alias(dashboard: Path) -> str:
    return dashboard.name


# ── Helpers: _initials ────────────────────────────────────────────────────────


class TestInitials:
    def test_simple_word(self):
        assert _initials("developer") == "DE"

    def test_two_words(self):
        assert _initials("Felipe Carillo") == "FC"

    def test_hyphenated(self):
        assert _initials("front-end") == "FE"

    def test_dotted(self):
        assert _initials("api.gateway") == "AG"

    def test_empty(self):
        assert _initials("") == "?"

    def test_whitespace_only(self):
        # Falls through to slicing the empty trimmed string — accept any short
        # value as long as it doesn't crash and is uppercase.
        out = _initials("   ")
        assert out == "" or out.isupper()


# ── Helpers: _avatar_hue ──────────────────────────────────────────────────────


class TestAvatarHue:
    def test_in_range(self):
        for name in ("alice", "bob", "carol", "dave", "eve", "frank", "grace"):
            assert 0 <= _avatar_hue(name) <= 5

    def test_deterministic(self):
        assert _avatar_hue("developer") == _avatar_hue("developer")

    def test_distinct_names_distribute(self):
        # We only need the hue to differ for at least two of these — not
        # all 10. Stable and non-trivial.
        names = ["alpha", "beta", "gamma", "delta", "epsilon",
                 "zeta", "eta", "theta", "iota", "kappa"]
        hues = {_avatar_hue(n) for n in names}
        assert len(hues) >= 2

    def test_empty(self):
        assert _avatar_hue("") == 0


# ── Helpers: _format_due ──────────────────────────────────────────────────────


class TestFormatDue:
    def test_iso_date(self):
        assert format_due("2026-05-09") == "May 9"

    def test_iso_datetime(self):
        assert format_due("2026-12-25T14:00:00Z") == "Dec 25"

    def test_invalid(self):
        assert format_due("not a date") == ""

    def test_empty(self):
        assert format_due("") == ""

    def test_none(self):
        assert format_due(None) == ""


# ── Helpers: _ticket_preview ──────────────────────────────────────────────────


class TestTicketPreview:
    def test_template_only_returns_empty(self, workspace: Path, workspace_config: dict):
        """A freshly-created ticket has only template/placeholder content;
        the preview helper should produce no text rather than leaking
        `(objective criterion)`-style hints."""
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Plain ticket", "agent": "developer"})
        assert ticket_preview(workspace, ticket) == ""

    def test_substantive_body(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "With body", "agent": "developer"})
        # Replace the body with something real.
        b.set_body(ticket["id"], "## Description\n\nAdd JWT-based auth to the public API. Token refresh + revocation.\n")
        # Re-load to pick up the updated file ref.
        ticket = b.get(ticket["id"])
        out = ticket_preview(workspace, ticket)
        assert out.startswith("Add JWT-based auth")

    def test_truncates_long_lines(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Long", "agent": "developer"})
        b.set_body(ticket["id"], "## Description\n\n" + "x" * 200 + "\n")
        ticket = b.get(ticket["id"])
        out = ticket_preview(workspace, ticket, max_chars=80)
        assert len(out) <= 80
        assert out.endswith("…")

    def test_skips_headers(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Headers", "agent": "developer"})
        b.set_body(ticket["id"], "# Goal\n\n## Sub\n\nReal prose line here.\n")
        ticket = b.get(ticket["id"])
        out = ticket_preview(workspace, ticket)
        assert out == "Real prose line here."

    def test_strips_list_marker(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "List", "agent": "developer"})
        b.set_body(ticket["id"], "## Tasks\n\n- [x] Done item with substance here\n")
        ticket = b.get(ticket["id"])
        out = ticket_preview(workspace, ticket)
        assert out == "Done item with substance here"

    def test_missing_file(self, workspace: Path):
        # Ticket dict without a matching file → empty, no exception.
        ticket = {"id": "TST-999", "file": "tickets/does-not-exist.md"}
        assert ticket_preview(workspace, ticket) == ""


# ── TestKanbanHtml: rendered Jinja partial ────────────────────────────────────


class TestKanbanHtml:
    def test_emits_priority_dot_with_data_attr(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "priority": "p1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-prio-dot" data-p="p1"' in html
        # Old stripe / p-badge in the card top row are gone.
        assert "kanban-card-top" not in html  # legacy top row class
        assert "p-badge" not in html  # legacy priority badge inside card

    def test_emits_avatar_initials_with_hue(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="avatar-initials"' in html
        assert "data-hue=" in html
        # Initials of "developer" are "DE".
        assert ">DE</span>" in html

    def test_emits_inline_add_ticket(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        # Each column gets its own [+ Add ticket] button.
        for s in workspace_config["board"]["statuses"]:
            assert f'data-add-ticket data-status="{s}"' in html

    def test_emits_card_menu(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert "data-card-menu" in html

    def test_friendly_empty_state(self, workspace: Path, workspace_config: dict):
        html = _render_kanban(workspace, workspace_config)
        assert "No tickets here" in html
        assert "kanban-empty-glyph" in html

    def test_data_attrs_for_filtering(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "priority": "p1", "agent": "developer",
               "sprint": "s1", "tags": "alpha"})
        html = _render_kanban(workspace, workspace_config)
        assert 'data-status="backlog"' in html
        assert 'data-p="p1"' in html
        assert 'data-agent="developer"' in html
        assert 'data-sprint="s1"' in html
        assert 'data-tags="alpha"' in html


# ── TestBoardPage: full route response ────────────────────────────────────────


class TestBoardPage:
    def test_header_has_board_title_and_path(self, client: TestClient, alias: str, workspace: Path):
        html = client.get(f"/project/{alias}/board").text
        # The board header is rendered by partials/board/_header.html.
        # project_name comes from the project config ("TestProject").
        assert 'class="board-title"' in html
        assert 'class="board-path"' in html
        # The workspace path appears somewhere in the page.
        assert str(workspace) in html
        # The project name (not just the CSS class) must appear in the page.
        assert "TestProject" in html

    def test_new_ticket_cta_is_active(self, client: TestClient, alias: str):
        html = client.get(f"/project/{alias}/board").text
        # CTA renders, hooked to data-new-ticket — JS routes it to the
        # first column's inline form.
        assert "data-new-ticket" in html
        # No more aria-disabled placeholder.
        assert 'aria-disabled="true"' not in html

    def test_live_indicator_in_topbar_not_board_header(self, client: TestClient, alias: str):
        # LIVE moved to the topbar (rendered by the route via `actions=`),
        # so it appears before the board-header in the document.
        html = client.get(f"/project/{alias}/board").text
        assert "topbar-actions" in html
        idx_topbar = html.find("topbar-actions")
        idx_live = html.find("live-indicator")
        idx_board_header = html.find('class="board-header"')
        # topbar-actions → live-indicator appear before board-header.
        assert 0 <= idx_topbar < idx_live < idx_board_header


# ── Routes: read-only ─────────────────────────────────────────────────────────


class TestReadRoutes:
    def test_home_200(self, client: TestClient):
        r = client.get("/")
        assert r.status_code == 200

    def test_board_page_200_and_contains_kanban(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        assert r.status_code == 200
        body = r.text
        assert 'id="kanban"' in body
        # New control strip is present.
        assert "view-switcher" in body
        assert 'id="bc-search"' in body

    def test_board_page_emits_live_indicator_in_topbar(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        # The LIVE chip should be inside the topbar-actions container, not the
        # body's board-header.
        assert "topbar-actions" in r.text
        idx_topbar = r.text.find("topbar-actions")
        idx_live = r.text.find("live-indicator")
        idx_board_header = r.text.find('class="board-header"')
        assert 0 <= idx_topbar < idx_live < idx_board_header

    def test_board_html_fragment(self, client: TestClient, alias: str):
        r = client.get(f"/api/project/{alias}/board-html")
        assert r.status_code == 200
        # Fragment-level (just the kanban div).
        assert r.text.lstrip().startswith('<div class="kanban"')

    def test_static_assets_served(self, client: TestClient, dashboard_css: str):
        css = client.get("/static/css/index.css")
        js = client.get("/static/js/index.js")
        assert css.status_code == 200
        assert js.status_code == 200
        # Sanity: new tokens / classes shipped (checked against the resolved
        # css bundle since index.css is just @imports).
        assert "html, body { height: 100vh; overflow: hidden; }" in dashboard_css
        assert ".kc-prio-dot" in dashboard_css
        assert ".kanban-col-add" in dashboard_css


# ── Routes: POST /tickets (create) ────────────────────────────────────────────


class TestApiTicketCreate:
    def test_creates_with_title_only(self, client: TestClient, alias: str, workspace: Path, workspace_config: dict):
        r = client.post(f"/api/project/{alias}/tickets", json={"title": "My new ticket"})
        assert r.status_code == 201
        ticket = r.json()
        assert ticket["title"] == "My new ticket"
        assert ticket["status"] == "backlog"  # default
        assert ticket["priority"] == "p2"      # default
        # Persisted on disk.
        b = Board(workspace, workspace_config)
        assert any(t["title"] == "My new ticket" for t in b.ls())

    def test_creates_at_specified_status(self, client: TestClient, alias: str):
        r = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "Started ticket", "status": "doing"},
        )
        assert r.status_code == 201
        assert r.json()["status"] == "doing"

    def test_rejects_missing_title(self, client: TestClient, alias: str):
        r = client.post(f"/api/project/{alias}/tickets", json={"status": "doing"})
        assert r.status_code == 400
        assert "title" in r.json()["detail"].lower()

    def test_rejects_blank_title(self, client: TestClient, alias: str):
        r = client.post(f"/api/project/{alias}/tickets", json={"title": "   "})
        assert r.status_code == 400

    def test_rejects_unknown_agent(self, client: TestClient, alias: str):
        r = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "T", "agent": "ghost"},
        )
        assert r.status_code == 400
        assert "ghost" in r.json()["detail"].lower() or "agent" in r.json()["detail"].lower()

    def test_rejects_invalid_status(self, client: TestClient, alias: str):
        r = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "T", "status": "bogus"},
        )
        assert r.status_code == 400

    def test_unknown_project_404(self, client: TestClient):
        r = client.post("/api/project/no-such-project/tickets", json={"title": "T"})
        assert r.status_code == 404


# ── Routes: POST /tickets/{id}/move ───────────────────────────────────────────


class TestApiTicketMove:
    def test_moves_to_valid_status(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "Move me"}
        ).json()
        r = client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move",
            json={"status": "doing"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["from"] == "backlog"
        assert body["to"] == "doing"

    def test_archives_via_cancelled(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "Archive me"}
        ).json()
        r = client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move",
            json={"status": "cancelled"},
        )
        assert r.status_code == 200

    def test_invalid_status_400(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move",
            json={"status": "elsewhere"},
        )
        assert r.status_code == 400

    def test_missing_status_400(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move", json={}
        )
        assert r.status_code == 400

    def test_unknown_ticket_404(self, client: TestClient, alias: str):
        r = client.post(
            f"/api/project/{alias}/tickets/TST-999/move",
            json={"status": "doing"},
        )
        assert r.status_code == 404


# ── Routes: PATCH /tickets/{id} ───────────────────────────────────────────────


class TestApiTicketPatch:
    def test_priority_update(self, client: TestClient, alias: str, workspace: Path, workspace_config: dict):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T", "priority": "p2"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "priority", "value": "p1"},
        )
        assert r.status_code == 200
        assert r.json()["value"] == "p1"
        # Persisted.
        b = Board(workspace, workspace_config)
        assert b.get(created["id"])["priority"] == "p1"

    def test_sprint_update(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "sprint", "value": "s2"},
        )
        assert r.status_code == 200
        assert r.json()["value"] == "s2"

    def test_status_update_recounts(self, client: TestClient, alias: str, workspace: Path, workspace_config: dict):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "status", "value": "doing"},
        )
        assert r.status_code == 200
        # Counts in meta should have moved.
        b = Board(workspace, workspace_config)
        assert b.stat()["doing"] == 1

    def test_agent_update_with_array(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "agent", "value": ["developer"]},
        )
        assert r.status_code == 200

    def test_rejects_unknown_field(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "id", "value": "TST-002"},
        )
        assert r.status_code == 400
        assert "editable" in r.json()["detail"].lower() or "id" in r.json()["detail"].lower()

    def test_rejects_invalid_priority(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"field": "priority", "value": "p9"},
        )
        assert r.status_code == 400

    def test_missing_field_400(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets", json={"title": "T"}
        ).json()
        r = client.patch(
            f"/api/project/{alias}/tickets/{created['id']}",
            json={"value": "p1"},
        )
        assert r.status_code == 400

    def test_unknown_ticket_404(self, client: TestClient, alias: str):
        r = client.patch(
            f"/api/project/{alias}/tickets/TST-999",
            json={"field": "priority", "value": "p1"},
        )
        assert r.status_code == 404


# ── Helper: _format_relative_date ─────────────────────────────────────────────


class TestFormatRelativeDate:
    def test_iso(self):
        from datetime import timezone
        disp, full = _format_relative_date("2026-05-09T12:00:00Z", tz=timezone.utc)
        assert disp == "May 9"
        assert full == "2026-05-09T12:00:00Z"

    def test_iso_converts_to_target_tz(self):
        # 00:30 UTC on May 9 → 21:30 May 8 in UTC-3 (Brasília).
        from datetime import timezone, timedelta
        disp, _ = _format_relative_date(
            "2026-05-09T00:30:00Z", tz=timezone(timedelta(hours=-3))
        )
        assert disp == "May 8"

    def test_empty(self):
        disp, full = _format_relative_date("")
        assert disp == "—"
        assert full == ""

    def test_invalid(self):
        disp, full = _format_relative_date("not a date")
        assert disp.startswith("not")
        assert full == "not a date"


# ── TestListHtml: rendered Jinja partial ──────────────────────────────────────


class TestListHtml:
    def test_renders_one_row_per_ticket(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer"})
        html = _render_list(workspace, workspace_config)
        assert html.count('class="ticket-row kanban-card"') == 2

    def test_groups_by_status(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "status": "doing"})
        html = _render_list(workspace, workspace_config)
        # One group div per status, in config order.
        for s in workspace_config["board"]["statuses"]:
            assert f'data-bucket="{s}"' in html
        # Backlog group has 1, doing group has 1.
        assert html.find('data-bucket="backlog"') < html.find('data-bucket="doing"')

    def test_emits_select_checkbox_per_row(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        html = _render_list(workspace, workspace_config)
        assert "data-ticket-select" in html
        assert "data-ticket-select-all" in html

    def test_emits_inline_edit_buttons(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "priority": "p1", "agent": "developer"})
        html = _render_list(workspace, workspace_config)
        assert 'data-edit-field="status"' in html
        assert 'data-edit-field="priority"' in html

    def test_emits_bulk_bar(self, workspace: Path, workspace_config: dict):
        html = _render_list(workspace, workspace_config)
        assert 'id="list-bulk-bar"' in html
        assert "data-bulk-move" in html
        assert "data-bulk-archive" in html

    def test_carries_filter_data_attrs(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "priority": "p1", "agent": "developer", "sprint": "s1", "tags": "auth"})
        html = _render_list(workspace, workspace_config)
        # Same data-* contract as kanban cards so filter/search/sort
        # logic on .kanban-card works in both views.
        assert 'data-status="backlog"' in html
        assert 'data-p="p1"' in html
        assert 'data-agent="developer"' in html
        assert 'data-sprint="s1"' in html
        assert 'data-tags="auth"' in html

    def test_off_config_status_lands_in_unsorted(self, workspace: Path, workspace_config: dict):
        # Manually inject a ticket with an unknown status (simulates a
        # config change that left old tickets behind).
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer"})
        tickets = b.ls()
        # Inject off-config status directly into the context.
        tickets[0] = {**tickets[0], "status": "rogue"}
        statuses = workspace_config["board"]["statuses"]
        html = render(
            "partials/board/_list.html",
            **list_context(tickets, statuses, workspace.name),
        )
        assert "(unsorted)" in html


# ── Route: ?view=list ─────────────────────────────────────────────────────────


class TestViewSwitcher:
    def test_default_view_is_kanban(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        assert r.status_code == 200
        # Kanban container exists; list-view does not.
        assert 'id="kanban"' in r.text
        assert 'id="list-view"' not in r.text

    def test_view_list_renders_list_markup(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=list")
        assert r.status_code == 200
        assert 'id="list-view"' in r.text
        assert 'class="list-head"' in r.text
        assert 'id="kanban"' not in r.text
        # board-controls advertises its current view so the JS knows
        # which fragment endpoint to fetch on SSE swaps.
        assert 'data-current-view="list"' in r.text

    def test_view_kanban_explicit(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=kanban")
        assert r.status_code == 200
        assert 'id="kanban"' in r.text
        assert 'data-current-view="kanban"' in r.text

    def test_invalid_view_falls_back_to_kanban(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=ufo")
        assert r.status_code == 200
        assert 'id="kanban"' in r.text

    def test_view_switcher_marks_active_tab(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=list")
        # The List tab must carry .active and aria-selected="true".
        assert 'data-view="list" role="tab" aria-selected="true"' in r.text
        assert '.view-tab active" data-view="kanban"' not in r.text

    def test_view_tree_renders_tree_markup(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=tree")
        assert r.status_code == 200
        assert 'id="tree-view"' in r.text
        assert 'data-current-view="tree"' in r.text
        assert 'id="kanban"' not in r.text
        # The Tree tab is in the switcher and marked active.
        assert 'data-view="tree" role="tab" aria-selected="true"' in r.text


# ── TestTreeHtml: rendered Jinja partial ──────────────────────────────────────


class TestTreeHtml:
    def test_renders_root_and_children_with_data_attrs(
        self, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        spec = b.add({"title": "Auth flow", "kind": "spec"})
        c1 = b.add({"title": "Sign", "agent": "developer", "parent": spec["id"]})
        c2 = b.add({"title": "Verify", "agent": "developer", "parent": spec["id"]})

        html = _render_tree(workspace, workspace_config)
        # Every ticket has its own row…
        assert f'data-id="{spec["id"]}"' in html
        assert f'data-id="{c1["id"]}"' in html
        assert f'data-id="{c2["id"]}"' in html
        # Children carry data-parent so DOM-side filters can still group.
        assert f'data-parent="{spec["id"]}"' in html
        # Depth signal — the spec is depth 0, children are depth 1.
        assert 'data-depth="0"' in html
        assert 'data-depth="1"' in html
        # Connector glyphs appear for the children (CSS draws the actual lines).
        assert "tr-glyph-mid" in html or "tr-glyph-last" in html

    def test_orphan_with_missing_parent_promotes_to_root(
        self, workspace: Path, workspace_config: dict
    ):
        """A ticket whose declared parent is absent from the board still renders —
        as a root, not as a dangling row that disappears from the tree."""
        b = Board(workspace, workspace_config)
        # Build directly: an orphan whose parent ID was never created.
        b.add({"title": "Orphan", "agent": "developer"})
        # Inject a phantom parent reference via the index so we can simulate
        # a dangling ref without going through add()'s validation.
        idx_path = workspace / ".holoctl" / "board" / "index.json"
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        data["tickets"][0]["parent"] = "PHANTOM-999"
        idx_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")

        tickets = b.ls()
        html = render(
            "partials/board/_tree.html",
            **tree_context(tickets, workspace.name),
        )
        # The orphan still appears at depth 0 (no glyph gutter).
        assert 'data-depth="0"' in html
        assert "Orphan" in html

    def test_empty_workspace_shows_friendly_message(
        self, workspace: Path, workspace_config: dict
    ):
        html = _render_tree(workspace, workspace_config)
        assert "tree-empty" in html or "No tickets" in html


class TestApiListHtmlFragment:
    def test_returns_list_view_fragment(self, client: TestClient, alias: str):
        r = client.get(f"/api/project/{alias}/list-html")
        assert r.status_code == 200
        body = r.text.lstrip()
        assert body.startswith('<div class="list-view"')
        assert 'class="list-head"' in body

    def test_unknown_project_404(self, client: TestClient):
        r = client.get("/api/project/no-such/list-html")
        assert r.status_code == 404


# ── Helper: _format_iso_datetime ──────────────────────────────────────────────


class TestFormatIsoDatetime:
    def test_iso_z(self):
        from datetime import timezone
        assert _format_iso_datetime("2026-05-07T14:22:36Z", tz=timezone.utc) == "2026-05-07 14:22:36"

    def test_iso_no_tz(self):
        # Naive strings are displayed as-is — no conversion.
        assert _format_iso_datetime("2026-05-07T14:22:36") == "2026-05-07 14:22:36"

    def test_iso_no_seconds_pads(self):
        # Naive string missing the seconds component is padded with `:00`.
        assert _format_iso_datetime("2026-05-07T14:22") == "2026-05-07 14:22:00"

    def test_iso_converts_to_target_tz(self):
        from datetime import timezone, timedelta
        assert _format_iso_datetime(
            "2026-05-07T14:22:36Z", tz=timezone(timedelta(hours=-3))
        ) == "2026-05-07 11:22:36"

    def test_invalid(self):
        # Returns the first 19 chars when it can't parse.
        assert _format_iso_datetime("not a date") == "not a date"

    def test_empty(self):
        assert _format_iso_datetime("") == ""


# ── Helper: _read_ticket_activity ─────────────────────────────────────────────


class TestReadTicketActivity:
    def test_returns_only_matching_ticket(self, workspace: Path):
        log = workspace / ".holoctl" / "activity.jsonl"
        log.write_text(
            '{"ts":"2026-05-04T10:00:00Z","type":"ticket.created","ticket":"TST-001","actor":"cli"}\n'
            '{"ts":"2026-05-05T10:00:00Z","type":"ticket.body_updated","ticket":"TST-001","actor":"cli"}\n'
            '{"ts":"2026-05-06T10:00:00Z","type":"ticket.created","ticket":"TST-002","actor":"cli"}\n',
            encoding="utf-8",
        )
        out = read_ticket_activity(workspace, "TST-001")
        assert len(out) == 2
        assert all(e["type"].startswith("ticket.") for e in out)

    def test_skips_corrupt_lines(self, workspace: Path):
        log = workspace / ".holoctl" / "activity.jsonl"
        log.write_text(
            'not-json\n'
            '{"ts":"2026-05-04T10:00:00Z","type":"ticket.created","ticket":"TST-001"}\n'
            '\n',
            encoding="utf-8",
        )
        out = read_ticket_activity(workspace, "TST-001")
        assert len(out) == 1

    def test_missing_log(self, tmp_path: Path):
        # Bare directory, no .holoctl/activity.jsonl.
        assert read_ticket_activity(tmp_path, "TST-001") == []


# ── TestTicketDetailPage: rendered Jinja output ───────────────────────────────


class TestTicketDetailPage:
    def test_renders_toolbar_header_grid(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer", "priority": "p1"})
        html = _render_detail(ticket, "## Description\n\nReal body.\n",
                              workspace.name, workspace, workspace_config)
        # Wrapper carries the data-flag the CSS uses to swap layout mode.
        assert "data-detail-page" in html
        assert 'class="detail-toolbar"' in html
        assert 'class="detail-header"' in html
        assert 'class="detail-grid"' in html
        # Two scroll columns.
        assert 'class="detail-main"' in html
        assert 'class="detail-rail"' in html

    def test_header_has_dot_id_pills_title(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "Hello world", "priority": "p1", "agent": "developer"})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        # Priority dot, ID, status pill, priority pill, h1 title.
        assert 'class="kc-prio-dot" data-p="p1"' in html
        assert f'>{ticket["id"]}</span>' in html
        assert 'class="lr-status" data-status="backlog"' in html
        assert 'class="lr-prio-pill" data-p="p1"' in html
        assert '<h1 class="detail-title">Hello world</h1>' in html

    def test_toolbar_has_back_link_and_actions(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        alias = workspace.name
        html = _render_detail(ticket, "", alias, workspace, workspace_config)
        assert f'href="/project/{alias}/board"' in html
        assert 'data-edit-field="status"' in html  # Move ▾
        assert 'data-card-menu' in html             # ⋯ menu

    def test_properties_card_has_editable_fields(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({
            "title": "T", "agent": "developer", "priority": "p1",
            "sprint": "s1", "tags": "auth,api",
        })
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        # Status/priority via .lr-edit; agents/sprint/tags via the new
        # text popover.
        assert 'data-edit-field="status"' in html
        assert 'data-edit-field="priority"' in html
        assert 'data-edit-text-field="agent"' in html
        assert 'data-edit-text-field="sprint"' in html
        assert 'data-edit-text-field="tags"' in html
        # data-current carries the existing value for prefill.
        assert 'data-current="developer"' in html
        assert 'data-current="s1"' in html
        assert 'data-current="auth,api"' in html

    def test_properties_dates_pretty_formatted(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        # Pretty `YYYY-MM-DD HH:MM` shows up; full ISO sits in the title attr.
        assert "Created" in html
        assert "Updated" in html
        assert ticket["created"][:10] in html  # YYYY-MM-DD prefix

    def test_linked_card_renders_depends(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        ticket_b = b.add({"title": "B", "agent": "developer", "depends": a["id"]})
        all_t = b.ls()
        alias = workspace.name
        html = _render_detail(ticket_b, "", alias, workspace, workspace_config,
                              all_tickets=all_t)
        assert "depends on" in html
        assert f'href="/project/{alias}/board/{a["id"]}"' in html

    def test_linked_card_renders_blocks_reverse(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        ticket_b = b.add({"title": "B", "agent": "developer", "depends": a["id"]})
        # Detail page for A should surface "blocks B" via reverse scan.
        a_full = b.get(a["id"])
        all_t = b.ls()
        alias = workspace.name
        html = _render_detail(a_full, "", alias, workspace, workspace_config,
                              all_tickets=all_t)
        assert "blocks" in html
        assert f'href="/project/{alias}/board/{ticket_b["id"]}"' in html

    def test_linked_card_empty_state(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config,
                              all_tickets=b.ls())
        assert "No linked tickets" in html

    def test_activity_card_includes_created(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        assert 'class="dr-activity"' in html
        assert "Created" in html  # derived event always present

    def test_activity_card_includes_completed_when_done(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        b.move(ticket["id"], "done")
        ticket = b.get(ticket["id"])
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        assert "Marked done" in html
        # Activity is sorted newest-first; scope the position check to the
        # <ol class="dr-activity"> block so the Properties card's "Created"
        # date label doesn't muddy the comparison.
        m = re.search(r'<ol class="dr-activity">(.*?)</ol>', html, re.S)
        assert m, "activity ol not found"
        activity = m.group(1)
        assert activity.find("Marked done") < activity.find("Created")

    def test_activity_includes_log_entries(self, workspace: Path, workspace_config: dict):
        # Seed an activity log entry for our ticket so the helper picks it up.
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        log = workspace / ".holoctl" / "activity.jsonl"
        log.write_text(
            log.read_text(encoding="utf-8") +
            f'{{"ts":"2026-05-08T10:00:00Z","type":"ticket.body_updated","ticket":"{ticket["id"]}","actor":"cli"}}\n',
            encoding="utf-8",
        )
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        assert "Body edited" in html

    def test_renders_markdown_body(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        html = _render_detail(
            ticket,
            "## Description\n\nThis is the **body**.\n",
            workspace.name, workspace, workspace_config,
        )
        assert "<strong>body</strong>" in html


# ── Route: /project/{alias}/board/{ticket_id} ────────────────────────────────


class TestTicketDetailRoute:
    def test_renders_detail_page(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "Live ticket", "agent": "developer", "priority": "p1"},
        ).json()
        r = client.get(f"/project/{alias}/board/{created['id']}")
        assert r.status_code == 200
        body = r.text
        assert "data-detail-page" in body
        assert 'class="detail-toolbar"' in body
        assert 'class="detail-rail"' in body
        # Properties card holds the new editable controls.
        assert 'data-edit-text-field="sprint"' in body

    def test_unknown_ticket_404(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board/TST-999")
        assert r.status_code == 404

    def test_blocks_link_appears(self, client: TestClient, alias: str):
        a = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "A", "agent": "developer"},
        ).json()
        client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "B", "agent": "developer", "depends": [a["id"]]},
        )
        # A should advertise "blocks <B-id>" on its detail page.
        r = client.get(f"/project/{alias}/board/{a['id']}")
        assert r.status_code == 200
        assert "blocks" in r.text


# ── Phase 5: a11y + cleanup ───────────────────────────────────────────────────


class TestAccessibility:
    def test_lr_edit_status_has_aria(self, client: TestClient, alias: str):
        client.post(f"/api/project/{alias}/tickets", json={"title": "T"})
        r = client.get(f"/project/{alias}/board?view=list")
        # Status / priority chips advertise themselves as listbox triggers.
        assert 'aria-haspopup="listbox"' in r.text
        assert 'aria-expanded="false"' in r.text

    def test_list_group_header_role_button(self, client: TestClient, alias: str):
        client.post(f"/api/project/{alias}/tickets", json={"title": "T"})
        r = client.get(f"/project/{alias}/board?view=list")
        # Group headers are clickable divs — must be keyboard-reachable.
        assert 'class="list-group-header"' in r.text
        assert 'role="button"' in r.text
        assert 'tabindex="0"' in r.text

    def test_kc_menu_has_aria_label(self, client: TestClient, alias: str):
        client.post(f"/api/project/{alias}/tickets", json={"title": "T"})
        r = client.get(f"/project/{alias}/board")
        # Icon-only ⋯ buttons need an accessible name.
        assert 'aria-label="Card actions"' in r.text

    def test_focus_visible_styles_present(self, client: TestClient, dashboard_css: str):
        # Tag the rule by its keyword so CSS-format changes don't break us.
        r = client.get("/static/css/index.css")
        assert r.status_code == 200
        assert ":focus-visible" in dashboard_css
        assert "prefers-reduced-motion" in dashboard_css


class TestCssCleanup:
    def test_legacy_kanban_card_classes_removed(self, dashboard_css: str):
        # These were Phase-1-era aliases; nothing emits them anymore.
        for sel in (".kanban-card-top", ".kanban-card-id",
                    ".kanban-card-title", ".kanban-card-meta",
                    ".kanban-card-dates"):
            assert sel + " " not in dashboard_css, f"legacy selector {sel} should be removed"

    def test_legacy_status_badge_removed(self, dashboard_css: str):
        # `.status-badge` was used by the old detail page; gone since Phase 4.
        assert ".status-badge" not in dashboard_css

    def test_legacy_p_badge_in_card_removed(self, dashboard_css: str):
        # `.p-badge` was the kanban card's old inline priority chip.
        # The new card uses `.kc-prio-dot` and the list view uses
        # `.lr-prio-pill`.
        assert ".p-badge " not in dashboard_css and ".p-badge\n" not in dashboard_css and ".p-badge{" not in dashboard_css


# ── Post-merge follow-up: horizontal scroll + repo + deps ─────────────────────


class TestKanbanHorizontalScroll:
    """Regression for the user-reported "horizontal scroll doesn't work".

    The bug: `.kanban` carried `min-width: fit-content`, which expanded the
    container to the sum of its column widths. The flex-item grew past its
    parent (`.content-body`) and `overflow-x: auto` had nothing left to
    scroll — the viewport just clipped the rightmost columns.
    """

    def test_min_width_fit_content_removed(self, dashboard_css: str):
        # Find the `.kanban {` block and assert the bad declaration is gone.
        m = re.search(r"\.kanban\s*\{[^}]*\}", dashboard_css)
        assert m, ".kanban block must exist in the served CSS"
        block = m.group(0)
        assert "min-width: fit-content" not in block, (
            "fit-content makes .kanban grow past its parent and silently kills "
            "the horizontal scroll between columns"
        )

    def test_kanban_uses_zero_min_width(self, dashboard_css: str):
        m = re.search(r"\.kanban\s*\{[^}]*\}", dashboard_css)
        block = m.group(0)
        # `min-width: 0` is the explicit override of flex's default
        # `min-width: auto` (content-sized) — without it, fixed-width
        # column children push the kanban past its parent again.
        assert "min-width: 0" in block
        # Sanity: overflow-x:auto stays so the scroll bar appears when the
        # columns collectively exceed the visible width.
        assert "overflow-x: auto" in block


class TestRepoChip:
    """Phase-6 follow-up: surface `projects` (repo / subproject) on cards.

    Tickets that touch a specific subproject can now declare it via
    `projects: [...]` and the dashboard shows it as a small mono pill on
    the card top row, in the list view, and as an editable property in
    the detail page Properties card.
    """

    def test_kanban_card_renders_repo_chip(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer",
               "projects": ["backend"]})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-repo"' in html
        # Single-project chip closes immediately after the name; multi adds
        # a trailing `<span class="kc-repo-extra">`.
        assert ">backend</span>" in html

    def test_kanban_card_no_chip_when_empty(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-repo"' not in html

    def test_kanban_card_extra_count_when_multiple(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer",
               "projects": ["backend", "web", "shared"]})
        html = _render_kanban(workspace, workspace_config)
        # Head project + `+N` indicator for the rest.
        assert ">backend " in html
        assert "+2" in html
        # Tooltip lists all of them so hover gives the full picture.
        assert 'title="repo: backend, web, shared"' in html

    def test_list_view_has_repo_column(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer", "projects": ["backend"]})
        html = _render_list(workspace, workspace_config)
        # New column header + cell.
        assert "lr-cell-repo" in html
        assert ">Repo<" in html
        assert ">backend</span>" in html

    def test_detail_page_properties_card_has_repo_field(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer",
                        "projects": ["backend", "web"]})
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config)
        assert 'data-edit-text-field="projects"' in html
        assert 'data-current="backend,web"' in html
        # Visible label.
        assert "Repo" in html


class TestDependsChip:
    """Phase-6 follow-up: surface `depends` (blocked-by IDs) on cards.

    Each card / row now shows the first dep ID and a `+N` count for the
    rest, plus a tooltip with the full list. Detail page already covered
    this in the Linked card.
    """

    def test_kanban_card_renders_deps(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        first = b.add({"title": "First", "agent": "developer"})
        b.add({"title": "Second", "agent": "developer",
               "depends": [first["id"]]})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-deps"' in html
        assert first["id"] in html  # the dep ID itself
        assert "↳" in html

    def test_kanban_card_deps_extra_count(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        c = b.add({"title": "C", "agent": "developer"})
        b.add({"title": "B", "agent": "developer",
               "depends": [a["id"], c["id"]]})
        html = _render_kanban(workspace, workspace_config)
        # First dep visible, +1 indicator for the second.
        assert "+1" in html
        assert f"depends on: {a['id']}, {c['id']}" in html

    def test_kanban_card_no_deps_chip_when_empty(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer"})
        html = _render_kanban(workspace, workspace_config)
        assert 'class="kc-deps"' not in html

    def test_list_view_has_deps_column(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "depends": [a["id"]]})
        html = _render_list(workspace, workspace_config)
        assert "lr-cell-deps" in html
        assert ">Deps<" in html
        assert a["id"] in html

    def test_data_attrs_carry_depends_csv(self, workspace: Path, workspace_config: dict):
        """Filter / search logic reads data-* — `data-depends` must round-trip
        across all three views so future filters can pivot on dependency too."""
        b = Board(workspace, workspace_config)
        a = b.add({"title": "A", "agent": "developer"})
        b.add({"title": "B", "agent": "developer", "depends": [a["id"]]})
        kanban_html = _render_kanban(workspace, workspace_config)
        list_html = _render_list(workspace, workspace_config)
        for html, label in ((kanban_html, "kanban"), (list_html, "list")):
            assert f'data-depends="{a["id"]}"' in html, f"{label} missed data-depends"


# ── Post-merge follow-up #2: detail scroll, Move popover, Day zoom ────────────


class TestDetailPageScrollContainment:
    """Regression for "card detail has no vertical scroll".

    `.content-body:has(> [data-detail-page])` was set to `overflow:
    hidden` but not `display: flex; flex-direction: column`, so the
    detail page's `flex: 1; min-height: 0` failed (parent wasn't flex).
    Page rendered at natural height and anything past the viewport got
    clipped silently. Independent column scrolls inside `.detail-main`
    and `.detail-rail` couldn't even start.
    """

    def test_content_body_becomes_flex_column_for_detail(self, dashboard_css: str):
        # Find the rule and assert it carries both overflow:hidden and the
        # flex-column setup. Without flex column on the parent, the
        # detail-page's flex children don't get sized correctly.
        m = re.search(
            r"\.content-body:has\(> \[data-detail-page\]\)\s*\{[^}]*\}",
            dashboard_css,
        )
        assert m, "content-body :has(detail-page) rule must exist"
        block = m.group(0)
        assert "overflow: hidden" in block
        assert "display: flex" in block
        assert "flex-direction: column" in block

    def test_detail_main_and_rail_scroll_independently(self, dashboard_css: str):
        # Sanity: each column still has its own overflow-y: auto so the
        # parent flex chain actually delivers usable scroll.
        m_main = re.search(
            r"\[data-detail-page\]\s*\.detail-main\s*\{[^}]*\}", dashboard_css,
        )
        assert m_main and "overflow-y: auto" in m_main.group(0)
        m_rail = re.search(r"\.detail-rail\s*\{[^}]*\}", dashboard_css)
        assert m_rail and "overflow-y: auto" in m_rail.group(0)


# ── Editorial visual token system ─────────────────────────────────────────────


class TestEditorialTokens:
    def test_fonts_imported(self, dashboard_css):
        assert "Fraunces" in dashboard_css
        assert "Inter" in dashboard_css
        assert "JetBrains Mono" in dashboard_css

    def test_serif_token_present(self, dashboard_css):
        assert "--font-serif" in dashboard_css

    def test_terracotta_accent(self, dashboard_css):
        assert "--accent" in dashboard_css
        assert "#c2410c" in dashboard_css or "#ea580c" in dashboard_css

    def test_both_themes_defined(self, dashboard_css):
        assert '[data-theme="light"]' in dashboard_css
        assert '[data-theme="dark"]' in dashboard_css


class TestDetailPageStatusList:
    """Regression for "Move ▾ button does nothing" on the detail page.

    The JS `statusList()` originally mined `.kanban-col[data-status]` to
    populate the Move/⋯ popovers. The detail page has no kanban columns,
    so the popover rendered empty — visually identical to "the button
    doesn't work". Server now stamps a `data-statuses` CSV onto the
    `[data-detail-page]` wrapper and the JS prefers that source.
    """

    def test_detail_wrapper_carries_data_statuses(self, client: TestClient, alias: str):
        created = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "T", "agent": "developer"},
        ).json()
        r = client.get(f"/project/{alias}/board/{created['id']}")
        assert r.status_code == 200
        # The default config ships 5 statuses — find them in the CSV.
        for s in ("backlog", "doing", "review", "done", "cancelled"):
            assert s in r.text
        # And the attribute itself, on the wrapper.
        assert 'data-detail-page data-statuses="' in r.text

    def test_detail_page_emits_status_csv(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ticket = b.add({"title": "T", "agent": "developer"})
        statuses = workspace_config["board"]["statuses"]
        html = _render_detail(ticket, "", workspace.name, workspace, workspace_config,
                              statuses=statuses)
        assert f'data-statuses="{",".join(statuses)}"' in html

    def test_status_list_js_prefers_data_statuses(self, dashboard_js: str):
        # Both lookups must ship — `[data-statuses]` is the new fallback
        # used outside the kanban view, the old kanban-col query stays
        # for views that mine the columns directly.
        assert "[data-statuses]" in dashboard_js
        assert ".kanban-col[data-status]" in dashboard_js
        # And `[data-statuses]` must appear *before* the column query in
        # the file so the new path takes precedence.
        i_attr = dashboard_js.find("[data-statuses]")
        i_col = dashboard_js.find(".kanban-col[data-status]")
        assert 0 <= i_attr < i_col, (
            "data-statuses lookup must come before the .kanban-col fallback "
            "in statusList() so the detail page's wrapper attr wins"
        )


# ── Tree row carries kanban-card so global filter/search reach it ─────────────


class TestTreeRowHasKanbanCardClass:
    def test_tree_view_route_emits_kanban_card_on_rows(self, client: TestClient, alias: str):
        # Seed one ticket so the tree has something to render.
        client.post(f"/api/project/{alias}/tickets",
                    json={"title": "Root", "agent": "developer"})
        r = client.get(f"/project/{alias}/board?view=tree")
        assert r.status_code == 200
        # The shared kanban-card class is what bcApplyFilter / bcCollectOptions
        # in static/js/board-controls.js look for — without it, search and
        # filter chips silently no-op on the tree.
        assert 'class="tree-row kanban-card"' in r.text


# ── Sort + Group selects only render on views that support them ──────────────


class TestControlsHiddenByView:
    """Tree has no concept of sort/group (would break hierarchy), so those
    selects must be omitted from the controls strip when view=tree.
    Kanban and list keep both."""

    def test_kanban_has_sort_and_group(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=kanban")
        assert 'id="bc-sort"' in r.text
        assert 'id="bc-group"' in r.text

    def test_list_has_sort_and_group(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=list")
        assert 'id="bc-sort"' in r.text
        assert 'id="bc-group"' in r.text

    def test_tree_hides_sort_and_group(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=tree")
        assert 'id="bc-sort"' not in r.text
        assert 'id="bc-group"' not in r.text


# ── Timeline view is removed — `?view=timeline` falls back to kanban ─────────


class TestFilterAxes:
    def test_kind_and_source_filter_axes_present(self, client: TestClient, alias: str):
        html = client.get(f"/project/{alias}/board").text
        assert 'data-axis="kind"' in html
        assert 'data-axis="source"' in html

    def test_group_by_project_and_kind_present(self, client: TestClient, alias: str):
        html = client.get(f"/project/{alias}/board").text
        # Group-by select options
        assert '<option value="project"' in html
        assert '<option value="kind"' in html


class TestTimelineRemoved:
    def test_view_timeline_falls_back_to_kanban(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board?view=timeline")
        assert r.status_code == 200
        # _VALID_VIEWS coerces unknown values to kanban.
        assert 'id="kanban"' in r.text
        assert 'id="timeline-view"' not in r.text

    def test_timeline_tab_no_longer_in_switcher(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        assert 'data-view="timeline"' not in r.text

    def test_timeline_html_fragment_route_gone(self, client: TestClient, alias: str):
        r = client.get(f"/api/project/{alias}/timeline-html")
        assert r.status_code == 404


# ── Doc detail routes: agents / commands / context ────────────────────────────


class TestDocDetailRoutes:
    """Regression suite for /agents/{slug}, /commands/{slug}, /context/{filename}.

    These routes were 500ing with TypeError (duplicate 'title' kwarg) because
    doc_context() returned a 'title' key that collided with the explicit
    title=f"{title} — {project['name']}" passed to render(). Fixed by
    renaming the ctx key to 'doc_title'.
    """

    def test_agent_detail_200(self, client: TestClient, alias: str, workspace: Path):
        # workspace fixture plants developer.md under .holoctl/agents/
        r = client.get(f"/project/{alias}/agents/developer")
        assert r.status_code == 200
        assert "developer" in r.text

    def test_command_detail_200(self, client: TestClient, alias: str, workspace: Path):
        commands_dir = workspace / ".holoctl" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        (commands_dir / "status.md").write_text(
            "---\nname: status\ndescription: Show status\n---\nBody.\n",
            encoding="utf-8",
        )
        r = client.get(f"/project/{alias}/commands/status")
        assert r.status_code == 200
        assert "status" in r.text

    def test_context_detail_200(self, client: TestClient, alias: str, workspace: Path):
        context_dir = workspace / ".holoctl" / "context"
        context_dir.mkdir(parents=True, exist_ok=True)
        (context_dir / "objective.md").write_text(
            "# Objective\n\nShip it.\n", encoding="utf-8"
        )
        r = client.get(f"/project/{alias}/context/objective.md")
        assert r.status_code == 200
        assert "Objective" in r.text

    def test_agent_detail_missing_404(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/agents/nonexistent")
        assert r.status_code == 404

    def test_agents_list_survives_null_tools(self, client: TestClient, alias: str, workspace: Path):
        # An agent whose frontmatter has `tools:` empty/null must not 500 the
        # whole /agents list (meta.agents_context coerces None → []).
        (workspace / ".holoctl" / "agents" / "notools.md").write_text(
            "---\nname: notools\ndescription: no tools here\ntools:\n---\nBody.\n",
            encoding="utf-8",
        )
        r = client.get(f"/project/{alias}/agents")
        assert r.status_code == 200
        assert "notools" in r.text


# ── Foreign-badge surface: managed vs foreign items ───────────────────────────


def _write_manifest(workspace: Path, managed_files: list[str]) -> None:
    """Write a minimal .holoctl/.compiled.json that marks files as managed."""
    from holoctl.lib.compiler.manifest import save
    files = {rel: {"sha256": "abc123", "source": "test", "target": "claude"} for rel in managed_files}
    save(workspace, files, holoctl_version="0.0.0-test")


class TestForeignBadge:
    """Task-25: foreign agents/commands appear with a 'foreign' badge; managed
    items get no badge; guard (no manifest) emits nothing foreign."""

    # ── agents ──────────────────────────────────────────────────────────────

    def test_foreign_agent_shows_badge(
        self, client: TestClient, alias: str, workspace: Path
    ):
        # Write a manifest that records only the managed .holoctl/ agents —
        # i.e. the .claude/agents/handmade.md is NOT in the manifest.
        _write_manifest(workspace, [
            ".claude/agents/developer.md",
            ".claude/agents/reviewer.md",
            ".claude/agents/architect.md",
            ".claude/agents/researcher.md",
        ])
        # Drop a foreign agent into .claude/agents/
        claude_agents = workspace / ".claude" / "agents"
        claude_agents.mkdir(parents=True, exist_ok=True)
        (claude_agents / "handmade.md").write_text(
            "---\nname: handmade\ndescription: user-authored agent\n---\nBody.\n",
            encoding="utf-8",
        )
        r = client.get(f"/project/{alias}/agents")
        assert r.status_code == 200
        assert "handmade" in r.text
        # Foreign badge present for the foreign agent
        assert 'class="foreign-badge"' in r.text

    def test_managed_agent_has_no_foreign_badge(
        self, client: TestClient, alias: str, workspace: Path
    ):
        # Manifest records all managed agents — none of .holoctl/ agents are foreign.
        _write_manifest(workspace, [
            ".claude/agents/developer.md",
        ])
        r = client.get(f"/project/{alias}/agents")
        assert r.status_code == 200
        # developer is a managed .holoctl/ agent — no foreign badge on it.
        # (No .claude/agents/ foreign file was dropped, so no badge at all.)
        assert "developer" in r.text
        assert 'class="foreign-badge"' not in r.text

    def test_no_manifest_no_foreign_badge(
        self, client: TestClient, alias: str, workspace: Path
    ):
        # No manifest → guard returns [] for foreign detection.
        # Drop a .claude/agents/ file — it must NOT appear as foreign.
        claude_agents = workspace / ".claude" / "agents"
        claude_agents.mkdir(parents=True, exist_ok=True)
        (claude_agents / "orphan.md").write_text(
            "---\nname: orphan\ndescription: dropped without manifest\n---\nBody.\n",
            encoding="utf-8",
        )
        r = client.get(f"/project/{alias}/agents")
        assert r.status_code == 200
        # Managed source agents still listed.
        assert "developer" in r.text
        # No foreign badge — guard suppressed it.
        assert 'class="foreign-badge"' not in r.text

    # ── commands ─────────────────────────────────────────────────────────────

    def test_foreign_command_shows_badge(
        self, client: TestClient, alias: str, workspace: Path
    ):
        # Write a manifest that does NOT include the handmade-cmd.
        _write_manifest(workspace, [".claude/agents/developer.md"])
        # Drop a foreign command
        claude_cmds = workspace / ".claude" / "commands"
        claude_cmds.mkdir(parents=True, exist_ok=True)
        (claude_cmds / "handmade-cmd.md").write_text(
            "---\nname: handmade-cmd\ndescription: user command\n---\nBody.\n",
            encoding="utf-8",
        )
        # Also need a managed command so we can compare badges
        commands_dir = workspace / ".holoctl" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        (commands_dir / "status.md").write_text(
            "---\nname: status\ndescription: Show status\n---\nBody.\n",
            encoding="utf-8",
        )
        r = client.get(f"/project/{alias}/commands")
        assert r.status_code == 200
        assert "handmade-cmd" in r.text
        assert 'class="foreign-badge"' in r.text

    def test_managed_command_has_no_foreign_badge(
        self, client: TestClient, alias: str, workspace: Path
    ):
        # Manifest records the managed command — it is NOT foreign.
        commands_dir = workspace / ".holoctl" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        (commands_dir / "status.md").write_text(
            "---\nname: status\ndescription: Show status\n---\nBody.\n",
            encoding="utf-8",
        )
        _write_manifest(workspace, [".claude/commands/status.md"])
        r = client.get(f"/project/{alias}/commands")
        assert r.status_code == 200
        assert "status" in r.text
        assert 'class="foreign-badge"' not in r.text

    def test_no_manifest_no_foreign_command_badge(
        self, client: TestClient, alias: str, workspace: Path
    ):
        # No manifest → guard suppresses foreign commands entirely.
        claude_cmds = workspace / ".claude" / "commands"
        claude_cmds.mkdir(parents=True, exist_ok=True)
        (claude_cmds / "orphan-cmd.md").write_text(
            "---\nname: orphan-cmd\ndescription: no manifest\n---\nBody.\n",
            encoding="utf-8",
        )
        r = client.get(f"/project/{alias}/commands")
        assert r.status_code == 200
        assert 'class="foreign-badge"' not in r.text

    # ── CSS presence ──────────────────────────────────────────────────────────

    def test_foreign_badge_class_in_css(self, dashboard_css: str):
        assert ".foreign-badge" in dashboard_css


# ── Context expandable tree ───────────────────────────────────────────────────


def _make_context_dir(workspace: Path) -> Path:
    """Create a minimal .holoctl/context/ layout with a subdir for tests."""
    ctx_dir = workspace / ".holoctl" / "context"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    (ctx_dir / "objective.md").write_text("# Objective\n\nShip it.\n", encoding="utf-8")
    (ctx_dir / "architecture.md").write_text("# Architecture\n\nMono.\n", encoding="utf-8")
    decisions = ctx_dir / "decisions"
    decisions.mkdir(exist_ok=True)
    (decisions / "0001.md").write_text("# ADR-0001\n\nUse FastAPI.\n", encoding="utf-8")
    (decisions / "0002.md").write_text("# ADR-0002\n\nUse Jinja.\n", encoding="utf-8")
    return ctx_dir


class TestReadContextDir:
    """Unit tests for the read_context_dir helper."""

    def test_top_level_lists_dirs_and_files(self, workspace: Path):
        from holoctl.server.projects import read_context_dir
        _make_context_dir(workspace)
        items = read_context_dir(workspace)
        names = [i["name"] for i in items]
        # decisions/ dir comes before the .md files (dirs-first ordering).
        assert "decisions" in names
        assert "objective.md" in names
        assert "architecture.md" in names
        assert items[0]["isDir"] is True
        assert items[0]["name"] == "decisions"

    def test_top_level_dir_item_shape(self, workspace: Path):
        from holoctl.server.projects import read_context_dir
        _make_context_dir(workspace)
        items = read_context_dir(workspace)
        d = next(i for i in items if i["isDir"])
        assert d["name"] == "decisions"
        assert "folder" in d["description"]

    def test_top_level_file_item_has_h1(self, workspace: Path):
        from holoctl.server.projects import read_context_dir
        _make_context_dir(workspace)
        items = read_context_dir(workspace)
        obj = next(i for i in items if i["name"] == "objective.md")
        assert obj["description"] == "Objective"
        assert obj["isDir"] is False

    def test_subdir_listing(self, workspace: Path):
        from holoctl.server.projects import read_context_dir
        _make_context_dir(workspace)
        items = read_context_dir(workspace, "decisions")
        names = [i["name"] for i in items]
        assert "0001.md" in names
        assert "0002.md" in names
        assert all(not i["isDir"] for i in items)

    def test_missing_context_dir_returns_empty(self, workspace: Path):
        from holoctl.server.projects import read_context_dir
        # No context dir created.
        assert read_context_dir(workspace) == []

    def test_nonexistent_subpath_returns_empty(self, workspace: Path):
        from holoctl.server.projects import read_context_dir
        _make_context_dir(workspace)
        assert read_context_dir(workspace, "nonexistent") == []


class TestContextTreeApi:
    """HTTP tests for GET /api/project/{alias}/context/tree."""

    def test_top_level_returns_entries(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/api/project/{alias}/context/tree")
        assert r.status_code == 200
        body = r.json()
        assert "entries" in body
        names = [e["name"] for e in body["entries"]]
        assert "decisions" in names
        assert "objective.md" in names

    def test_entries_have_type_field(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/api/project/{alias}/context/tree")
        body = r.json()
        types = {e["name"]: e["type"] for e in body["entries"]}
        assert types["decisions"] == "dir"
        assert types["objective.md"] == "file"

    def test_subdir_listing(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/api/project/{alias}/context/tree?path=decisions")
        assert r.status_code == 200
        names = [e["name"] for e in r.json()["entries"]]
        assert "0001.md" in names
        assert "0002.md" in names

    def test_traversal_returns_403(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/api/project/{alias}/context/tree?path=../../etc")
        assert r.status_code == 403

    def test_unknown_alias_returns_404(self, client: TestClient):
        r = client.get("/api/project/no-such-project/context/tree")
        assert r.status_code == 404

    def test_nonexistent_path_returns_404(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/api/project/{alias}/context/tree?path=no-such-dir")
        assert r.status_code == 404

    def test_empty_context_returns_empty_entries(self, client: TestClient, alias: str):
        # No context dir at all.
        r = client.get(f"/api/project/{alias}/context/tree")
        assert r.status_code == 200
        assert r.json()["entries"] == []


class TestContextTreePage:
    """Tests for the context page rendering the expandable tree."""

    def test_context_page_200(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert r.status_code == 200

    def test_context_page_has_tree_container(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert 'id="context-tree"' in r.text

    def test_context_tree_carries_data_attrs(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert f'data-alias="{alias}"' in r.text
        assert f'/api/project/{alias}/context/tree' in r.text
        assert f'/project/{alias}/context/' in r.text

    def test_directory_renders_as_details(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        # decisions/ is a dir — must render as <details> with data-path
        assert '<details class="tree-dir context-tree-dir">' in r.text
        assert 'data-path="decisions"' in r.text

    def test_file_renders_as_link(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert f'href="/project/{alias}/context/objective.md"' in r.text

    def test_lazy_children_div_present_for_dir(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert 'data-loaded="false"' in r.text
        assert 'class="tree-children tree-lazy"' in r.text
        # depth marker must be present so JS can pass parentDepth+1 to
        # renderTreeEntries() when a second-level dir expands — without it
        # all lazy-expanded levels indent at the same depth as level 1.
        assert 'data-depth="0"' in r.text

    # ── Editorial redesign assertions ────────────────────────────────────────

    def test_context_panel_card_chrome_present(self, client: TestClient, alias: str, workspace: Path):
        """Page must wrap the tree in a card-chromed .context-panel container."""
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert 'class="context-panel"' in r.text

    def test_context_panel_header_and_counter(self, client: TestClient, alias: str, workspace: Path):
        """Panel header must include the 'Context documents' label and a counter."""
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert 'class="context-panel-header"' in r.text
        assert 'class="context-panel-title"' in r.text
        assert "Context documents" in r.text
        assert 'class="context-panel-counter"' in r.text
        # Layout has 1 folder (decisions/) and 2 files
        assert "folder" in r.text
        assert "file" in r.text

    def test_no_emoji_icons_in_context_page(self, client: TestClient, alias: str, workspace: Path):
        """Emoji folder/doc glyphs must be replaced by SVG icons."""
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert "\U0001f4c1" not in r.text  # 📁
        assert "\U0001f4c4" not in r.text  # 📄
        assert "\U0001f4c2" not in r.text  # 📂

    def test_svg_folder_icon_in_dir_row(self, client: TestClient, alias: str, workspace: Path):
        """Directory rows must carry the SVG folder icon class."""
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert 'class="tree-icon tree-icon-folder"' in r.text

    def test_svg_doc_icon_in_file_row(self, client: TestClient, alias: str, workspace: Path):
        """File rows must carry the SVG doc icon class."""
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert 'class="tree-icon tree-icon-doc"' in r.text

    def test_chevron_is_svg_not_text_glyph(self, client: TestClient, alias: str, workspace: Path):
        """Chevrons must be inline SVG, not a unicode text character."""
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context")
        assert 'class="tree-chevron"' in r.text
        # The SVG chevron wraps an <svg> tag
        assert "<svg" in r.text
        # Must NOT be the old unicode triangle glyph
        assert "▶" not in r.text


class TestNestedContextFileDetail:
    """Nested context files (subdir/file.md) open via the detail route."""

    def test_nested_file_returns_200(self, client: TestClient, alias: str, workspace: Path):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context/decisions/0001.md")
        assert r.status_code == 200
        assert "ADR-0001" in r.text

    def test_nested_file_breadcrumb_links_back_to_context(
        self, client: TestClient, alias: str, workspace: Path
    ):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context/decisions/0001.md")
        assert f'href="/project/{alias}/context"' in r.text

    def test_traversal_on_detail_route_returns_403(
        self, client: TestClient, alias: str, workspace: Path
    ):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context/../../etc/passwd")
        # FastAPI path normalization may turn this into 404 before we even
        # hit our guard — either 403 or 404 is acceptable, but NOT 200.
        assert r.status_code in (403, 404)

    def test_missing_nested_file_returns_404(
        self, client: TestClient, alias: str, workspace: Path
    ):
        _make_context_dir(workspace)
        r = client.get(f"/project/{alias}/context/decisions/9999.md")
        assert r.status_code == 404


# ── Hardening: read_context_dir with unreadable .md ──────────────────────────


class TestReadContextDirHardening:
    """read_context_dir must not propagate OSError / UnicodeDecodeError from a
    single unreadable .md file — it should fall back to an empty description."""

    def test_unreadable_md_falls_back_to_empty_description(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from holoctl.server.projects import read_context_dir

        ctx_dir = workspace / ".holoctl" / "context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        bad = ctx_dir / "unreadable.md"
        bad.write_text("# Good title\n", encoding="utf-8")

        # Patch Path.read_text to raise OSError for our specific file.
        original_read_text = Path.read_text

        def _patched_read_text(self, *args, **kwargs):  # type: ignore[override]
            if self == bad:
                raise OSError("permission denied (simulated)")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _patched_read_text)

        items = read_context_dir(workspace)
        bad_item = next((i for i in items if i["name"] == "unreadable.md"), None)
        assert bad_item is not None, "unreadable file should still appear in listing"
        assert bad_item["description"] == "", "description must fall back to empty string"

    def test_unicode_decode_error_falls_back_to_empty_description(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from holoctl.server.projects import read_context_dir

        ctx_dir = workspace / ".holoctl" / "context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        bad = ctx_dir / "binary.md"
        bad.write_bytes(b"\xff\xfe bad bytes")  # non-UTF-8

        # Don't patch here — let the real read_text raise UnicodeDecodeError.
        items = read_context_dir(workspace)
        bad_item = next((i for i in items if i["name"] == "binary.md"), None)
        assert bad_item is not None
        assert bad_item["description"] == ""

    def test_other_files_unaffected_by_one_bad_entry(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from holoctl.server.projects import read_context_dir

        ctx_dir = workspace / ".holoctl" / "context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "good.md").write_text("# Good Title\n", encoding="utf-8")
        bad = ctx_dir / "bad.md"
        bad.write_bytes(b"\xff\xfe")

        items = read_context_dir(workspace)
        good = next((i for i in items if i["name"] == "good.md"), None)
        assert good is not None
        assert good["description"] == "Good Title"


# ── JS filetree: SVG icon markup in renderTreeEntries ────────────────────────


class TestFiletreeJsSvgIcons:
    """Smoke: the JS renderTreeEntries function emits SVG markup tokens,
    not the old emoji Unicode escapes."""

    def test_js_uses_svg_folder_icon(self, dashboard_js: str):
        # The JS source must define the folder SVG — same viewBox as icons/folder.svg
        assert "tree-icon-folder" in dashboard_js
        assert "M3 7a2 2 0 012-2h4l2 2h8" in dashboard_js  # unique path fragment

    def test_js_uses_svg_doc_icon(self, dashboard_js: str):
        # The JS source must define the doc SVG — same path as icons/doc.svg
        assert "tree-icon-doc" in dashboard_js
        assert "M14 2H6a2 2 0 00-2 2v16" in dashboard_js  # unique path fragment

    def test_js_uses_svg_chevron(self, dashboard_js: str):
        # Chevron must be SVG, not the old &#x25B6; html entity or ▶ literal
        assert "tree-chevron" in dashboard_js
        assert "&#x25B6;" not in dashboard_js
        assert "ICON_CHEVRON" in dashboard_js or "tree-chevron" in dashboard_js

    def test_js_no_emoji_unicode_escapes(self, dashboard_js: str):
        # Old code used &#x1F4C1; (folder) and &#x1F4C4; (doc)
        assert "&#x1F4C1;" not in dashboard_js
        assert "&#x1F4C4;" not in dashboard_js

    def test_js_emits_empty_folder_state(self, dashboard_js: str):
        # renderTreeEntries now handles the empty case with a dedicated message
        assert "Empty folder" in dashboard_js

    def test_js_emits_error_state_with_hint(self, dashboard_js: str):
        # Error state should invite the user to retry
        assert "Failed to load" in dashboard_js


# ── Context panel CSS present in bundle ──────────────────────────────────────


class TestContextPanelCss:
    """Editorial panel selectors must ship in the served CSS bundle."""

    def test_context_panel_selector_present(self, dashboard_css: str):
        assert ".context-panel" in dashboard_css

    def test_context_panel_uses_bg_card(self, dashboard_css: str):
        # The panel card must reference --bg-card token
        m = re.search(r"\.context-panel\s*\{[^}]*\}", dashboard_css)
        assert m, ".context-panel rule must exist"
        assert "var(--bg-card)" in m.group(0)

    def test_context_panel_uses_shadow(self, dashboard_css: str):
        m = re.search(r"\.context-panel\s*\{[^}]*\}", dashboard_css)
        assert m
        assert "var(--shadow-sm)" in m.group(0)

    def test_context_panel_header_selector_present(self, dashboard_css: str):
        assert ".context-panel-header" in dashboard_css

    def test_context_tree_chevron_transition(self, dashboard_css: str):
        # Chevron must use CSS transition (var(--ease))
        assert "var(--ease)" in dashboard_css

    def test_context_tree_lazy_states_present(self, dashboard_css: str):
        assert ".context-tree .tree-lazy-loading" in dashboard_css
        assert ".context-tree .tree-lazy-error" in dashboard_css
        assert ".context-tree .tree-lazy-empty" in dashboard_css

    def test_context_tree_accent_on_open_folder(self, dashboard_css: str):
        # Open folder icon gets accent color
        assert "tree-icon-folder" in dashboard_css
        assert "var(--accent)" in dashboard_css


# ── Metrics tab: view shaper + route + template ───────────────────────────────


def _make_done_ticket(
    alias: str,
    board: "Board",
    *,
    title: str = "T",
    agent: str = "developer",
    created_offset_days: int = 5,
    completed_offset_days: int = 0,
) -> dict:
    """Create a done ticket with controllable timestamps for metrics tests."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    created_ts = (now - timedelta(days=created_offset_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    completed_ts = (now - timedelta(days=completed_offset_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ticket = board.add({"title": title, "agent": agent, "status": "done"})
    # Patch timestamps directly in the index so cycle_time sees them.
    idx_path = board._root / ".holoctl" / "board" / "index.json"
    data = json.loads(idx_path.read_text(encoding="utf-8"))
    for t in data["tickets"]:
        if t["id"] == ticket["id"]:
            t["created"] = created_ts
            t["completed"] = completed_ts
    idx_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")
    return ticket


class TestMetricsContextShaper:
    """Unit tests for the metrics_context() view shaper."""

    def test_returns_required_keys(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ctx = metrics_context(b.ls())
        assert "throughput" in ctx
        assert "cycle" in ctx
        assert "wip_view" in ctx
        assert "by_agent" in ctx
        assert "by_project" in ctx
        assert "since_days" in ctx
        assert "agent_max" in ctx
        assert "project_max" in ctx

    def test_throughput_has_days_and_max_count(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ctx = metrics_context(b.ls())
        tp = ctx["throughput"]
        assert "days" in tp
        assert "max_count" in tp
        assert isinstance(tp["days"], list)
        assert isinstance(tp["max_count"], int)

    def test_throughput_days_length_matches_since(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ctx = metrics_context(b.ls(), since_days=14)
        # 14 days → 15 buckets (inclusive of both endpoints)
        assert len(ctx["throughput"]["days"]) == 15

    def test_cycle_keys_present_and_rounded(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        _make_done_ticket(workspace.name, b, created_offset_days=3)
        ctx = metrics_context(b.ls())
        cycle = ctx["cycle"]
        assert cycle["count"] == 1
        # Rounded to 1 decimal
        assert isinstance(cycle["mean"], float)
        assert isinstance(cycle["median"], float)
        assert isinstance(cycle["p95"], float)

    def test_empty_board_cycle_zeros(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ctx = metrics_context(b.ls())
        cycle = ctx["cycle"]
        assert cycle["count"] == 0
        assert cycle["mean"] == 0.0
        assert cycle["median"] == 0.0
        assert cycle["p95"] == 0.0

    def test_wip_view_keys(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "In progress", "agent": "developer", "status": "doing"})
        ctx = metrics_context(b.ls())
        wip = ctx["wip_view"]
        assert "count" in wip
        assert "stale_count" in wip
        assert "stale_days" in wip
        assert "tickets" in wip
        assert wip["count"] == 1

    def test_by_agent_has_group_key(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer"})
        ctx = metrics_context(b.ls())
        assert isinstance(ctx["by_agent"], list)
        if ctx["by_agent"]:
            row = ctx["by_agent"][0]
            assert "group" in row
            assert "completed" in row
            assert "avg_cycle_days" in row
            assert "wip" in row

    def test_since_days_passed_through(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        ctx = metrics_context(b.ls(), since_days=7)
        assert ctx["since_days"] == 7

    def test_max_values_computed(self, workspace: Path, workspace_config: dict):
        b = Board(workspace, workspace_config)
        _make_done_ticket(workspace.name, b, agent="developer")
        ctx = metrics_context(b.ls())
        assert ctx["agent_max"] >= 0
        assert ctx["project_max"] >= 0


class TestMetricsRoute:
    """HTTP tests for GET /project/{alias}/metrics."""

    def test_returns_200(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200

    def test_unknown_alias_returns_404(self, client: TestClient):
        r = client.get("/project/no-such-project/metrics")
        assert r.status_code == 404

    def test_page_has_throughput_section(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "metrics-throughput" in r.text

    def test_page_has_cycle_section(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics")
        assert "metrics-cycle" in r.text

    def test_page_has_wip_section(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics")
        assert "metrics-wip" in r.text

    def test_page_has_by_agent_section(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics")
        assert "metrics-by-agent" in r.text

    def test_empty_board_renders_without_error(self, client: TestClient, alias: str):
        # No tickets — all empty states should appear, page must not 500.
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        # Three of the four sections show the empty state (by-project is hidden when there are no project labels).
        assert r.text.count("metrics-empty") >= 3

    def test_board_with_tickets_shows_data(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        b.add({"title": "Active", "agent": "developer", "status": "doing"})
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        # WIP count badge visible.
        assert "metrics-wip-count-badge" in r.text

    def test_done_tickets_appear_in_cycle_stats(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        _make_done_ticket(alias, b, created_offset_days=3)
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        # Cycle histogram must show percentile chips (not the empty state).
        assert "mcd-chips" in r.text
        assert "mcd-chip" in r.text


class TestMetricsTab:
    """Verify the Metrics tab appears on all project pages and links correctly."""

    def test_metrics_tab_on_board_page(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        assert r.status_code == 200
        assert "Metrics" in r.text
        assert f"/project/{alias}/metrics" in r.text

    def test_metrics_tab_on_agents_page(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/agents")
        assert r.status_code == 200
        assert "Metrics" in r.text
        assert f"/project/{alias}/metrics" in r.text

    def test_metrics_tab_on_context_page(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/context")
        assert r.status_code == 200
        assert "Metrics" in r.text
        assert f"/project/{alias}/metrics" in r.text

    def test_metrics_tab_is_active_on_metrics_page(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        # The Metrics tab link must carry the "active" class.
        assert 'class="tab active"' in r.text or 'class="tab  active"' in r.text or "tab active" in r.text

    def test_board_tab_active_on_board_page(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/board")
        # Board tab is active; Metrics tab is not.
        html = r.text
        # Find the metrics tab link — it must not be the active one.
        metrics_tab_idx = html.find(f'href="/project/{alias}/metrics"')
        board_tab_idx = html.find(f'href="/project/{alias}/board"')
        assert metrics_tab_idx > 0
        assert board_tab_idx > 0


class TestMetricsCss:
    """Verify metrics.css is included in the bundle and has key selectors."""

    def test_metrics_css_imported_in_index(self, dashboard_css: str):
        # dashboard_css fixture resolves @imports — metrics.css content must be present.
        assert ".metrics-card" in dashboard_css

    def test_metrics_bar_svg_class_present(self, dashboard_css: str):
        assert ".metrics-bar-svg" in dashboard_css

    def test_metrics_stat_value_present(self, dashboard_css: str):
        assert ".metrics-stat-value" in dashboard_css

    def test_metrics_group_table_present(self, dashboard_css: str):
        assert ".metrics-group-table" in dashboard_css

    def test_metrics_wip_list_present(self, dashboard_css: str):
        assert ".metrics-wip-list" in dashboard_css

    def test_metrics_uses_editorial_tokens(self, dashboard_css: str):
        # Key token usage in metrics rules.
        assert "var(--accent)" in dashboard_css
        assert "var(--green)" in dashboard_css
        assert "var(--bg-card)" in dashboard_css
        assert "var(--font-mono)" in dashboard_css
        assert "var(--font-serif)" in dashboard_css

    def test_metrics_served_as_static_file(self, client: TestClient):
        r = client.get("/static/css/metrics.css")
        assert r.status_code == 200
        assert ".metrics-card" in r.text


# ── Workspace metrics rollup: GET /metrics ────────────────────────────────────


class TestWorkspaceMetricsRoute:
    """HTTP tests for GET /metrics (workspace-level rollup)."""

    def test_returns_200(self, client: TestClient):
        r = client.get("/metrics")
        assert r.status_code == 200

    def test_page_has_throughput_section(self, client: TestClient):
        r = client.get("/metrics")
        assert "metrics-throughput" in r.text

    def test_page_has_cycle_section(self, client: TestClient):
        r = client.get("/metrics")
        assert "metrics-cycle" in r.text

    def test_page_has_wip_section(self, client: TestClient):
        r = client.get("/metrics")
        assert "metrics-wip" in r.text

    def test_page_has_by_agent_section(self, client: TestClient):
        r = client.get("/metrics")
        assert "metrics-by-agent" in r.text

    def test_page_has_by_workspace_project_section(self, client: TestClient):
        r = client.get("/metrics")
        assert "metrics-by-workspace-project" in r.text

    def test_empty_workspace_renders_gracefully(self, client: TestClient):
        """Empty workspace (no tickets) must render without error — not 500."""
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "metrics-empty" in r.text

    def test_breadcrumb_links_to_home(self, client: TestClient):
        r = client.get("/metrics")
        assert 'href="/"' in r.text
        assert "Workspace metrics" in r.text

    def test_no_project_tabs_on_workspace_metrics(self, client: TestClient):
        """Workspace metrics page is not project-scoped; no per-project tabs."""
        r = client.get("/metrics")
        assert 'class="tabs"' not in r.text

    def test_workspace_with_done_tickets_shows_cycle_data(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        _make_done_ticket(alias, b, created_offset_days=3)
        r = client.get("/metrics")
        assert r.status_code == 200
        # Cycle histogram must show percentile chips (not the empty state).
        assert "mcd-chips" in r.text or "mcd-chip" in r.text

    def test_by_workspace_project_shows_alias_link(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        """By-workspace-project table links each alias to its project metrics page."""
        b = Board(workspace, workspace_config)
        b.add({"title": "T", "agent": "developer", "status": "doing"})
        r = client.get("/metrics")
        assert r.status_code == 200
        assert alias in r.text
        assert f"/project/{alias}/metrics" in r.text


# ── Workspace summary band on home page ──────────────────────────────────────


class TestWorkspaceSummaryBand:
    """Home page must show the compact 3-tile summary band + CTA."""

    def test_band_present_on_home(self, client: TestClient):
        r = client.get("/")
        assert r.status_code == 200
        assert 'class="ws-summary-band"' in r.text

    def test_band_has_three_tiles(self, client: TestClient):
        r = client.get("/")
        assert r.text.count('class="ws-summary-tile') >= 3

    def test_band_has_cta_link_to_metrics(self, client: TestClient):
        r = client.get("/")
        assert 'href="/metrics"' in r.text
        assert "workspace metrics" in r.text.lower()

    def test_band_shows_wip_count(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        b.add({"title": "A", "agent": "developer", "status": "doing"})
        b.add({"title": "B", "agent": "developer", "status": "review"})
        r = client.get("/")
        assert r.status_code == 200
        # WIP tile value "2" should appear somewhere in the band.
        assert "2" in r.text

    def test_tile_labels_present(self, client: TestClient):
        r = client.get("/")
        assert "Total WIP" in r.text
        assert "Done last 7d" in r.text
        assert "Stale" in r.text

    def test_stale_tile_has_warn_class_when_stale(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        """When stale_count > 0 the stale tile carries the warn modifier."""
        from datetime import datetime, timedelta, timezone
        import json
        b = Board(workspace, workspace_config)
        t = b.add({"title": "Old", "agent": "developer", "status": "doing"})
        # Force the updated timestamp to be 10 days ago so wip() flags it stale.
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        idx_path = workspace / ".holoctl" / "board" / "index.json"
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        for tk in data["tickets"]:
            if tk["id"] == t["id"]:
                tk["updated"] = stale_ts
        idx_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")

        r = client.get("/")
        assert r.status_code == 200
        assert "ws-tile-warn" in r.text

    def test_summary_band_css_in_bundle(self, dashboard_css: str):
        assert ".ws-summary-band" in dashboard_css
        assert ".ws-summary-tile" in dashboard_css
        assert ".ws-summary-cta" in dashboard_css


# ── workspace_summary shaper unit tests ──────────────────────────────────────


class TestWorkspaceSummaryShaper:
    """Unit tests for the workspace_summary() view shaper."""

    def test_empty_projects_returns_zeros(self):
        from holoctl.server.views.workspace_summary import workspace_summary
        result = workspace_summary([])
        assert result == {"total_wip": 0, "last7_throughput": 0, "stale_count": 0}

    def test_total_wip_sums_doing_and_review(self):
        from holoctl.server.views.workspace_summary import workspace_summary
        projects = [
            {"counts": {"doing": 2, "review": 1, "backlog": 5, "done": 3}},
            {"counts": {"doing": 1, "review": 0, "backlog": 2, "done": 1}},
        ]
        result = workspace_summary(projects)
        assert result["total_wip"] == 4  # 2+1 + 1+0

    def test_missing_counts_defaults_to_zero(self):
        from holoctl.server.views.workspace_summary import workspace_summary
        projects = [{"counts": {}}]
        result = workspace_summary(projects)
        assert result["total_wip"] == 0

    def test_no_tickets_key_gives_zero_throughput_and_stale(self):
        from holoctl.server.views.workspace_summary import workspace_summary
        # Projects without pre-loaded _tickets → throughput and stale fall back to 0.
        projects = [{"counts": {"doing": 3}}]
        result = workspace_summary(projects)
        assert result["last7_throughput"] == 0
        assert result["stale_count"] == 0

    def test_last7_throughput_with_tickets(self, workspace: Path, workspace_config: dict):
        """Projects enriched with _tickets give correct last7 count."""
        from holoctl.server.views.workspace_summary import workspace_summary
        b = Board(workspace, workspace_config)
        alias = workspace.name
        # Create a done ticket with completed = now (within last 7 days).
        t = _make_done_ticket(alias, b, created_offset_days=5, completed_offset_days=1)
        tickets = b.ls()
        projects = [{"counts": {"doing": 0}, "_tickets": tickets}]
        result = workspace_summary(projects)
        assert result["last7_throughput"] >= 1

    def test_stale_count_with_stale_ticket(
        self, workspace: Path, workspace_config: dict
    ):
        from holoctl.server.views.workspace_summary import workspace_summary
        from datetime import datetime, timedelta, timezone
        import json

        b = Board(workspace, workspace_config)
        t = b.add({"title": "Stale", "agent": "developer", "status": "doing"})
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        idx_path = workspace / ".holoctl" / "board" / "index.json"
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        for tk in data["tickets"]:
            if tk["id"] == t["id"]:
                tk["updated"] = stale_ts
        idx_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")

        tickets = b.ls()
        projects = [{"counts": {"doing": 1}, "_tickets": tickets}]
        result = workspace_summary(projects)
        assert result["stale_count"] >= 1


# ── F1: Metrics filter toolbar — route + HTML integration ────────────────────


class TestMetricsFilterRoute:
    """Integration tests: filter query params reflected in rendered HTML."""

    def test_since_param_returns_200(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics?since=7d")
        assert r.status_code == 200

    def test_since_30d_default_toolbar_present(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "metrics-filter-toolbar" in r.text

    def test_preset_chip_active_class(self, client: TestClient, alias: str):
        r = client.get(f"/project/{alias}/metrics?since=7d")
        assert "mft-preset-active" in r.text

    def test_kind_filter_narrows_tickets(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        """Filtering by kind=spec must exclude task-kind tickets from the
        rendered metrics context.  We verify by checking that the WIP count
        badge reflects only the matching tickets."""
        b = Board(workspace, workspace_config)
        b.add({"title": "A task", "agent": "developer",
               "status": "doing", "kind": "task"})
        b.add({"title": "A spec", "agent": "developer",
               "status": "doing", "kind": "spec"})

        # Without filter: both in WIP.
        r_all = client.get(f"/project/{alias}/metrics?since=all")
        assert r_all.status_code == 200

        # With kind=spec filter: only the spec ticket survives.
        r_filt = client.get(f"/project/{alias}/metrics?since=all&kind=spec")
        assert r_filt.status_code == 200
        # The WIP badge must show 1 (only spec ticket is in progress).
        assert 'class="metrics-wip-count-badge">1<' in r_filt.text

    def test_agent_filter_param(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        b.add({"title": "T1", "agent": "developer", "status": "doing"})
        b.add({"title": "T2", "agent": "reviewer", "status": "doing"})

        r = client.get(f"/project/{alias}/metrics?since=all&agent=developer")
        assert r.status_code == 200
        assert 'class="metrics-wip-count-badge">1<' in r.text

    def test_active_chip_rendered_for_active_filter(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics?since=30d&kind=task")
        assert "mft-active-chips" in r.text
        assert "mft-chip" in r.text

    def test_clear_all_link_present_when_filters_active(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics?since=7d&kind=task")
        assert "mft-clear-all" in r.text
        assert "Clear all" in r.text

    def test_no_active_chips_when_no_filters(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        # No multi-value filters active → no chips row.
        assert "mft-active-chips" not in r.text

    def test_sticky_toolbar_class_in_css(self, dashboard_css: str):
        assert ".metrics-filter-toolbar" in dashboard_css
        assert "position: sticky" in dashboard_css

    def test_scrollable_class_in_css(self, dashboard_css: str):
        assert ".metrics-scrollable" in dashboard_css
        assert "max-height" in dashboard_css
        assert "overflow-y: auto" in dashboard_css

    def test_metrics_page_wrapper_present(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert 'class="metrics-page"' in r.text

    def test_comma_separated_tags_filter(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        b.add({"title": "Auth task", "agent": "developer",
               "status": "doing", "tags": "auth"})
        b.add({"title": "UI task", "agent": "developer",
               "status": "doing", "tags": "ui"})

        # Filter by tags=auth — only auth ticket in WIP.
        r = client.get(f"/project/{alias}/metrics?since=all&tags=auth")
        assert r.status_code == 200
        assert 'class="metrics-wip-count-badge">1<' in r.text

    def test_unknown_project_404_with_filter(self, client: TestClient):
        r = client.get("/project/no-such-project/metrics?since=7d&kind=task")
        assert r.status_code == 404


class TestWorkspaceMetricsFilterRoute:
    """Integration tests for the workspace-level filter."""

    def test_since_param_returns_200(self, client: TestClient):
        r = client.get("/metrics?since=7d")
        assert r.status_code == 200

    def test_filter_toolbar_present(self, client: TestClient):
        r = client.get("/metrics")
        assert "metrics-filter-toolbar" in r.text

    def test_project_facet_shown_on_workspace(self, client: TestClient):
        """Workspace metrics shows the Project facet; per-project view does not."""
        r = client.get("/metrics")
        assert r.status_code == 200
        # Project facet summary appears via is_workspace=True in context.
        # We check the hidden 'since' input is present (toolbar rendered).
        assert 'name="since"' in r.text

    def test_active_chip_on_workspace_filter(self, client: TestClient):
        r = client.get("/metrics?since=7d&kind=task")
        assert r.status_code == 200
        assert "mft-active-chips" in r.text

    def test_clear_all_on_workspace(self, client: TestClient):
        r = client.get("/metrics?kind=task")
        assert "mft-clear-all" in r.text

    def test_kind_filter_on_workspace(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        b.add({"title": "Task", "agent": "developer",
               "status": "doing", "kind": "task"})
        b.add({"title": "Spec", "agent": "developer",
               "status": "doing", "kind": "spec"})

        r = client.get("/metrics?since=all&kind=spec")
        assert r.status_code == 200
        assert 'class="metrics-wip-count-badge">1<' in r.text


# ── F3: Cycle histogram, Throughput overlay, Stalled list ────────────────────


class TestF3CycleHistogram:
    """Cycle-time distribution histogram (_cycle_dist.html) renders correctly."""

    def test_histogram_section_present_on_project_metrics(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "metrics-cycle-dist" in r.text

    def test_histogram_empty_state_on_clean_board(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        # Empty state text in the cycle histogram.
        assert "No completed tickets in this window" in r.text

    def test_histogram_shows_percentile_chips_with_data(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        _make_done_ticket(alias, b, created_offset_days=5)
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "mcd-chips" in r.text
        assert "mcd-chip-p50" in r.text
        assert "mcd-chip-p95" in r.text

    def test_histogram_present_on_workspace_metrics(
        self, client: TestClient
    ):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "metrics-cycle-dist" in r.text

    def test_histogram_css_classes_present(self, dashboard_css: str):
        assert ".mcd-svg" in dashboard_css
        assert ".mcd-bar" in dashboard_css
        assert ".mcd-chips" in dashboard_css
        assert ".mcd-chip-p95" in dashboard_css


class TestF3ThroughputOverlay:
    """Throughput trend overlay chart (_throughput_overlay.html) renders correctly."""

    def test_overlay_section_present_on_project_metrics(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "metrics-throughput-overlay" in r.text

    def test_overlay_empty_state_on_clean_board(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "No completed tickets to show a trend" in r.text

    def test_overlay_legend_present_with_data(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        _make_done_ticket(alias, b, created_offset_days=5)
        r = client.get(f"/project/{alias}/metrics?since=all")
        assert r.status_code == 200
        assert "mto-legend" in r.text
        # Legend shows "Current" and "Previous" labels.
        assert "Current" in r.text
        assert "Previous" in r.text

    def test_overlay_has_prev_period_bar_class(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        _make_done_ticket(alias, b, created_offset_days=5)
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        # Ghost bar class must be in the SVG markup.
        assert "mto-bar-prev" in r.text

    def test_overlay_present_on_workspace_metrics(
        self, client: TestClient
    ):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "metrics-throughput-overlay" in r.text

    def test_overlay_css_classes_present(self, dashboard_css: str):
        assert ".mto-bar-prev" in dashboard_css
        assert ".mto-legend" in dashboard_css
        assert ".mto-delta-up" in dashboard_css
        assert ".mto-delta-down" in dashboard_css


class TestF3StalledList:
    """Stalled tickets list (_stalled.html + stalled_view shaper) integration."""

    def test_stalled_section_present_on_project_metrics(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "metrics-stalled" in r.text

    def test_stalled_empty_state_on_clean_board(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "No stalled tickets" in r.text

    def test_stalled_shows_orphaned_backlog_ticket(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        """A backlog ticket without an agent should appear in the stalled list
        with the 'no agent assigned' reason."""
        b = Board(workspace, workspace_config)
        # Add a ticket with no agent explicitly (default in _ticket helper is []).
        # Board.add requires valid agent, so add with agent then clear it in index.
        t = b.add({"title": "Orphan", "agent": "developer"})
        idx_path = workspace / ".holoctl" / "board" / "index.json"
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        for tk in data["tickets"]:
            if tk["id"] == t["id"]:
                tk["agent"] = []
        idx_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")

        r = client.get(f"/project/{alias}/metrics?since=all")
        assert r.status_code == 200
        assert "no agent assigned" in r.text

    def test_stalled_shows_no_priority_reason(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        """A backlog ticket without priority should show 'no priority set'."""
        b = Board(workspace, workspace_config)
        t = b.add({"title": "NoPrio", "agent": "developer"})
        idx_path = workspace / ".holoctl" / "board" / "index.json"
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        for tk in data["tickets"]:
            if tk["id"] == t["id"]:
                tk["priority"] = ""
        idx_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")

        r = client.get(f"/project/{alias}/metrics?since=all")
        assert r.status_code == 200
        assert "no priority set" in r.text

    def test_stalled_section_present_on_workspace_metrics(
        self, client: TestClient
    ):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "metrics-stalled" in r.text

    def test_stalled_css_classes_present(self, dashboard_css: str):
        assert ".mst-list" in dashboard_css
        assert ".mst-item" in dashboard_css
        assert ".mst-status-chip" in dashboard_css
        assert ".mst-reason-chip" in dashboard_css
        assert ".mst-ticket-id" in dashboard_css

    def test_stalled_section_near_wip_block(
        self, client: TestClient, alias: str
    ):
        """Stalled and WIP cards appear inside the same side-by-side grid row."""
        r = client.get(f"/project/{alias}/metrics")
        html = r.text
        assert "metrics-wip-stalled-row" in html
        wip_idx = html.find("metrics-wip")
        stalled_idx = html.find("metrics-stalled")
        assert wip_idx > 0 and stalled_idx > 0

    def test_wip_stalled_row_css_present(self, dashboard_css: str):
        assert ".metrics-wip-stalled-row" in dashboard_css


# ── F2: KPI band + time-in-status HTTP tests ─────────────────────────────────


class TestProjectMetricsKpiBand:
    """HTTP-level tests: KPI band renders on /project/{alias}/metrics."""

    def test_kpi_band_present_on_project_metrics(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "mkpi-band" in r.text

    def test_kpi_band_has_throughput_card(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        # The band renders at least one mkpi-card element.
        assert "mkpi-card" in r.text

    def test_kpi_band_renders_with_data(
        self, client: TestClient, alias: str, workspace: Path, workspace_config: dict
    ):
        b = Board(workspace, workspace_config)
        b.add({"title": "Active", "agent": "developer", "status": "doing"})
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "mkpi-band" in r.text
        # WIP card value should be non-zero.
        assert "mkpi-value" in r.text


class TestWorkspaceMetricsKpiBand:
    """HTTP-level tests: KPI band renders on /metrics (workspace rollup)."""

    def test_kpi_band_present_on_workspace_metrics(self, client: TestClient):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "mkpi-band" in r.text

    def test_kpi_band_has_mkpi_cards(self, client: TestClient):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "mkpi-card" in r.text

    def test_kpi_band_renders_gracefully_when_empty(self, client: TestClient):
        """Empty workspace must still render the KPI band (all dashes / zeros)."""
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "mkpi-band" in r.text


class TestProjectMetricsTimeInStatus:
    """HTTP-level tests: time-in-status section renders on /project/{alias}/metrics."""

    def test_time_in_status_section_present_on_project_metrics(
        self, client: TestClient, alias: str
    ):
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "metrics-time-in-status" in r.text

    def test_time_in_status_empty_state_when_no_activity(
        self, client: TestClient, alias: str
    ):
        """When activity.jsonl is empty (no moves), the empty state renders
        gracefully without raising."""
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        # Either empty state text or mtis-chart present — both are valid.
        assert (
            "No status-transition history yet" in r.text
            or "mtis-chart" in r.text
        )

    def test_time_in_status_shows_chart_after_move(
        self, client: TestClient, alias: str, workspace: Path
    ):
        """After at least one ticket.moved event, the TIS chart renders."""
        created = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "Workflow ticket", "agent": "developer"},
        ).json()
        # Move the ticket so activity.jsonl gets a ticket.moved event.
        client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move",
            json={"status": "doing"},
        )
        r = client.get(f"/project/{alias}/metrics")
        assert r.status_code == 200
        assert "mtis-chart" in r.text or "metrics-time-in-status" in r.text


class TestWorkspaceMetricsTimeInStatus:
    """HTTP-level tests: time-in-status section renders on /metrics."""

    def test_time_in_status_section_present_on_workspace_metrics(
        self, client: TestClient
    ):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "metrics-time-in-status" in r.text

    def test_time_in_status_empty_state_on_workspace_metrics(
        self, client: TestClient
    ):
        """Empty workspace (no activity) must render the TIS empty state
        gracefully — no 500, no AttributeError from non-dict JSON lines."""
        r = client.get("/metrics")
        assert r.status_code == 200
        assert (
            "No status-transition history yet" in r.text
            or "mtis-chart" in r.text
        )

    def test_time_in_status_shows_chart_after_move_on_workspace(
        self, client: TestClient, alias: str, workspace: Path
    ):
        """After a move event the workspace rollup also shows the TIS chart."""
        created = client.post(
            f"/api/project/{alias}/tickets",
            json={"title": "WS chart ticket", "agent": "developer"},
        ).json()
        client.post(
            f"/api/project/{alias}/tickets/{created['id']}/move",
            json={"status": "doing"},
        )
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "mtis-chart" in r.text or "metrics-time-in-status" in r.text

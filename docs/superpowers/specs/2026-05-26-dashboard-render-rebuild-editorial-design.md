# Dashboard render-layer rebuild + Editorial visual identity

- **Date:** 2026-05-26
- **Status:** Approved design (pending spec review)
- **Scope:** Sub-project 1 of a larger dashboard upgrade. Sub-project 2 ("command center") is out of scope here.

## Context

The web dashboard (`holoctl/server/`) is the heaviest visual surface of holoctl. A review for a planned upgrade surfaced two facts that shape this work:

1. **The Jinja migration is ~90% done in production, but stalled.** All main views — board (kanban/list/tree), ticket detail, and the SSE fragments — already render through `routes/ → views/ (presenters) → templates/`. The large string-built HTML helpers in `server/app.py` (which bloat it to 1462 lines) are **dead in production**: no route imports them. They survive only because `tests/test_dashboard.py` (~40 test methods) still asserts against their old string markup. That test coupling is the friction that stalled the migration.
2. **The visual identity is competent but generic.** The current `tokens.css` is a capable dark/light system (Outfit + JetBrains Mono, indigo accent, Apple-ish palette) — but it reads as the default "dark SaaS dashboard," with no identity of its own.

These two are best fixed **together**: finishing the migration means rewriting templates/CSS view-by-view, which is exactly the moment to apply a new visual identity. Doing them separately would mean touching the same HTML/CSS twice.

## Goals

- Replace the generic look with a distinctive **Editorial** identity across **all** dashboard surfaces.
- Finish the Jinja migration: delete the dead string-builders, shrink `app.py` to thin wiring, and remove the lazy-import smell between `app.py` and `views/`.
- Replace the hand-rolled markdown renderer with a real library.
- Keep behavior parity: no route, API, or SSE behavior regresses; the test suite stays green (re-pointed at rendered output).

## Non-goals (deferred to sub-project 2)

- New write actions / "command center" (running compile/curate/agent-add from the UI, fuller editing).
- Journal / memory / curator views.
- Multi-workspace dashboard, mobile-first rework, VS Code extension.

## Locked visual system

Decided during brainstorming (with mockups):

| Aspect | Decision |
|---|---|
| Direction | **Editorial / Clean** — premium, airy, "curated product" not "app" |
| Theme | **Light-first**, with a first-class **dark** (warm near-black, not the current cool gray). Keep the existing toggle. |
| Type — titles | **Fraunces** (modern serif) — page titles, card titles, section headers |
| Type — body/UI | **Inter** |
| Type — code/IDs | **JetBrains Mono** (kept) |
| Palette | Warm off-white canvas (`#f3f2ee`) / warm near-black dark; paired light+dark tokens |
| Accent | **Terracotta** (`#c2410c` family) — used only on action points (primary buttons, active view, p1/urgency), not as wallpaper |
| Density | Airy columns, generous card padding, hairline warm borders |

The accent and warm palette deliberately diverge from the blue/indigo norm of dev tools.

## Architecture: current state → target

### Dead string-builders (delete after tests are re-pointed)

In `server/app.py`, unreferenced by any route:

- `_kanban_html`, `_list_row_html`, `_list_html`, `_tree_html`
- `_board_page`, `_board_controls_html`
- `_ticket_detail_page` (+ its inline Properties/Linked/Activity string building)
- chip string helpers: `_repo_chip_html`, `_deps_chip_html`, `_kind_chip_html`, `_source_chip_html`, `_parent_chip_html`
- supporting constants only used by the above: `_SVG_ATTRS` / `_ICON_*` (verify against `templates/icons/` first), `_KIND_GLYPHS`, `_PROVIDER_GLYPHS`, and `_e` (Jinja `autoescape` replaces it)

### Live helpers (relocate, kill lazy imports)

Currently stranded in `app.py` and lazy-imported by `views/`/`routes/`:

- `_get_projects`, `_get_project`, `_list_workspace_compat`, `_PROJECTS_CACHE*` → new **`server/projects.py`**
- `_ticket_preview`, `_format_due` → fold into **`views/card.py`**
- `_read_ticket_activity` → fold into **`views/detail.py`**
- `_render_markdown`, `_strip_empty_sections` → new **`server/markdown.py`** (see below)
- `_not_found_html` → render the `partials/_empty_state.html` template directly at call sites (or a tiny helper in `server/projects.py`)

### Markdown

- Add **`markdown-it-py`** as an explicit dependency in `pyproject.toml` (it is currently only present transitively via `rich` — do not rely on that).
- New `server/markdown.py` wraps it; keep `_strip_empty_sections` as preprocessing.
- **Output markup will change** (markdown-it emits standard `<h1>/<ul>/<ol>/<table>/<a>`). Consequence: `static/css/markdown.css` must be reviewed against the new output, and detail/doc tests assert the new rendered structure. Fixes the current renderer's gaps (tables, links, nested lists, heading levels).

### `app.py` end state

Thin wiring only: app creation, static mount, router includes, the write API endpoints + SSE. Optionally extract the API endpoints (`/api/projects`, `/api/project/{alias}/board`, POST tickets, PATCH ticket, POST move, SSE `/events`) into **`routes/api.py`** so `app.py` is purely composition.

## Work order

The order matters — deleting before re-pointing tests breaks the suite.

1. **Re-point tests** (`tests/test_dashboard.py`): assert against rendered output instead of string-builders. Use `TestClient` for whole routes (`GET /project/{alias}/board`, `/board/{id}`) and direct `render("partials/board/_kanban.html", **ctx)` for fragments. Assert on **semantic markup** (presence of `data-*` attributes, ticket id/title, kind/source chips, tree nesting, empty states, HTML escaping) rather than exact strings — so future restyles don't break tests. Achieve coverage parity with every behavior the old helper-tests checked. (Red → green before any deletion.)
2. **Delete the dead string-builder cluster** and its orphan constants.
3. **Relocate the live helpers** into the modules above; remove the lazy imports.
4. **Swap the markdown renderer** to markdown-it-py as its own step; update `markdown.css` and the detail/doc tests; eyeball before/after on a few real ticket bodies.
5. **Editorial reskin**, surface by surface, on the existing templates:
   - Rewrite `tokens.css` (warm palette, paired light/dark, terracotta accent, type scale, Fraunces/Inter/JetBrains import).
   - Adjust component CSS (`card.css`, `kanban.css`, `list.css`, `tree.css`, `detail.css`, `home.css`, `context.css`, `agents.css`, `tabs.css`, `controls.css`, `buttons.css`, …) for editorial spacing + serif titles.
   - Minor template class tweaks where needed (e.g., a serif title class).
   - Surfaces: board (kanban/list/tree), detail, home, and the Repos / Agents / Commands / Context tabs.
6. **Verify both themes** on every surface.

Steps 1–4 (saneamento) and 5 (reskin) can overlap per-view, but within a view do structure-then-skin.

## Testing strategy

- `test_dashboard.py` re-pointed at rendered output (see step 1); both light and dark asserted where markup carries a `data-theme` hook.
- Existing route/API/SSE tests stay green unchanged (behavior parity).
- Markdown swap covered by detail/doc render tests against the new standard markup.
- `mypy` + `ruff` remain green (CI gates).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Deleting dead code breaks tests | Re-point tests first (step 1); deletion only after green. |
| Markdown output change ripples into CSS/tests | Isolated step (4) with before/after spot-check on real bodies. |
| Reskin regressions across themes | Per-surface light+dark verification (step 6). |
| Serif titles hurt density on small repeated cards | Validated in mockup; if it drags at real density, scope serif to page/section titles and keep card titles in Inter. |

## Open questions

None blocking. Card-title serif-vs-sans is the one thing to re-judge once it's live at real density (mitigation noted above).

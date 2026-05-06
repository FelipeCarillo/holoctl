# Changelog

All notable changes to holoctl follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.8.0] — 2026-05-06

### Added (board controls UI)

- **Filter / sort / group-by panel above the kanban.** A collapsible "Filter, sort & group" toggle exposes six filter dropdowns (status, priority, agent, sprint, tag, project), a sort dropdown (created asc/desc, updated desc, priority p0→p3, title A-Z, ID numeric) and a group-by dropdown (status default, priority, sprint, agent, tag). Group-by rebuilds the columns entirely — e.g. switching to "agent" gives one column per assigned persona; tickets with multiple values are cloned into each bucket they belong to.
- **State persists per workspace** via `localStorage` (`holoctl-bc:<alias>`). Refreshing or navigating away keeps the agent's view intact. The toggle auto-expands when any non-default filter / sort / group is active so the user sees what's filtering their view.
- **Live updates honor the active controls.** When SSE swaps the kanban DOM (PR #9 / #10 mechanic), the new cards are run back through `__reapplyBoardControls()` so an incoming ticket lands in the correct bucket and respects the active filter rather than appearing unfiltered for one cycle.
- All `kanban-card` elements now carry `data-id`, `data-status`, `data-p`, `data-agent`, `data-sprint`, `data-tags`, `data-projects`, `data-title`, `data-created`, `data-updated`. Filter/sort/group is fully client-side — no extra server round-trip.

## [0.7.1] — 2026-05-06

### Added (parallel decomposition)

- **`hctl board batch` — create N parallel-safe tickets in one call.** Takes a JSON object `{shared: {...}, tickets: [...]}`. Shared fields are merged into each ticket; per-ticket fields override. Atomic — if any invariant fails, no ticket is created.
- **Parallelism invariants enforced before creation:**
  - Each ticket must declare `files: list[str]` — the file paths it will touch.
  - No two tickets in the batch may share a file path (pre-flight overlap check). Forces the boardmaster to actually plan disjoint scopes.
  - No ticket may have a sibling-by-title in its `depends` (sibling deps mean serial execution; create those with `add` instead). External deps to already-existing IDs are fine.
  - Standard validators (`title`, `status`, `priority`, `agent`) run per ticket; first failure aborts the whole batch.
- **`files: list[str]`** — new optional field on `Board.add()` and serialized into ticket frontmatter. Used by the batch validator and useful for the developer agent to confirm `Start` matches reality.
- **`boardmaster` persona updated** with a "decomposing into a parallel-safe batch" section. Walks the agent through the invariants with a worked `hctl board batch` example, and tells it to retry on validation errors instead of falling back to raw `add` calls that would skip the checks.

## [0.7.0] — 2026-05-06

### Added (board agent + single-shot ticket creation)

- **New `boardmaster` agent persona.** `holoctl init` (and `holoctl sync --agents`) now plants `.holoctl/agents/boardmaster.md` alongside the existing developer / reviewer / architect / researcher. The persona owns the ticket lifecycle: creates tickets with full body content in a single CLI call, edits body via stdin, moves through statuses, never touches the .md files by hand. Refuses requests for code / review / architecture work and routes to the right specialist.
- **`Board.add()` accepts body content directly in the create patch.** No more two-pass "create then edit". The patch can include any of:
  - `goal: list[str]` — each item rendered as `- [ ] <text>` under `# Goal — Definition of Done`.
  - `start: str` / `context: str` / `outOfScope: str` / `executionNotes: str` — each rendered as a `# Section\n\n<text>` block. Empty / whitespace-only fields are silently dropped.
  - `body: str` — full markdown override. When set, the structured fields above are ignored.

  When no body fields are passed, `_create_ticket_md` falls back to the existing `_template.md` placeholders (backwards compatible).
- **New CLI: `hctl board body <ID>`.** Reads new body from stdin (`echo '...' | hctl board body PRJ-001`) or `--from-file path`. Replaces the body of the ticket .md while preserving frontmatter and bumping `updated:`. Logs `ticket.body_updated` in `activity.jsonl`. Replaces the previous workflow of opening the .md file in an editor and hand-editing.
- **`/ticket` slash command rewritten** to instruct the agent to pass body fields in the same `add` JSON, with worked examples covering the structured + raw-body forms.

### Changed (token economy)

- **`boardCli` default switched from `holoctl board` to `hctl board`.** `hctl` is the short alias of `holoctl` (both registered as entry points in `pyproject.toml`). Slash commands now use the shorter form by default — saves ~3 chars × dozens of CLI invocations per agent session, nontrivial token economy on long workflows. Existing workspaces with an explicit `boardCli` in their `config.json` are unaffected.
- All `holoctl <cmd>` references in `holoctl/templates/commands/holoctl-*.md` (the `/holoctl` bootstrap commands per AI tool) switched to `hctl <cmd>` for the same reason.

### Fixed (server)

- **SSE board updates were silently broken: required F5 to see new tickets.** PR #9 wired the kanban DOM swap on every `board-update` event, but the SSE handler emitted `data: {multi-line JSON}` directly. The SSE protocol treats every `\n` inside the data field as a record terminator, so the browser only saw `e.data === "{"`. The handler's deduplication check (`e.data === lastData`) then matched on every event and never fired the swap. Fix: compact the JSON to a single line via `json.dumps(json.loads(raw), separators=(",", ":"))` before yielding. Live updates now work.

### Fixed (dashboard layout)

- **Page-level scroll replaced with contained scroll regions.** Previously busy boards or long agent lists made the entire page scroll vertically, hiding the topbar and pushing the sidebar. Now: `body`, `.app`, `.main`, and `.content` all lock to the viewport (`height: 100vh; overflow: hidden`); a new `.content-body` wrapper inside `.content` is the scroll surface (`overflow-y: auto` for grids/lists, opted into a flex-column kanban layout for the board page via CSS `:has()`).
- **Each kanban column scrolls vertically on its own.** `.kanban-cards` now has `flex: 1; min-height: 0; overflow-y: auto`, so a column with 50 tickets scrolls inside the column instead of pushing the column past the viewport. Column headers stay pinned at the top of each column (`flex-shrink: 0`).
- **Horizontal scrollbar on the board lands at the visible viewport bottom.** `.kanban` now has `overflow-x: auto; overflow-y: hidden` and is itself the horizontal scroll container, so the bar sits at the bottom of the visible content area regardless of how tall the tallest column is. Replaces the previous behavior where the bar appeared below the last ticket card (often off-screen).
- `_render` wraps page content in `<div class="content-body">…</div>`. `.tabs` and `.content-wrap` are also flex-column constrained so they don't grow past the viewport.

### Added

- `GET /api/project/<alias>/board-html` returns just the kanban fragment as HTML, used by the SSE swap.
- **Strict input validation in `Board.add()` and `Board.set()`.** Agents writing tickets via slash commands frequently passed values like `priority: "high"` or `status: "todo"` — both used to silently land in the index, leading to broken board filters and confusing dashboard views. Now:
  - `title` must be non-empty (clear error otherwise, with a copy-pasteable example).
  - `status` must be one of `config.board.statuses`.
  - `priority` must be one of `config.board.priorities`.
  - `agent` must reference a defined persona under `.holoctl/agents/*.md`.
  - `Board.set()` now validates `priority` and `agent` (used to validate only `status`).
- Each rejection includes the list of valid values so the agent can retry without guessing.

### Changed (default behavior)

- **No more `git` subprocess by default, anywhere.** New config option `git.checkDirty` (default `false`) controls whether holoctl ever spawns `git status` / `git log`. When false, the dashboard Repos tab, `holoctl repo list`, `holoctl repo info`, and `holoctl overview` all run on the fast-path (`.git/` reads only) and the `dirty` flag + last-commit message/date are omitted from the output. Flip to `true` in `.holoctl/config.json` to restore the old behavior workspace-wide, or pass `--check-dirty` to any of the affected CLI commands for a single invocation.
- Off-by-default eliminates the last bit of git-subprocess latency on Windows + corporate AV setups. Pre-PR #6 a dashboard click cost 14 subprocesses; PR #6 dropped that to ~12 (only on the Repos tab); this PR drops it to **0** by default.

### Changed (schema)

- **Ticket timestamps are now full ISO 8601 UTC** (`2026-05-06T17:14:55Z`) instead of date-only (`2026-05-06`). Applies to `created`, `updated`, `completed`, and `meta.updated` in `index.json`. Old tickets with date-only values continue to parse correctly thanks to `datetime.fromisoformat` accepting both forms; on the next `set` / `move` / `rebuild-index` they get rewritten with full timestamps. The `overview` stalled-calc handles either format transparently.

### Changed (templates)

- **`/ticket` slash command rewritten.** Lists the exact valid statuses + priorities pulled from config. Hard requirement: ASK the user once (single batched question) for any missing required field instead of guessing. Optional sections (Start / Context / Out of scope) are explicitly marked optional and the agent is instructed to **omit** them when there's no real content — no more `(placeholder)` text in tickets.
- **`tickets/_template.md` cleaned up.** Sections now contain HTML comments as guidance instead of `(criterion 1)` / `(Why this exists)` placeholders. Header `# Goal — Definition of Done` is the only required section. Frontmatter shows the actual valid status / priority sets and indicates ISO 8601 UTC for timestamps.

### Fixed (dashboard)

- **Horizontal scroll on the board is contained inside the content area, not the whole page.** With multi-column kanbans the `.kanban` flex container grows past the viewport. The `.main` area is a flex child without `min-width: 0`, so it inherited that growth and pushed the body itself wider than the screen — the sidebar slid out of view when you scrolled. Added `min-width: 0` to `.main` so `overflow-x: auto` on `.content` actually does its job. Sidebar stays fixed; only the board scrolls.
- **Kanban now updates live without a page refresh.** SSE was already firing `board-update` events on every `index.json` mtime change but the JS handler only showed a toast. The handler now fetches a new `/api/project/<alias>/board-html` HTML fragment and atomically swaps the `<div id="kanban">` in place. New tickets, status moves, and ticket edits show up immediately. Falls back to the toast on fetch error and re-tries on the next event.
- **Kanban card left border no longer looks "bitten" at the corners.** Was caused by mixing a 1px border with a 3px `border-left` under `border-radius` — the rounded corners only honored the smaller width and clipped the colored bar. Replaced the border with a `::before` pseudo-element so the priority stripe lives inside the rounded card and renders cleanly when the card is at rest.
- **Dashboard ticket detail hides empty/placeholder sections.** Sections whose content is blank, only HTML comments, only parenthetical hints (`(some hint)`), or only placeholder checklist items (`- [ ] (criteria)`) are now stripped before render. Tickets that have only a meaningful Goal section show only Goal in the dashboard — matching the user's expectation that absent info isn't displayed.

## [0.6.0] — 2026-05-06

### Removed (breaking)

- **Node implementation removed.** The parallel Node mirror under `src/`, `bin/holoctl.js`, `scripts/`, `package.json`, and `package-lock.json` is gone. holoctl was never published to npm; the Node tree was a stale historical mirror that diverged from Python and doubled the maintenance cost. Python (PyPI) is the only implementation going forward. If you need the old JS entrypoint, check out tag `v0.5.1`.

### Added

- **`/holoctl` slash command is now actually emitted by `compile` for every target.** Previously only the (unpublished) Node tree wrote it for cursor/windsurf/copilot. Python now writes it for **claude / cursor / windsurf / copilot / devin** at compile time, loaded from `holoctl/templates/commands/holoctl-<target>.md` via `compiler.template.load_bootstrap()`.
- `compile_cursor` now writes to `.cursor/rules/holoctl.md` (modern Cursor rules format) instead of the legacy `.cursorrules`, plus `.cursor/commands/<name>.md` for every slash command and `.cursor/commands/holoctl.md` bootstrap. Matches the README "Pick your AI tool" table.
- `compile_windsurf` now writes `.windsurf/workflows/<name>.md` per command + `.windsurf/workflows/holoctl.md` bootstrap, alongside the existing `.windsurfrules`.
- `compile_copilot` now writes `.github/prompts/<name>.prompt.md` per command + `.github/prompts/holoctl.prompt.md` bootstrap, alongside the existing `.github/copilot-instructions.md`.
- `compile_devin` now writes a `.devin/skills/holoctl/SKILL.md` bootstrap.
- `holoctl sync` now refreshes `.holoctl/board/tickets/_template.md` (it was missing from `_SYNC_TARGETS`).

### Security

- **Stored XSS in dashboard.** Every page generator (`_home_page`, `_board_page`, `_agents_page`, `_commands_page`, `_context_page`, `_repos_page`, `_ticket_detail_page`, `_doc_detail_page`, `_sidebar`, `_topbar`, `_layout`) was interpolating user-controlled strings (project name, ticket title, agent description, sprint label, repo path) raw into HTML. Anyone able to write `.holoctl/config.json` or a ticket frontmatter could inject script that ran in the browser of anyone hitting the dashboard. Especially relevant under the documented `holoctl serve --host 0.0.0.0` LAN-exposure mode. All interpolations now go through a new `_e()` helper that calls `html.escape(value, quote=True)`.
- **Path traversal in agent and command detail routes.** `/project/<alias>/agents/<slug>` and `/project/<alias>/commands/<slug>` joined the URL `slug` parameter directly into a filesystem path with no containment check. Both routes now resolve to absolute paths and reject anything outside their respective `.holoctl/agents/` and `.holoctl/commands/` directories — same `Path.resolve()` + `relative_to()` pattern applied to the context route earlier.

### Fixed

- `holoctl repo list` now merges auto-discovered subprojects with manual overrides from `config.project.repos[]`, matching the README/CHANGELOG 0.5.0 promise. Previously it only listed manual entries — same bug 0.5.1 fixed for `overview`.
- `holoctl doctor` `_TARGET_OUTPUTS` now matches what each compiler actually writes, so doctor stops false-flagging targets as broken right after `holoctl compile`.
- `__version__` fallback in `holoctl/__init__.py` bumped from `"0.3.0"` to a current value; only used when `importlib.metadata` can't read package metadata.
- Path-traversal hardening in the dashboard's `/project/<alias>/context/<filename>` route — uses `Path.resolve()` + `relative_to()` instead of stripping `..` from the raw filename (which `....//` could escape).
- Removed the orphaned `/project/<alias>/files` route, `/api/.../files` endpoint, and `_files_page()` helper. The Files tab was officially removed in 0.4.2 — only dead code remained in the FastAPI server.
- Dropped stale reference to `holoctl setup-global` (removed in 0.5.0) from the `/holoctl` Claude bootstrap template.

## [0.5.1] — 2026-05-05

### Fixed

- `holoctl overview` now actually lists discovered subprojects under the **📁 Projects** section. The 0.5.0 release shipped with stale code that read `config.project.repos` (manual list) instead of calling `discover_repos`, so the section was always empty in real workspaces.
- Web dashboard ticket detail page replaces the old `Scope` field with `Projects` (array), matching the schema migration.

## [0.5.0] — 2026-05-05

### Changed

- **Renamed package to `holoctl`** (was `projctl` on npm and `projhub` on PyPI). New CLI binaries: `holoctl` and the short alias `hctl`. Folder marker is now `.holoctl/`. Existing `.projctl/` and `.projhub/` directories are auto-renamed to `.holoctl/` on first read.
- **Workspace = the directory where `holoctl init` was run.** No more global registry of projects in `$HOME` and no more global slash-command installer. `holoctl init` writes only inside the workspace; `~/.holoctl/`, `~/.projctl/`, `~/.projhub/` are never touched.
- **Auto-discovery of subprojects.** Every command (overview, board, dashboard) scans the workspace's direct subdirectories for project markers (`.git`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `composer.json`, `Gemfile`, `pubspec.yaml`, `mix.exs`, `build.gradle`, `pom.xml`, `CMakeLists.txt`) and surfaces matches as projects — no `repo add` required. Skip-list excludes `node_modules`, `.venv`, `dist`, `build`, etc.
- **Tickets now reference one or more projects.** New field `projects: string[]` replaces the old `scope: string`. CLI: `--project <name>` filter on `board ls`; create with `'{"projects":["app","api"]}'`. Legacy tickets with `scope: X` are read as `projects: [X]` automatically on first reindex.

### Removed

- `holoctl setup-global` command and its associated `npm postinstall` hook. The `/holoctl` slash command is now generated **per workspace** by `holoctl compile --target claude` (writes `.claude/commands/holoctl.md` inside the workspace).
- `holoctl workspace` subcommands (`add`/`list`/`remove`) and the `~/.holoctl/workspace.json` global registry.

### Migration

- Existing projects with `.projctl/` or `.projhub/` keep working — the directory is auto-renamed to `.holoctl/` on the next read of config.
- Existing tickets with `scope: X` keep working — they're served as `projects: [X]` and rewritten with the new field on the next index rebuild or set.
- Users who relied on a global `/holoctl` slash command should run `holoctl compile --target claude` once per workspace to wire it up locally.

## [0.4.4] — 2026-05-05

### Added
- **Devin CLI compile target.** `holoctl compile --target devin` writes:
  - `AGENTS.md` at the project root (Devin's primary always-active rules file, equivalent to `CLAUDE.md`).
  - `.devin/skills/<name>/SKILL.md` per slash command, with YAML frontmatter (`name`, `description`, `arguments`). Devin invokes them as `/<name>`.
- **`holoctl overview` command.** One-screen project snapshot: name, prefix, version, objective, board counts (backlog/doing/review/done/cancelled), repos with branch + dirty + ticket count, agents, slash commands, dashboard URL, and a context-aware suggested next action (stalled tickets, next p1, or "create your first").
- The `/holoctl` slash command now ends every invocation with `holoctl overview` so the user sees the canonical snapshot — same template applied to claude/cursor/windsurf/copilot/devin variants.
- `holoctl doctor` recognises the `devin` target and verifies that `AGENTS.md` and `.devin/skills` exist when devin is in `config.targets`.

## [0.4.3] — 2026-05-05

### Fixed
- **No more dark→light theme flash on navigation.** Inline boot script in `<head>` reads `localStorage` and applies the theme + sidebar state to `<html>` before the first paint. Previously the server hardcoded `data-theme="dark"`, so every navigation flashed dark even when the user had picked light.
- **Sidebar collapsed view now usable.** Each nav item gained a small avatar (project prefix initials, ★ for Agents) that stays visible when collapsed; theme + collapse buttons stack vertically; brand shrinks to just the "P" logo. Width 64px.

### Changed
- **`/holoctl` slash command: execute by default, ask only at 3 checkpoints.** The previous version paused after every context file, which was friction for the simple case. Now the agent reads the codebase and writes `objective.md`, `architecture.md`, `conventions.md`, `instructions.md` directly. It only stops to ask the user when (a) `.holoctl/` already exists (conflict), (b) sub-repos are detected (one aggregated question listing all candidates, not one per repo), or (c) the codebase is genuinely ambiguous and the objective can't be inferred from the README. Same flow applied to cursor/windsurf/copilot variants.

## [0.4.2] — 2026-05-05

### Fixed
- **UI bugs in the web dashboard**:
  - Theme toggle and sidebar collapse buttons: SVG icons were missing `width`/`height`/`stroke` attributes and were therefore invisible. Now ship with `width="16" height="16" stroke="currentColor"` baked in.
  - Theme toggle no longer rotates on hover (the rotation was applied to the menu button too, which felt buggy). Hover now changes background only.
  - Command/agent/context detail pages: when there's no metadata sidebar, the page no longer renders with a broken `grid-template-columns` inline style that made the whole content area look "dark".
- **Performance**: when many repos are registered, the dashboard called `git status` per repo on every request. Added a 5-second in-memory cache for the project list (the SSE board updates still feel live).

### Changed
- Removed the **Files** tab from the project view. The dashboard now focuses on tickets, agents, commands, context, and repos.
- `/holoctl` slash command rewritten to be **interactive** with confirmation gates. The previous version asked the agent to "populate context files" but didn't enforce checkpoints, so agents skipped repos and wrote thin/wrong content. The new version requires the agent to:
  1. Ask the user for project name + prefix before init.
  2. Read the codebase first (read-only).
  3. Propose each context file (`objective.md`, `architecture.md`, `conventions.md`, `instructions.md`) **one at a time**, show the draft, wait for approval/edits, then write.
  4. Propose sub-repos to register and ask which to keep.
  5. Recompile.

  Same flow applied to the Cursor / Windsurf / Copilot variants.

## [0.4.1] — 2026-05-05

### Fixed
- Web dashboard: clicking an agent / command / context document no longer 404s. Added detail routes `/project/{alias}/agents/{slug}`, `/.../commands/{slug}`, `/.../context/{filename}` that render the file contents as Markdown.

### Changed
- `/holoctl` slash command rewritten. Previously it just ran `holoctl init` and stopped — leaving `objective.md`, `architecture.md`, `conventions.md`, and `instructions.md` as bare placeholders. Now it instructs the agent to actually read the codebase (README, package files, top-level dirs, lint configs) and POPULATE those files with real content; register sub-repos when multi-package; then recompile. Same change applied to the Cursor / Windsurf / Copilot variants.

## [0.4.0] — 2026-05-05

### Changed (breaking)
- **`holoctl serve` now binds to `127.0.0.1` by default** (was `0.0.0.0`). Use `--host 0.0.0.0` to expose on the network — a warning is printed when you do.
- **`setup-global` simplified to install only the Claude Code slash command.** Cursor / Windsurf / Copilot don't support globally-installed slash commands; their previous paths (`~/.codeium/.../memories/`, `~/.copilot/prompts/`) didn't exist on disk. Use `holoctl compile` per-project for those tools.

### Changed
- `holoctl init` now auto-runs `compile` for every configured target and `setup-global` for Claude Code. Use `--skip-compile` / `--skip-global` to opt out.

### Added
- `holoctl doctor` now detects drift between `tickets/*.md` and `index.json`, verifies that compile targets are up to date, and flags a stale global slash command.
- Web dashboard renders ticket Markdown bodies (headings, checklists, lists, inline code).
- Sidebar in the web dashboard is collapsible with persistent state.
- Theme toggle (dark/light) persists across reloads.

### Fixed
- `Board.set()` validates the field name and status transition, and survives values that look like JSON arrays.
- `Board._patch_ticket_md` serialises lists to comma-separated YAML (was writing Python `repr`).
- Agent templates: dropped references to non-existent agents (`mock-data-curator`, `qa`); unified `trigger: ticket` across agents.
- All web dashboard tabs use the correct CSS class names — agents, commands, context, repos and ticket detail render properly.

## [0.3.0] — 2026-05-05

### Changed
- **Renamed package from `projctl`/`projhub` to `holoctl`.** PyPI distribution now lives at <https://pypi.org/project/holoctl>.
- **Migrated from Node.js to Python + uv.** Install via `uv tool install holoctl`. The CLI binary is now `holoctl` (with `hctl` as a shorter alias).
- Web dashboard rebuilt on FastAPI + Uvicorn (was Hono).

### Fixed
- Windows: `sys.stdout.reconfigure(encoding="utf-8")` so Rich can render `✓` / `✗` characters on `cp1252` consoles.

[0.8.0]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.8.0
[0.7.1]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.7.1
[0.7.0]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.7.0
[0.6.0]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.6.0
[0.5.1]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.5.1
[0.5.0]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.5.0
[0.4.4]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.4
[0.4.3]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.3
[0.4.2]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.2
[0.4.1]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.1
[0.4.0]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.0
[0.3.0]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.3.0

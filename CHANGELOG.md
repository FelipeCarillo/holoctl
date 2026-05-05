# Changelog

All notable changes to projhub follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.4.3] — 2026-05-05

### Fixed
- **No more dark→light theme flash on navigation.** Inline boot script in `<head>` reads `localStorage` and applies the theme + sidebar state to `<html>` before the first paint. Previously the server hardcoded `data-theme="dark"`, so every navigation flashed dark even when the user had picked light.
- **Sidebar collapsed view now usable.** Each nav item gained a small avatar (project prefix initials, ★ for Agents) that stays visible when collapsed; theme + collapse buttons stack vertically; brand shrinks to just the "P" logo. Width 64px.

### Changed
- **`/projhub` slash command: execute by default, ask only at 3 checkpoints.** The previous version paused after every context file, which was friction for the simple case. Now the agent reads the codebase and writes `objective.md`, `architecture.md`, `conventions.md`, `instructions.md` directly. It only stops to ask the user when (a) `.projhub/` already exists (conflict), (b) sub-repos are detected (one aggregated question listing all candidates, not one per repo), or (c) the codebase is genuinely ambiguous and the objective can't be inferred from the README. Same flow applied to cursor/windsurf/copilot variants.

## [0.4.2] — 2026-05-05

### Fixed
- **UI bugs in the web dashboard**:
  - Theme toggle and sidebar collapse buttons: SVG icons were missing `width`/`height`/`stroke` attributes and were therefore invisible. Now ship with `width="16" height="16" stroke="currentColor"` baked in.
  - Theme toggle no longer rotates on hover (the rotation was applied to the menu button too, which felt buggy). Hover now changes background only.
  - Command/agent/context detail pages: when there's no metadata sidebar, the page no longer renders with a broken `grid-template-columns` inline style that made the whole content area look "dark".
- **Performance**: when many repos are registered, the dashboard called `git status` per repo on every request. Added a 5-second in-memory cache for the project list (the SSE board updates still feel live).

### Changed
- Removed the **Files** tab from the project view. The dashboard now focuses on tickets, agents, commands, context, and repos.
- `/projhub` slash command rewritten to be **interactive** with confirmation gates. The previous version asked the agent to "populate context files" but didn't enforce checkpoints, so agents skipped repos and wrote thin/wrong content. The new version requires the agent to:
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
- `/projhub` slash command rewritten. Previously it just ran `projhub init` and stopped — leaving `objective.md`, `architecture.md`, `conventions.md`, and `instructions.md` as bare placeholders. Now it instructs the agent to actually read the codebase (README, package files, top-level dirs, lint configs) and POPULATE those files with real content; register sub-repos when multi-package; then recompile. Same change applied to the Cursor / Windsurf / Copilot variants.

## [0.4.0] — 2026-05-05

### Changed (breaking)
- **`projhub serve` now binds to `127.0.0.1` by default** (was `0.0.0.0`). Use `--host 0.0.0.0` to expose on the network — a warning is printed when you do.
- **`setup-global` simplified to install only the Claude Code slash command.** Cursor / Windsurf / Copilot don't support globally-installed slash commands; their previous paths (`~/.codeium/.../memories/`, `~/.copilot/prompts/`) didn't exist on disk. Use `projhub compile` per-project for those tools.

### Changed
- `projhub init` now auto-runs `compile` for every configured target and `setup-global` for Claude Code. Use `--skip-compile` / `--skip-global` to opt out.

### Added
- `projhub doctor` now detects drift between `tickets/*.md` and `index.json`, verifies that compile targets are up to date, and flags a stale global slash command.
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
- **Renamed package from `projctl` to `projhub`.** PyPI distribution now lives at <https://pypi.org/project/projhub>.
- **Migrated from Node.js to Python + uv.** Install via `uv tool install projhub`. The CLI binary is now `projhub` (with `phub` as a shorter alias).
- Web dashboard rebuilt on FastAPI + Uvicorn (was Hono).

### Fixed
- Windows: `sys.stdout.reconfigure(encoding="utf-8")` so Rich can render `✓` / `✗` characters on `cp1252` consoles.

[0.4.3]: https://github.com/FelipeCarillo/projhub/releases/tag/v0.4.3
[0.4.2]: https://github.com/FelipeCarillo/projhub/releases/tag/v0.4.2
[0.4.1]: https://github.com/FelipeCarillo/projhub/releases/tag/v0.4.1
[0.4.0]: https://github.com/FelipeCarillo/projhub/releases/tag/v0.4.0
[0.3.0]: https://github.com/FelipeCarillo/projhub/releases/tag/v0.3.0

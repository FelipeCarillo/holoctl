# Changelog

All notable changes to projhub follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

[0.4.0]: https://github.com/FelipeCarillo/projhub/releases/tag/v0.4.0
[0.3.0]: https://github.com/FelipeCarillo/projhub/releases/tag/v0.3.0

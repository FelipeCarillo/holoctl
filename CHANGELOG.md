# Changelog

All notable changes to projhub follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] — 2026-05-05

### Changed
- **Renamed package from `projctl` to `projhub`.** PyPI distribution now lives at <https://pypi.org/project/projhub>.
- **Migrated from Node.js to Python + uv.** Install via `uv tool install projhub`. The CLI binary is now `projhub` (with `phub` as a shorter alias).
- Web dashboard rebuilt on FastAPI + Uvicorn (was Hono).
- `projhub serve` now binds to `127.0.0.1` by default. Use `--host 0.0.0.0` to expose on the network.
- `setup-global` simplified to install only the Claude Code slash command. Cursor / Windsurf / Copilot integrations are now per-project via `projhub compile`.
- `projhub init` now auto-runs `compile` and `setup-global` (Claude). Use `--skip-compile` / `--skip-global` to opt out.

### Added
- `projhub doctor` now detects index/disk drift and stale global slash command versions, and verifies that compile targets are up to date.
- Web dashboard renders ticket Markdown bodies (headings, checklists, lists, inline code).
- Sidebar in the web dashboard is collapsible with persistent state.
- Theme toggle (dark/light) persists across reloads.

### Fixed
- `Board.set()` now validates the field name and status transition, and survives values that look like JSON arrays.
- `Board._patch_ticket_md` correctly serialises lists to comma-separated YAML (was writing Python `repr`).
- Windows: `sys.stdout.reconfigure(encoding="utf-8")` so Rich can render `✓` / `✗` characters on `cp1252` consoles.
- All web dashboard tabs now use the correct CSS class names — agents, commands, context, repos and ticket detail render properly.

[0.3.0]: https://github.com/FelipeCarillo/projhub/releases/tag/v0.3.0

# Changelog

All notable changes to holoctl follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Removed (breaking)

- **Node implementation removed.** The parallel Node mirror under `src/`, `bin/holoctl.js`, `scripts/`, `package.json`, and `package-lock.json` is gone. holoctl was never published to npm; the Node tree was a stale historical mirror that diverged from Python and doubled the maintenance cost. Python (PyPI) is the only implementation going forward. If you need the old JS entrypoint, check out tag `v0.5.1`.

### Added

- **`/holoctl` slash command is now actually emitted by `compile` for every target.** Previously only the (unpublished) Node tree wrote it for cursor/windsurf/copilot. Python now writes it for **claude / cursor / windsurf / copilot / devin** at compile time, loaded from `holoctl/templates/commands/holoctl-<target>.md` via `compiler.template.load_bootstrap()`.
- `compile_cursor` now writes to `.cursor/rules/holoctl.md` (modern Cursor rules format) instead of the legacy `.cursorrules`, plus `.cursor/commands/<name>.md` for every slash command and `.cursor/commands/holoctl.md` bootstrap. Matches the README "Pick your AI tool" table.
- `compile_windsurf` now writes `.windsurf/workflows/<name>.md` per command + `.windsurf/workflows/holoctl.md` bootstrap, alongside the existing `.windsurfrules`.
- `compile_copilot` now writes `.github/prompts/<name>.prompt.md` per command + `.github/prompts/holoctl.prompt.md` bootstrap, alongside the existing `.github/copilot-instructions.md`.
- `compile_devin` now writes a `.devin/skills/holoctl/SKILL.md` bootstrap.
- `holoctl sync` now refreshes `.holoctl/board/tickets/_template.md` (it was missing from `_SYNC_TARGETS`).

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

[0.4.4]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.4
[0.4.3]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.3
[0.4.2]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.2
[0.4.1]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.1
[0.4.0]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.4.0
[0.3.0]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.3.0

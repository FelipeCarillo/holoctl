# Changelog

All notable changes to holoctl follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.22.0] — 2026-06-15

### Added

- **Live spec authoring ("plano vivo no board")** — a `kind=spec` ticket body now works as a live plan document: the agent authors it from chat while the user watches the dashboard detail page update in real time; approval and status changes stay in chat (`board_move`).
  - New MCP write tools: `holoctl.board_set_body` (full body replace — skeleton/restructure) and `holoctl.board_update_section` (replace/append one `# H1` section — the token-efficient default for live authoring). Both recalculate DoD checkbox counts and are listed under `permissions.ask` in the compiled Claude settings.
  - Mermaid diagrams: ```` ```mermaid ```` fences render as SVG in the dashboard. Server side emits `<pre class="mermaid">` with the source HTML-escaped (the `html:False` XSS control extends to this path); client side lazy-loads a vendored `mermaid.min.js` (UMD v11, ~3.2MB added to the wheel — fetched only when a page actually contains a diagram) with `securityLevel:'strict'`.
  - Ticket detail page live-updates over the existing SSE stream: header, description and activity rail swap in place (≤2s after an edit, "Plan updated" toast), diagrams re-render after the swap, and an active inline edit defers the swap. New fragment endpoint `GET /api/project/{alias}/board/{ticket_id}/detail-html`.
  - `holoctl-spec-flow` skill + `/spec` command rewritten for the flow: materialize the spec **early** → ensure `hctl serve` is up and hand the user the live URL → update only changed sections per discussion milestone → `review` gate with verbal approval in chat → decompose via boardmaster. Includes an authoring-efficiency guide (section-level edits, telegraphic prose, ≤15-node mermaid recipes).

## [0.21.0] — 2026-06-10

Code-review follow-up release (PR #48): board integrity under concurrent
writers, a dashboard XSS fix, frontend repairs, compiler strictness with
escape hatches, DX tooling — and the dashboard now ships with the base
install.

### Security

- **Markdown XSS in ticket bodies fixed** — the dashboard's markdown parser is built with `html: False`, so raw HTML from untrusted ticket bodies (e.g. `/spec` imports) is escaped instead of rendered (`<img onerror=...>` no longer executes). Normal markdown (headings, lists, tables, code, task lists) renders unchanged. Frontend hardening to match: shared `esc()` on every dynamic `innerHTML`, toasts via `textContent`.

### Added

- **Bulk move endpoint** — `POST /api/project/{alias}/tickets/bulk-move` (`{ids, status}` → per-id results; 200 on partial failure, mirroring the MCP `batch_move` contract).
- Denormalized `acceptance_total`/`acceptance_done` per ticket in `index.json` (transparent backfill — child DoD progress no longer re-reads every `.md`).
- Strict-template escape hatches: `${{ ... }}` (GitHub Actions / shell templating) passes through untouched; `\{{...}}` emits literal braces.
- Foreign-assistant drift guard: the `holoctl-foreign-bootstrap` skill records generated-file hashes in `.holoctl/.foreign-compiled.json` and warns before overwriting hand-edits.
- DX tooling: `pytest-xdist` (`-n auto`), `pytest-cov`, `pytest-timeout`; ESLint flat config as a **blocking** CI job (pinned major); `scripts/validate_changelog.py` keeps pyproject ↔ CHANGELOG in sync in CI; shared `seed_workspace`/`cli_runner` fixtures.

### Changed

- **The dashboard now installs with the base package** — `pip install holoctl` brings the full web stack; no `holoctl[dashboard]` extra to remember. The extra is kept as an empty no-op so existing `pip install 'holoctl[dashboard]'` instructions keep working. The web stack remains a lazy import: CLI/MCP cold-start still never loads fastapi/uvicorn/jinja2 (guarded by `test_cli_import_does_not_pull_web_stack`); `hctl serve` no longer needs (or prints) an install hint.
- **Compile resolves templates in strict mode** — an unresolved `{{placeholder}}` (typo or stray prose) now fails the compile with an actionable error naming the key, instead of leaking literal braces into generated files. Use the escape hatches above for intentional literals; a present-but-null config key gets its own message.
- Incremental compile: unchanged outputs are not rewritten (stable mtimes, no git churn); `/holoctl` + `/hctl-upgrade` bootstraps are ledger-tracked (doctor/prune manage them); `SYNC_TARGETS` is derived from `get_templates()` so the sync list can't drift.
- SSE stream: file I/O off the event loop (`asyncio.to_thread`), stat-first polls (idle ticks cost one `stat()`), 32-connection hard cap with a TOCTOU-free counter (503 when saturated), `: keepalive` every ~25s.
- `__version__` comes solely from `importlib.metadata` (fallback `0.0.0+unknown`) — no hardcoded version string to drift.

### Fixed

- **Board concurrency** — every load→mutate→save holds a cross-process lock (sidecar `index.json.lock`) and `_save` is atomic (temp file + `os.replace`): concurrent CLI × MCP × dashboard writers no longer last-write-wins. Mutators work on a deep copy, so readers never observe half-applied state; transient Windows `PermissionError` (sharing violations) is retried on both the writer and reader sides; a lock-acquisition timeout now logs a warning instead of degrading silently.
- Frontmatter patches go through parse→mutate→serialize (no more per-field regex that could clobber body lines); values with colons, quotes, and commas round-trip correctly.
- Three broken dashboard flows — kanban "+ Add ticket", bulk move/archive, inline detail edits — repaired by extracting shared `api.js`/`dom.js`/`util.js`/`popover.js` modules (the cross-module `ReferenceError`s are gone, and ESLint now guards them).
- Dashboard UX/a11y: popover focus management + arrow-key navigation, toast `role="status"`, in-place updates instead of forced reloads, selection survives SSE board swaps, `prefers-color-scheme` honored, stagger/grouping selector bugs fixed; dead `project-filter.js` removed.
- Curator rule failures are logged (no longer swallowed); `_deep_merge` is pure; `HOLOCTL_LOCK_TIMEOUT` env var tunes lock acquisition.

## [0.20.4] — 2026-05-28

Doc + help refresh: bring README and a few stale `--help` strings in
line with what holoctl has actually been since 0.20.0 (Claude-only
compiler, dashboard with a Metrics tab, expandable Context tree).
No behavior changes.

### Changed

- `hctl setup-global --target` now defaults to `claude` (was `all`,
  which only ever resolved to `claude` after the 0.20.0 collapse).
  `--target all` is still accepted as a backward-compatible alias.
- `hctl setup` docstring no longer implies it plants the skill in
  every assistant — since 0.20.0 it's effectively Claude-only; the
  others self-configure via the `holoctl-foreign-bootstrap` skill.

### Docs

- README (EN + pt-BR): dashboard tabs list now includes **Metrics**
  (added in 0.20.0) and notes that Context is an expandable tree.
- README (EN + pt-BR): refreshed stale `v0.17` / `0.14` version
  references — install verifier hint, persona library line, MCP
  preference note, `holoctlVersion` example, `handoff --note` example.

## [0.20.3] — 2026-05-28

UTF-8 hygiene pass: accented titles (and any non-ASCII text) now survive
end-to-end without mojibake on Windows + without ASCII escapes anywhere
the raw JSON is surfaced.

### Fixed

- **`json.dumps` was escaping every non-ASCII codepoint to `\uXXXX`** in
  the on-disk board index, the SSE `board-update` stream, the
  `activity.jsonl` log, workspace config, curator state, and every CLI
  command that prints JSON (`hctl board get/ls/move/set`,
  `hctl agent suggest`, `hctl journal show`). Functional — `json.loads`
  decodes it back — but the bytes were unreadable in `cat`, `git diff`,
  DevTools Network panel, and anything that surfaces the raw payload
  without re-parsing. Now `ensure_ascii=False` everywhere user-authored
  text can land. Adds a regression test that an accented title round-trips
  as literal UTF-8 through `index.json`. The index is rewritten on the
  next mutation, so existing workspaces self-heal on first ticket change.
- **`subprocess` on Windows decoded git output as cp1252.**
  `subprocess.run(..., text=True)` without `encoding` falls back to
  `locale.getpreferredencoding()`, so accented branch names, commit
  messages, and filenames came back as mojibake in the dashboard Repos
  tab and in `hctl handoff`'s changed-files preview. Pinned to
  `encoding="utf-8", errors="replace"` in both call sites
  (`lib/git.py`, `cli/handoff.py`).

## [0.20.2] — 2026-05-28

Two follow-ups to the 0.20.1 UI patch:

### Fixed

- **Metrics page crashed on naive timestamps.** `_parse_ts` in
  `holoctl/lib/metrics.py` returned a tz-naive `datetime` when the input ISO
  string had no `Z` / no `+offset` suffix. Comparing that against the
  tz-aware `now` later in the pipeline raised
  `TypeError: can't compare offset-naive and offset-aware datetimes`,
  breaking `cycle_time`, `wip`, `throughput`, and the stalled view on any
  workspace with externally-imported tickets (`Board._now()` itself always
  emits Z, so it didn't show up in fresh workspaces). Defensive fix: bare
  ISO timestamps are now assumed UTC and returned tz-aware. Mirrors the
  identical fix applied to `holoctl/server/filters.py` in 0.20.0.
- **Doc-detail pages (`/agents/{slug}`, `/commands/{slug}`,
  `/context/{file}`) now horizontally center.** `.detail-page` had
  `max-width: 960px` but no `margin-inline: auto`, so on wide screens the
  card hugged the left edge instead of sitting in the middle. The ticket
  detail (`[data-detail-page] { max-width: none }`) is unaffected — the
  auto-margin is a no-op when content fills the available width.

## [0.20.1] — 2026-05-28

Dashboard UI patch: the left-edge "sliver clip" that 0.20.0 fixed only on
detail pages was still happening on every other page (home, agents,
commands, context, repos, metrics, workspace metrics). Same root cause —
`.content-body { overflow-x: hidden }` clipped the cards' left
`box-shadow`. Same fix, now applied globally. Also adds consistent
horizontal centering for non-board pages so wide screens don't sprawl.

### Fixed

- **Global clip protection.** `padding-inline: 4px` now lives on the base
  `.content-body` rule (`holoctl/server/static/css/main.css`), giving every
  card's left box-shadow the same breathing room the detail pages got in
  0.20.0. The board page (`.content-body:has(> .kanban)`) inherits the
  padding without affecting its horizontal scroll; the detail pages already
  have their own `.detail-page { padding-inline: 4px }` and stay unchanged.

### Added

- **`.page-shell` centering wrapper** (`max-width: 1200px; margin-inline:
  auto`) on non-board page templates — `home.html`,
  `project/{agents,commands,context,repos,metrics}.html`, and `metrics.html`
  (workspace). Content frames consistently and stops sprawling edge-to-edge
  on wide displays. `project/board.html` is intentionally NOT wrapped
  (kanban needs full width for horizontal scroll); `detail.html` /
  `doc_detail.html` are NOT wrapped (`.detail-page` already constrains them).

### Internal

- **CI smoke test** updated to drop references to `copilot` / `codex`
  compile targets (retired in 0.20.0). The `release.yml` workflow was
  unaffected — this just unbreaks the regular `ci.yml` smoke step on main.

## [0.20.0] — 2026-05-28

0.20.0 is the largest single release since 0.17 — a Claude-only compiler refocus,
a full Editorial dashboard redesign, manifest-based compilation, a strategic
productivity-metrics page, and a suite of control-plane capabilities that turn
holoctl into a central management hub for the `.claude/` ecosystem.

### Removed — `copilot` + `codex` compile targets (breaking)

- **`holoctl/lib/compiler/copilot.py`** deleted — `.github/copilot-instructions.md`, `.github/prompts/<name>.prompt.md`, `.github/instructions/holoctl-memory-*.instructions.md`, `.copilot/config.json`, and `.vscode/mcp.json` are no longer emitted.
- **`holoctl/lib/compiler/codex.py`** deleted — `.codex/AGENTS.override.md` and `.codex/config.toml` are no longer emitted.
- **Shared emitters pruned**: `mcp_emit.emit_copilot` / `emit_codex` (+ the TOML merge helpers), `memory_emit.emit_copilot`, and the already-dead `hooks_emit.emit_copilot` removed.
- **Bootstrap command templates** `holoctl-copilot.prompt.md` and `hctl-upgrade-copilot.prompt.md` deleted from `holoctl/templates/commands/`.
- **`hctl setup-global`** ships an installer only for Claude now — the `copilot` target (the `~/.copilot/AGENTS.md` block) is gone; `--target all` resolves to just `claude`.
- **Migration is silent**: `lib/config.py:load_config` filters `copilot` / `codex` (alongside `cursor` / `windsurf` / `devin` / `generic`) out of any workspace's `targets` array on load. Already-materialized `.github/`, `.codex/`, `.vscode/`, `.copilot/` directories from earlier compiles are **not** auto-deleted — remove them by hand if you want.

### Changed — manifest replaces generated-by header (breaking)

- **`.holoctl/.compiled.json`** is now the sole ownership mechanism. The
  `<!-- Generated by holoctl -->` header is gone; compiled files are emitted
  clean. Ownership is hash-based: `CompileLedger` (in `holoctl/lib/manifest.py`)
  tracks every output by SHA-256 hash, detects hand-edits, and prunes orphans
  safely on the next compile. Any downstream consumer that relied on the header
  to identify holoctl-generated files must switch to checking the manifest.
- **`prune_orphans` dual-channel ownership**: the pruner tries the byte-channel
  hash as a fallback when the text-channel hash misses (supports files written via
  `write_bytes()` on Windows where `read_text()` translates line endings).
- `hctl compile` now reports `migrated` count on first run (legacy headered files
  are adopted into the manifest cleanly).

### Added — productivity metrics dashboard

The headline addition of 0.20.0. A full strategic-grade metrics surface ships
across two routes and a new pure-function library module.

- **`holoctl/lib/metrics.py`** — stdlib-only pure functions (all accept injected
  `now`): `throughput`, `cycle_time`, `wip`, `by_group`, `trend`,
  `cycle_time_distribution`, `time_in_status` (reads `activity.jsonl`),
  `flow_efficiency`, `forecast`, `read_activity_events`. Zero I/O except
  `read_activity_events`.
- **Per-project `/project/{alias}/metrics`** tab and **workspace `/metrics`**
  rollup. Home page gains a compact 3-tile summary band (Total WIP / Done last
  7d / Stale) with a CTA linking to `/metrics`. Cross-project breakdown table on
  the workspace page links each alias to its per-project tab.
- **Executive KPI band**: throughput Δ% vs previous period, cycle-time p50/p95,
  WIP count, flow efficiency %, stale count, simple weekly forecast.
- **Time-in-status chart** (SVG): reads `ticket.moved` events from
  `activity.jsonl`; surfaces bottleneck stages and flow signal.
- **Cycle-time distribution histogram** (inline SVG, 10 bins) with p50/p75/p95
  percentile chips and a graceful empty state.
- **Throughput overlay chart**: current-period solid bars overlaid with
  previous-period ghost bars; legend with totals and delta arrow chip. Auto-switches
  to weekly buckets when `since_days > 180` so large ranges stay readable.
- **Stalled-tickets list**: actionable list of aging/orphaned/missing-metadata
  tickets (active stale > 5d, backlog no-agent, backlog no-priority, done without
  `completed` timestamp); sorted by age desc; scrollable when > 12 items.
- **Complete filter toolbar** (`holoctl/server/filters.py`): date presets (7d /
  30d / 90d / Sprint / All) + custom ISO range; per-field multi-select facets
  (Tags, Kind, Status, Agent, Project, Sprint, Priority); URL-driven state; active
  chips with × remove and Clear all; sticky toolbar with backdrop-blur.
- **Layout/scroll**: WIP aging, by-agent, by-project, and stalled lists all get
  internal scroll (`.metrics-scrollable`, max-height 360px) when > 12 items so
  large boards don't blow out the page.

### Added — `hctl adopt`: bring foreign config under management

- **`hctl adopt`** brings externally-authored Claude config (agents, skills,
  commands not tracked by the manifest) under holoctl management. No args previews
  and adopts nothing; `--all` adopts everything; `--type {agent,skill,command}`
  (optionally `--name <x>`) adopts selectively. Foreign MCP servers are reported as
  external (not adoptable). Non-interactive.
- Adoption copies the `.claude/` file into `.holoctl/` source (reverse-mapping
  Claude `tools`/`model` frontmatter for agents) and records the current file in
  the manifest. The next `hctl compile` regenerates from `.holoctl/` instead of
  treating the file as foreign. Adoption never auto-compiles.
- New `holoctl/lib/ecosystem.py:scan_unmanaged(root)` — single classifier for what
  is foreign, shared by `doctor`, `adopt`, and the dashboard badges.
- New `manifest.add_entries(root, new_entries, *, holoctl_version)` merges adoption
  records into the manifest.

### Added — skills first-class manifest citizens

- **Built-in skill override**: a `SKILL.md` in `.holoctl/skills/<name>/` now
  explicitly shadows the matching built-in; on compile the built-in is skipped
  entirely and the user's version lands at the same `.claude/skills/<name>/SKILL.md`
  path.
- **Manifest-tracked support files**: `references/`, `scripts/`, and `templates/`
  subdirs under both built-in and custom skills are synced per-file through the
  `CompileLedger` (individually owned, hand-edit-guarded, pruned on removal).
  User-added files under `.claude/skills/<name>/` that holoctl never generated are
  preserved as foreign — never pruned.

### Added — portable `holoctl-foreign-bootstrap` skill

- **`holoctl/templates/skills/holoctl-foreign-bootstrap/`** (SKILL.md +
  `references/format-hints.md`). Compiled into `.claude/skills/` and also emitted
  (frontmatter stripped, hints inlined) at **`.holoctl/foreign-bootstrap.md`** — a
  tool-neutral path any non-Claude assistant can read. Carries per-tool format hints
  (Copilot / Codex / Cursor / generic) so a foreign assistant can materialise its
  own config dir from `.holoctl/`.

### Added — managed-vs-foreign dashboard badges

- The per-project `/agents` and `/commands` pages surface **foreign** items (in
  `.claude/` but NOT tracked by the manifest) with a subtle amber **"foreign"**
  badge and a tooltip pointing to `hctl adopt`. Badge detection is suppressed when
  `.holoctl/.compiled.json` does not exist (no false positives on pre-manifest
  workspaces).
- New `.foreign-badge` CSS class in `agents.css` using `--yellow`/`--yellow-subtle`
  editorial tokens.

### Added — context expandable directory tree

- The **Context tab** now renders an expandable directory tree. Directories expand
  lazily via `GET /api/project/{alias}/context/tree?path=<subpath>` (returns one
  listing level as `{entries: [{name, type}]}`; 403 on traversal, 404 on unknown
  alias or non-directory path). Files link to their detail view; nested children
  show a faint vertical guide line.
- `filetree.js` generalised with `data-tree-endpoint` / `data-file-href-base`
  configuration; attaches to both `#file-tree` and `#context-tree`.
- Editorial reskin of the Context tab: card-chrome `.context-panel`, inline SVG
  folder/doc/chevron icons replacing emoji, full-row hover, accent colour on open
  folders, lazy-state pulses.
- `read_context_dir` wraps per-file reads in try/except (`OSError`,
  `UnicodeDecodeError`) so a single unreadable `.md` never 500s the endpoint.

### Added — `hctl doctor` MCP health + ecosystem awareness

- **MCP health section**: checks whether `hctl` is on PATH and whether the holoctl
  MCP server is registered in `.mcp.json` / `.claude/settings.json:mcpServers`.
- **Ecosystem awareness section**: reports managed-vs-foreign agents, skills,
  commands, and MCP servers using `ecosystem.scan_unmanaged` (single classifier,
  shared with `adopt` and the dashboard badges).

### Added — `hctl provider` MCP-server awareness

- `hctl provider list/add/doctor` now read `.mcp.json` and
  `.claude/settings.json:mcpServers` to surface which providers have a connected
  MCP server, in addition to the declarative catalog.

### Added — `agents` target changed to discovery shim

- **`AGENTS.md` is now minimal.** It states the project is holoctl-managed, points
  Claude at `.claude/`, and points every other assistant at
  `.holoctl/foreign-bootstrap.md`. Objective / architecture / conventions /
  build-commands are no longer mirrored. Hand-edit guard and `--compile-drift` still
  apply.
- `hctl coverage` / `hctl doctor` matrices collapsed to the two live targets
  (`agents`, `claude`).
- README / `ARCHITECTURE.md` / `CONTRIBUTING.md` reframed from "multi-assistant
  compiler" to "Claude-first, with a portable bootstrap for the rest."

### Added — server refactor: Jinja templates + modular routes

- **`holoctl/server/markdown.py`**: `markdown-it-py` renderer module (replaces the
  old inline `_render_markdown` string-builder). `markdown-it-py` and
  `mdit-py-plugins` added as locked dependencies.
- **`app.py` thinned to ~180 lines**: all string-building HTML helpers removed;
  routes extracted into `routes/` modules; views extracted into `views/` modules.
  `app.py` is now thin wiring: FastAPI app, static mount, router includes, and
  SSE/API endpoints only.
- **`holoctl/server/projects.py`**: project listing, foreign-agent/command helpers,
  and context-tree reader extracted from `app.py` and `project_doc.py`.
- **`holoctl/server/paths.py`**: `safe_resolve` traversal guard extracted as a
  shared utility, used by context tree and doc detail routes.
- Board filter controls now support **Kind** and **Source** filters alongside the
  existing status/priority/agent/sprint/tag set; group-by parity across list and
  kanban views. Popover scroll fixed.
- Meta tabs (agents, commands, context, repos) gain **live search + scroll** via
  `meta-search.js`; doc-detail 500 (title-clash bug) fixed.
- Agents list survives agents with null/empty `tools` frontmatter (no longer
  crashes the page).

### Added — board integrity: `ticket.moved` activity log

- `Board.move()`, `Board.set(status)`, and `Board.batch_move()` all route through
  one shared helper. `ticket.moved` is appended to `activity.jsonl` **after**
  `_save()` + `_patch_ticket_md()` complete — eliminating the phantom-move window
  on process death.
- `completed` is reliably set on `done`-status transitions and cleared when leaving
  `done`. Activity timestamps use `isoformat(timespec="seconds")` to match
  `updated`/`completed` field precision.

### Added — Editorial dashboard redesign

- **Token system overhaul** (`tokens.css`): warm palette, terracotta `--accent`
  (`--terracotta`), rich dark background (`--bg-page` near-black), distinct
  card/rail/hover layers. Full dark and light theme support.
- **Typography**: Fraunces (serif, display headings), Inter (sans-serif, body/UI),
  JetBrains Mono (monospace, code/IDs). Loaded via `<link rel="preconnect">` in
  `_boot.html`.
- **Board + detail surfaces** (`card.css`, `kanban.css`, `detail.css`,
  `markdown.css`, `chips.css`, `list.css`, `tree.css`): refined card chrome, richer
  markdown rendering (code blocks, tables, blockquotes), editorial chip styles,
  editorial list rows, tree indentation.
- **Home, secondary tabs, and shell** (`home.css`, `agents.css`, `context.css`,
  `tabs.css`, `main.css`, `scope.css`): hero band, tab underline indicators,
  consistent surface/border tokens throughout.

### Fixed — detail-page card box-shadow clipping

- Detail pages (ticket and doc detail) clipped a sliver of each card's left
  box-shadow. Root cause: `.detail-main` / `.detail-rail` set `overflow-y: auto`
  (which computes `overflow-x` to `auto`) with no left padding, and doc detail
  scrolled inside `.content-body { overflow-x: hidden }`. Fix: `padding-inline` on
  `.detail-page` and scroll containers. Also defined the previously-undefined
  `--content-px` token (referenced by `scope.css` + `filetree.css`).

### Fixed — context tree accessibility and security

- Context tree "Loading…" pulse animation wrapped in
  `prefers-reduced-motion: no-preference` media query, consistent with
  `accessibility.css` policy.
- Filetree DOM HTML-escapes all user-controlled values (`e.name`, `entryPath`,
  badge labels) via a new `esc()` helper; file href segments are
  `encodeURIComponent`-encoded — defense-in-depth for names with `&`, `<`, `>`,
  or spaces.
- Lazy-expand nesting depth fixed: `data-depth` stored on every `.tree-lazy` div;
  toggle handler reads parent depth and passes `parentDepth+1` to
  `renderTreeEntries` so indentation grows correctly with nesting.

## [0.19.0] — 2026-05-27

Post-0.18 audit: correctness + drift fixes (Phase A) plus structural
hardening (Phase B). The headline is a set of **previously-broken Claude
hooks** that now work; the hand-edit guard now protects every target; and
the web dashboard moved to an optional extra so the core install stays lean.

### Changed (packaging — action may be needed)

- **The dashboard (`hctl serve`) moved to an optional `[dashboard]` extra.** `fastapi`, `uvicorn`, and `jinja2` are no longer core dependencies, so a CLI/MCP-only install (the common case) no longer pulls the web stack (fastapi → pydantic → starlette). Install the dashboard with `pip install 'holoctl[dashboard]'` (or `uv tool install 'holoctl[dashboard]'`); `hctl serve` prints this hint and exits non-zero if the extra is absent. The CLI, board, compile, and MCP server (`hctl serve --mcp`) are unaffected. A guard test locks the invariant that importing the CLI never pulls the web stack.

### Fixed

- **Claude hooks were broken on every session.** The compiled `.claude/settings.json` invoked two flags that don't exist: the `Stop` hook ran `handoff --quiet --auto` and the `PreToolUse` hook ran `journal record … --deny-glob …`, both of which made typer exit with a usage error. Switched to the real generalist commands (`handoff --quiet`, `journal record write_attempt … --quiet`); direct writes to derived state were already blocked by `permissions.deny`, so `--deny-glob` was redundant on top of being invalid. New guard `test_hooks_emit.py::test_hook_commands_are_valid_cli_invocations` runs each baked hook command and fails on any usage error.
- **Hooks + MCP config baked a machine-specific absolute path.** `_resolve_hctl_bin()` (in `compiler/hooks_emit.py` and `compiler/mcp_emit.py`) resolved `shutil.which("hctl")`, so a committed `.claude/settings.json` / `.vscode/mcp.json` / `.codex/config.toml` broke the moment it was used on another machine, user, or assistant. Now emits the portable `hctl` command (PATH-resolved); set `HOLOCTL_BIN` to override.
- **Recompile clobbered hand-edited target files.** The header-aware hand-edit guard that protected `CLAUDE.md` now also protects `AGENTS.md`, `.github/copilot-instructions.md`, and `.codex/AGENTS.override.md`: a hand-edited copy (no holoctl header) is preserved instead of overwritten, and `--force` still overwrites. Previously only the Claude target honored this — the others wrote blindly, contradicting the "never overwrite hand-edited configs" rule holoctl itself ships.
- **`/spec` and `/agent-new` went stale after upgrades.** The sync allow-list was duplicated across `cli/sync_.py`, `cli/init_.py`, and `cli/upgrade_.py`, and all three copies omitted `spec.md` and `agent-new.md` — so the two flagship 0.17 commands were seeded once at `init` but never refreshed. The list is now a single shared constant, `lib/templates.SYNC_TARGETS`, that includes them (guarded by `test_sync_targets.py`).
- **`hctl coverage` pointed at the wrong Codex path.** The matrix mapped `instructions.md` → codex `.codex/AGENTS.md` and MCP → `~/.codex/config.toml (user-level)`, while the compiler emits `.codex/AGENTS.override.md` and a project-level `.codex/config.toml`. Corrected, and `test_target_consistency.py` now validates `_COVERAGE`'s concrete path *values* against the files compilers actually emit (it previously checked only the column set).
- **MCP server replied to JSON-RPC notifications.** `server/mcp.py` returned an error response for any unknown method, including notifications (no `id`) — a protocol violation. Unknown notifications now return nothing, and a `ping` keep-alive handler was added.
- **`board_set` / `board_batch_set` via MCP crashed on non-string values.** A JSON client sending `value: ["a","b"]` (or a bool/null) hit `_parse_set_value` doing `value.startswith(...)` on a non-string. The MCP layer now coerces non-strings with `json.dumps`, which maps exactly onto the literals Board already understands (`null` / `true` / `[json,array]`), so array/bool/null values round-trip correctly.
- **The board activity log appended without a lock.** `.holoctl/activity.jsonl` (board mutations, read by the dashboard) was a plain append while the journal used OS-level locking — a corruption risk under concurrent assistants. Both now share `lib.jsonl.append_jsonl_line` (fcntl/msvcrt). The two logs stay separate on purpose (different schema + consumer); only the lock is shared.

### Added

- **`hctl doctor --compile-drift`.** Detects compiled outputs (`CLAUDE.md`, `AGENTS.md`, …) that are stale vs their `.holoctl/` source — i.e. you edited the source but forgot to recompile. It compiles into a throwaway copy of the workspace and byte-compares each generated file; hand-edited outputs (no holoctl header) are reported as such, not as drift, and merge-based configs (`settings.json` / `mcp.json` / `config.toml`) are skipped. Exits non-zero when anything is stale; the first output line (`holoctl: compile-drift` / `ok`) is router-friendly.
- **Codex parity — memory + personas in `.codex/AGENTS.override.md`.** Codex has no skills/subagent/lazy-memory surface like Claude's `.claude/` tree, so it previously got strictly less context. The override now inlines the always-on memory index + a list of lazy topics (read on demand from `.holoctl/memory/topics/`) and a summary of the active personas. Sections are omitted when their source is absent (empty in → empty out), and the output stays idempotent.
- **Linting + type-checking in CI (`ruff` + `mypy`).** A focused pyflakes + bugbear ruff set (`[tool.ruff]`, ignoring typer's required call-in-default pattern) plus a lenient mypy pass over the core (`holoctl/lib`, `holoctl/cli`) both run in CI. Existing dead-code / bad-f-string smells were cleaned up, two redundant `except (..., Exception)` handlers collapsed, and ~14 real type gaps fixed (including the `board_set` crash above). The FastAPI dashboard is intentionally out of mypy scope (dynamically typed, reachable only via a lazy import).

### Changed

- **`lib/board.py` decomposition (internal, no behavior change).** The 1000-LOC god-module shed two distinct responsibilities into focused, independently-testable modules: ASCII tree rendering → `lib/board_tree.py` (`render_tree`, a pure function), and ticket-body assembly → `lib/board_body.py` (`build_body`). `Board.tree` is now a thin wrapper. Covered by new `test_board_tree.py` plus the existing board suite.
- **MCP stdio conformance test.** `test_mcp_stdio.py` drives the real `hctl serve --mcp` subprocess through a full initialize → list → call → ping handshake and asserts notifications get no response line (the in-process tests couldn't cover the cold-start stdio loop).
- **Docs/drift sweep.** `ARCHITECTURE.md` corrected (it claimed `setup-global` was removed and that nothing is written to `$HOME`, and its layout / compile-pipeline / ticket-body / static-asset sections were stale); the generated `AGENTS.md` no longer cites the retired `.cursor/rules/`; stale docstrings (`memory.py`, `journal.py`, `server/mcp.py`) and MCP tool descriptions ("stubbed in 0.13") refreshed; `hctl coverage` help + glyphs no longer reference retired targets; `CONTRIBUTING.md` points at the new shared `SYNC_TARGETS`.

## [0.18.0] — 2026-05-18

Target slimdown + first-class Codex support. Holoctl now ships four
compile targets instead of seven: the long tail (cursor / windsurf /
devin / generic) is retired, and `codex` is added on top of the
existing claude / copilot / agents set. Workspaces still listing the
retired targets in `config.json:targets[]` continue to compile cleanly
— a silent migration filter strips the unknown names before the
dispatcher sees them.

### Removed — supported targets reduced to claude / copilot / codex / agents (breaking)

- **`cursor` compile target** — `holoctl/lib/compiler/cursor.py` deleted; emitters for `.cursor/rules/`, `.cursor/commands/`, `.cursor/hooks.json`, `.cursor/mcp.json` removed from `hooks_emit` / `mcp_emit` / `memory_emit`.
- **`windsurf` compile target** — `holoctl/lib/compiler/windsurf.py` deleted; `.windsurfrules`, `.windsurf/workflows/`, `.windsurf/rules/`, `.windsurf/hooks.json`, `.windsurf/mcp.json` no longer emitted. Companion curator rule `windsurf_memory_promote` retired.
- **`devin` compile target** — `holoctl/lib/compiler/devin.py` deleted; `.devin/agents/`, `.devin/skills/`, `.devin/rules/`, `.devin/hooks.v1.json`, `.devin/mcp.json` no longer emitted. `hctl setup-global --target devin` removed.
- **`generic` compile target** — `holoctl/lib/compiler/generic.py` deleted. It emitted a parallel `AGENTS.md` / `COMMANDS.md` / `AI-INSTRUCTIONS.md` that conflicted with the canonical `agents` target. The `agents` target is the universal AGENTS.md path for any tool that doesn't have a dedicated compiler.
- **Bootstrap command templates retired**: `holoctl-{cursor,windsurf,devin}.md` and `hctl-upgrade-{cursor,windsurf,devin}.md` deleted from `holoctl/templates/commands/`. `holoctl/templates/hooks/cursor_hooks.json` deleted.
- **Migration is silent**: `lib/config.py:load_config` now filters `cursor` / `windsurf` / `devin` / `generic` out of any workspace's `targets` array on load. Existing workspaces don't break — the next `hctl compile` just emits the remaining targets. Materialized `.cursor/`, `.windsurf/`, `.devin/` directories from earlier compiles are **not** auto-deleted — remove them manually if you want.

### Added — `codex` compile target

- **`holoctl/lib/compiler/codex.py`** — emits `.codex/AGENTS.override.md` (compiled from `instructions.md`; Codex merges this on top of the root `AGENTS.md` per its precedence spec) and `.codex/config.toml` with `[mcp_servers.holoctl]` so Codex auto-spawns the holoctl stdio MCP server when the project is trusted.
- **`mcp_emit.emit_codex`** — tolerant line-based TOML merge that preserves user's other `[mcp_servers.X]` tables and config sections.
- Coverage matrix (`hctl coverage`), doctor checks (`hctl doctor`), and per-target docs in README updated.

### Removed (previous Unreleased entries, retained)

- **Timeline board view** — the roadmap-style horizontal view (sprint/agent lanes, day/week/month/quarter zoom) was retired. Sub-controls conflicted with the global controls strip and the value didn't justify the maintenance cost. Tickets still carry `created` / `completed` data attributes that any future view can reuse. URL `?view=timeline` now falls back to kanban.

### Fixed

- **Board controls in list + tree** — `group` now reorganizes list buckets by any axis (status / priority / sprint / agent / tag), not just status. `search` and `filter` now reach tree rows. Sort + Group selects are hidden in tree (where they don't apply).

### Changed

- **Timestamps in the dashboard** are now rendered in the browser-host's local timezone with seconds (`YYYY-MM-DD HH:MM:SS`). Storage and the API contract are unchanged — every timestamp on disk and on the wire stays UTC ISO 8601.
- **`instructions.md` template** (source of `CLAUDE.md`) updated to surface `/agent-new`, the provider catalog (`hctl provider`), and the MCP-first behavior of `/spec` (was already present in the slash command, now also in boot context).
- **`holoctl-router` skill** updated with rows for `/agent-new` and `hctl provider`, plus a tiebreak rule clarifying that `holoctl-provider-mcp` runs before `holoctl-spec-flow` whenever a URL is pasted.

## [0.17.0] — 2026-05-16

Two complementary capabilities built on top of v0.16: provider MCP discovery
(when the user connects an external-board MCP in Claude Code, holoctl uses it
automatically), and proactive specialized persona creation (library expansion
+ AI-designed personas tailored to the specific repo).

### Added — provider MCP discovery (M16)

- **`config.providers` catalog** — declarative entries describing which URL patterns map to which MCP tool names. Shipped defaults for **Linear, GitHub, Trello, Azure DevOps, Jira, Slack** (best-guess tool names; user overrides per workspace when wrong). Additive on load: workspaces from v0.16 get the defaults automatically.
- **`hctl provider {list,add,enable,disable,test,remove}`** — manage the catalog. `provider add` accepts `--mcp-fetch` and `--url-pattern` for **custom providers** (e.g. an internal company board's MCP).
- **`mcp__holoctl__config_show`** read MCP tool — returns the resolved config, used by skills to read the provider catalog without parsing the file.
- **`holoctl-provider-mcp` SKILL** — auto-trigger when user pastes an external-board URL or refs a card. Reads catalog, matches URL pattern, probes the configured MCP fetch tool; uses it when available, falls back to paste cleanly when not.
- **Integration with `/spec` + `holoctl-work-item-router`** — both now delegate URL fetching to `holoctl-provider-mcp` instead of asking for paste first.

### Added — proactive specialized personas (M17)

- **Library expansion** with 4 curated personas:
  - **`dba`** — schemas, migrations, query optimization (paths: `**/*.sql`, `**/migrations/**`, `**/schema.prisma`, …)
  - **`devops`** — CI/CD, IaC, k8s, containers (paths: `**/.github/workflows/**`, `**/Dockerfile*`, `**/terraform/**`, `**/k8s/**`, …)
  - **`security-auditor`** — audit, threats, CVE review (description-triggered, no `paths:` — fires on prompts like "audit", "vulnerability", "is this safe?")
  - **`tech-writer`** — docs, READMEs, CHANGELOGs (paths: `**/docs/**`, `**/*.md`, …; model: fast)
- **`agent-designer`** — new reasoning-tier persona whose job is **to design other personas**. Reads the repo (README, package files, top-level dirs), confirms paths exist, and produces schema-correct `.md` bodies tailored to the project. Invoked by `/agent-new` and by `holoctl-persona-suggester`.
- **`/agent-new <name>` slash command** — explicit entry point for designing a new persona. Workflow: library check → activate `agent-designer` if needed → delegate draft → save as `.draft.md` → preview → on `y` create via `mcp__holoctl__agent_create` and compile.
- **`mcp__holoctl__agent_create`** write tool (in `permissions.ask`) — validates frontmatter (name, description, body non-empty) and writes `.holoctl/agents/<name>.md`. Refuses to clobber active personas without `force: true`.
- **`holoctl-persona-suggester` SKILL** — reactive surfacing. Fires when work touches paths/domains no active persona owns. Library match → propose activation; no match → propose `/agent-new` with a candidate name. Caches suggestions per gap to avoid spam.
- **`hctl agent suggest` expanded** with 4 new signal groups: SQL/migrations → `dba`; workflows/Dockerfile/Terraform/k8s → `devops`; SECURITY.md/audit configs → `security-auditor`; docs/ with >10 md or active CHANGELOG → `tech-writer`.

## [0.16.0] — 2026-05-16

Refactor of every prompt-surface holoctl plants in Claude Code. Each
`.claude/*` file is now scoped to one responsibility, declares its native
auto-trigger metadata, and prefers MCP tools over shell-quoted CLI. The board
gains the missing primitives (`show`, `ack`, `note`) so the framework can stop
contradicting its own "never edit `.md` by hand" rule. CLAUDE.md grows
defensive protection against accidental overwrite of hand-curated content.

### Added — board primitives + MCP tools (M7)

- **`hctl board show <ID>`** + `mcp__holoctl__board_show` — read frontmatter + body of a ticket. Replaces the anti-pattern of agents opening `.holoctl/board/tickets/<ID>-*.md` directly.
- **`hctl board ack <ID> <idx>`** + `mcp__holoctl__board_ack` — toggle a DoD checkbox by zero-based index. Atomic; replaces hand-editing the `.md`.
- **`hctl board note <ID> "<text>"`** + `mcp__holoctl__board_note` — append a timestamped note to the ticket's `# Notes` section. Append-only.
- **`mcp__holoctl__board_batch`** — exposed the existing `batch_add` over MCP so agents can create parallel-safe ticket sets without shell quoting.

### Added — batch operations on existing tickets

- **`hctl board move PRJ-1,PRJ-2,PRJ-3 done`** — comma-separated IDs are treated as a batch move. Atomic per-ticket; errors per id reported without aborting siblings.
- **`hctl board set PRJ-1,PRJ-2 priority p0`** — batch set, same semantics.
- **`hctl board delete <ID>`** + `--force` (or comma-separated for batch) — **hard-delete**: removes the `.md` file and the index entry. For soft-delete (recoverable), use `move <ID> cancelled` instead.
- **MCP**: `mcp__holoctl__board_delete`, `_batch_move`, `_batch_set`, `_batch_delete` — explicit array-of-ids tools for atomic batch operations.

### Added — work item types (kind + parent + source_*)

The board now stores generic **work items** — `kind` distinguishes variants and `parent` links them hierarchically. The ticket model gains five new optional fields:

- **`kind`** — `task` (default), `story`, `bug`, `spec`, `epic`, `rfc`, `incident`, or any custom string. Drives which downstream agent is suggested and what lifecycle the item follows. Free-form: not an enum.
- **`parent`** — ID of a containing work item. A `task` whose `parent` is a `spec` is one of that spec's executable children. Different from `depends:` (which is sequencing, not containment).
- **`source_provider`** + **`source_ref`** + **`source_url`** + **`source_label`** — preserve the origin when the item came from an external board (Trello card, Linear issue, Azure DevOps PBI, Jira issue, GitHub issue, Slack thread, …). All optional; `manual` is the canonical value when the item was typed directly into the conversation. Inherited from `batch.shared` to all children when the boardmaster decomposes a spec, so round-trip traceability is automatic.

#### Filters and inspection

- **`hctl board ls --kind <kind> --parent <ID>`** + MCP — list filtered by work item type or by hierarchical parent.
- **`hctl board children <ID>`** + `mcp__holoctl__board_children` — list direct children of a spec/story/epic, with aggregate DoD progress (acked/total) and by-status breakdown.

### Added — `/spec` slash command + Spec-Driven Development flow

- **`/spec <optional-url-or-ref>`** — entry point for **Spec-Driven Development** (M13). Drives the pipeline: external-source intake → discuss to refine scope → materialize a `kind=spec` work item → decompose into parallel-safe child tasks via the boardmaster → propose execution. Works whether the source is pasted, referenced by URL, or invented on the spot.
- **`holoctl-spec-flow` SKILL** — the auto-triggered workflow behind `/spec`. Fires when the user pastes external board content or a multi-paragraph request worth structuring.
- **`holoctl-work-item-router` SKILL** — infers `kind` from user language. "como usuário…" → story; "tá com bug" → bug; "preciso definir…" → spec; etc. Also detects external board URLs (Trello/Linear/Azure DevOps/Jira/GitHub/Slack) and pre-fills `source_provider` + `source_ref`.
- **Boardmaster aware of Spec-Driven hand-off** — when called with `parent: <SPEC_ID>` in `batch.shared`, children automatically inherit `parent` + `source_*` so the entire batch is traceable back to the spec without per-ticket repetition.

### Added — reactive skills planted globally and per-project

Three new SKILL.md files emitted by `compile --target claude` into `.claude/skills/`:

- **`holoctl-parallel-evaluator`** — fires when work touches multiple files/modules. Decides single-vs-batch decomposition before the boardmaster is invoked.
- **`holoctl-ticket-discipline`** — fires when the user announces non-trivial work without a ticket. Checks for duplicates via `board_list`, proposes creation otherwise.
- **`holoctl-memory-discipline`** — fires on durable decisions ("vamos sempre X"). Routes to `/decision` (ADR) for hard locks or `memory_add` for soft context.

### Added — `/holoctl` becomes a SKILL with progressive disclosure (M1)

- **`~/.claude/skills/holoctl-router/`** — SKILL.md (~50 lines: Step 1 doctor + Flow C inline) plus `references/flow-a-first-time.md` (lazy first-time setup) and `references/flow-b-upgrade.md` (lazy upgrade flow). Installed globally by `hctl setup-global --target claude`.
- **`~/.claude/commands/holoctl.md`** — slim slash command (12 lines) that delegates to the SKILL. Slash command convention preserved; heavy content lazy.

### Changed — agent templates rewritten (M3 + M12)

- **`boardmaster.md`** — now `model: fast` (Haiku) since it's pure routing. Reorganized around a paralelo-first decision tree: single-vs-batch is the first question, not a special case. Cut from 142 → 130 lines, with parallel batch invariants kept as canonical reference. MCP tools listed as primary; CLI fallback.
- **`developer.md`** — adds Claude Code-native `paths:` auto-trigger for `src/**`, `**/*.py`, etc. New "DoD discipline" section pointing to `board_ack` and `board_note` instead of editing the `.md`. Includes handoff protocol to boardmaster on completion.
- **`reviewer.md`** — adds `paths:`. Issues reported as ticket notes via `board_note` (severity + file:line) instead of free-form prose.
- **`architect.md`** — adds `paths:` for interface/contract/schema globs. Decisions routed to `/decision` for ADR creation.
- **`researcher.md`** — now `model: fast` (Haiku). New section on promoting durable findings to memory via `memory_add` instead of dumping in ticket notes.
- **`compiler/claude.py`** filters `when_to_suggest:` and `trigger:` from agent frontmatter when emitting to `.claude/agents/` — those are curator-private metadata, not Claude Code instructions. Adds `paths:` emission when present in source.

### Changed — slash commands of project are now thin and MCP-first (M2)

Each `.claude/commands/<name>.md` rewritten to ≤ 20 lines with explicit `allowed-tools:`:

- **`/status`** — `board_list` filtered locally; CLI fallback only.
- **`/ticket`** — collects inputs, runs parallel-evaluator, delegates to boardmaster.
- **`/board [arg]`** — `board_list` for kanban, `board_show` for inspect, `board_move` for transition. No `Read` of ticket `.md` files.
- **`/sprint`** — `board_list`/`board_set` for plan and review.
- **`/decision`** — creates ADR in `.holoctl/context/decisions/` with structured Context/Decision/Implications.
- **`/close`** — `board_show`/`board_ack`/`board_note`/`board_move` atomically. No hand-editing checkboxes, no hand-editing notes.

### Changed — `CLAUDE.md` seed is invariants only (M4)

`.holoctl/instructions.md` reduced from ~55 lines of CLI cheat-sheet to ~25 lines of invariants + pointers. The board syntax lives in `--help`; CLAUDE.md is the always-on context, so only non-negotiables and where-to-find-it stay.

### Changed — ticket schema refined (M8)

- **`acceptance`** (preferred) is the new field name for what was `goal` — `goal` keeps working as a backwards-compatible alias. Renders as `# Acceptance — Definition of Done`.
- **`out_of_scope`** (snake_case preferred) — `outOfScope` accepted as legacy alias.
- **`start`** field removed from the conceptual schema; legacy `start` content merges into `context` on creation. The template's `# Start` section is gone.
- **`executionNotes`** removed from the creation schema; legacy content goes to `# Notes` instead. Going forward, use `board_note` for the append-only timeline.
- **`_template.md`** rewritten: frontmatter split into `# Auto — managed by hctl` and `# User — set on creation` blocks so the agent never confuses generated fields (id, created, updated, completed, status) with user-set ones. HTML comments dropped — they violated their own "no HTML comments" rule.

### Added — `hctl compile --force` and defensive overwrite protection (M9 + M11)

- **Hand-edited outputs are now preserved by default.** When `.claude/agents/<n>.md`, `.claude/commands/<n>.md`, etc. lack the `<!-- Generated by holoctl -->` header, `hctl compile --target claude` skips them and reports the skip — instead of overwriting silently.
- **`CLAUDE.md` gets stronger protection.** Hand-edited content is preserved by renaming to `CLAUDE.local.md` rather than skipped (so the new generated content can land). If `CLAUDE.local.md` already exists, a timestamped variant is used.
- **`hctl compile --force`** bypasses both. For `CLAUDE.md`, `--force` backs up the existing content to `.claude/.cache/CLAUDE.backup-<ts>.md` before overwriting.

### Migration notes

- Workspaces from 0.15: legacy `goal`/`outOfScope`/`executionNotes` fields keep working. New tickets get the new shape. Run `hctl board rebuild-index` to re-emit `.md`s in the cleaner format.
- Workspaces with hand-edited `CLAUDE.md`: the first `hctl compile --target claude` after upgrade will rename it to `CLAUDE.local.md`. Move what you want into `.holoctl/instructions.md` and re-compile.

## [0.15.0] — 2026-05-08

### Added (cross-tool primitives + rich `/holoctl` router)

- **New compile target `agents`** — `holoctl/lib/compiler/agents.py` emits `AGENTS.md` at the project root following the [agents.md](https://agents.md/) standard, respected by 20+ assistants (Claude Code, Codex, Copilot, Cursor, Devin, Zed, Aider, Junie, Jules, Factory, goose, Windsurf, UiPath, VS Code, …). Decoupled from the `devin` compiler that previously owned AGENTS.md emission. **Default `config.targets` is now `["agents", "claude"]`** so any AGENTS.md-aware assistant opening the repo gets context out of the box.
- **`hctl setup-global --target {claude|copilot|devin|all}`** — installs the `/holoctl` router globally for each AI tool. Idempotent via marker-fenced blocks (`<!-- holoctl:start ... end -->`) that preserve user-edited content outside the markers. Cursor/Windsurf intentionally excluded (no user-level surface; per-project compile covers them).
- **`hctl coverage [--only-present] [--target X]`** — prints the source-to-target matrix for the workspace: what's in `.holoctl/` and where each piece materializes per compile target. Useful for debugging "why isn't my hook firing in Cursor?" and auditing cross-tool gaps.
- **`hctl agent suggest [--json]`** — heuristic that inspects the codebase (package files, tests, ADRs, interfaces, monorepo signals, research notebooks) and proposes which library personas to activate via `hctl agent add`. Used by `/holoctl` Step 5 to recommend `developer`/`reviewer`/`architect`/`researcher` based on what the project actually is.
- **`hctl doctor` rewritten with router-friendly first line** — `holoctl: not initialized | outdated | ok`. Slash-command routers (Claude `/holoctl`, Devin skill, Copilot prompt) parse this line to choose init / upgrade / operate flow. The previous output buried the verdict in Rich-formatted markup, so the slash command couldn't actually route. New `--global` flag detects drift between installed package version and the global routers in `~/.claude`/`~/.copilot`/`~/.config/devin` and points to the exact `hctl setup-global --target X` command to fix it.

### Changed (compilers — wider native-primitive coverage)

- **`compiler/devin.py`** now emits `.devin/agents/<n>/AGENT.md` (subagents — was missing despite Devin having the format) and `.devin/hooks.v1.json` (lifecycle hooks — was missing). AGENTS.md emission removed (now handled by the dedicated `agents` target).
- **`compiler/windsurf.py`** now imports `hooks_emit` and emits `.windsurf/hooks.json` (was missing entirely — Windsurf received zero hooks even when `.holoctl/hooks/` was populated).
- **`compiler/copilot.py`** now emits `.copilot/config.json` for hook merge.
- **`compiler/claude.py`** now emits `.claude/rules/` (path-scoped rules with `paths:` frontmatter), `.claude/skills/<n>/...` (custom skills with progressive disclosure: `references/`/`scripts/`/`templates/` copied verbatim) and `.claude/output_styles/`.
- **`templates/hooks/claude_settings.json`** extended with `SessionStart` → `hctl boot --plain` teaser, `Stop` → `hctl handoff --auto`, `PreToolUse` `Edit|Write` deny-glob on derived state, plus `permissions.deny` enforcement on `.holoctl/board/index.json` / `memory/MEMORY.md` / `activity.jsonl` (so even if the agent forgets the instruction, the harness blocks the tool call).
- **`hooks_emit.py`** grows `emit_windsurf`, `emit_copilot`, `emit_devin` functions. Cursor template is reused as fallback when a target-specific template is absent — same lifecycle semantics, different file location.
- **`templates/commands/holoctl-claude.md`** synced with the rewritten global router (DRY).

### Fixed

- **`/holoctl` no longer "stalls" on init.** The global skill at `~/.claude/commands/holoctl.md` was a 4-step `hctl init` → `hctl boot` → "stop and wait" stub, while the rich 7-step flow (detect → init → discover → configure → suggest personas → seed memory → overview-react) lived only in the per-project compiled template (which doesn't exist before init runs). Plus a hardcoded venv path referencing the legacy `projctl` name. Replaced by the same 7-step flow as the per-project template, with PATH-based `hctl` invocation. Legacy `~/.claude/commands/projctl.md` and `projhub.md` are flagged for removal in the README's Migration section.

### Anti-overengineering invariant preserved

Compilers only emit what exists in `.holoctl/`. Optional source surfaces (`hooks/`, `rules/`, `skills/`, `output_styles/`, `ignore`) are **not** created by `hctl init` — they're opt-in directories users create when they need them. Empty input → empty output (no JSON `{}` blobs polluting workspaces).

### Docs

- **READMEs (EN + pt-BR) comprehensively rewritten** — 879 lines each with full parity. New sections: Anatomy of `.holoctl/`, expanded Installation (with the `pip` venv gotcha explained: PEP 668, alias/wrapper recipes for bash/zsh/PowerShell), Per-machine global setup, `/holoctl` 7-step deep dive, Compilation cross-tool with full source→target matrix, **MCP vs CLI design-choice section**, Daily workflows, Lifecycle hooks (actual `settings.json` content), Per-assistant guide, Coverage and doctor, Troubleshooting (8 real failure modes), FAQ (9), Roadmap.

### MCP vs CLI — design choice (documented honestly)

Today's agent and slash-command templates are still instructed to use `hctl` CLI, not the MCP server tools. The MCP server (`hctl serve --mcp`, 14 tools, write-tools landing in `permissions.ask`) is installed by `hctl init` and runs in parallel — but `boardmaster.md` says `hctl board add ...`, not `mcp__holoctl__board_create`. Trade-off: universality (CLI works in any terminal/agent/shell) vs granular permission gating (MCP). Roadmap entry added to flip to MCP-first once a probe step is added to `/holoctl` Step 1.5.

### Tests

- 1 test rewritten (`test_emit_claude_idempotent_no_duplicate_hooks`) — instead of asserting "exactly 1 SessionStart hook", it now asserts "no duplicate commands in any event", which is the actual idempotency property and survives the new richer hook set. **260 tests passing** locally without the dashboard suite; the full CI matrix (Python 3.11/3.12/3.13 × Ubuntu/macOS/Windows) runs everything via `uv sync --frozen` (which pulls `httpx` from the `dev` dependency group) and stays green.

## [0.14.0] — 2026-05-07

### Added (autonomous curator — the "alive" of the system)

- **`hctl curate {run, show, silence, apply}`** — the curator engine that watches the journal and proposes new agents/rules/topics as `meta:curate` tickets on the board. Per item 8A of the multi-assistant plan: when you approve a `meta:curate` ticket by moving it to **`done`**, the boardmaster auto-executes the action stored in the ticket's metadata (e.g. `agent_add`, `rule_extract`, `topic_archive`, `memory_promote`). One-click approval; reversible via the inverse command.
- **5 built-in rules**, each in its own module under `holoctl/lib/curator_rules/`:
  - `repeated_glob_edits` — N edits in same `a/b/**` path → propose a memory topic with `scope=glob` and the conventions for that area.
  - `repeated_prompt` — same prompt asked N times → propose extracting it as a durable note (precursor to slash command). Uses token-hash matching by default; with `pip install holoctl[ml]` upgrades to `fastembed` ONNX embeddings (~250MB) for paraphrase detection at ≥0.85 cosine similarity (item 6 — opt-in extra avoids the 700MB torch from sentence-transformers).
  - `unused_topic` — memory topic untouched ≥60 days → propose archiving. Skips `session-trail` (append-only by `hctl handoff`).
  - `library_persona_match` — parses each library persona's `when_to_suggest:` frontmatter via PyYAML (item 7 — added as core dep) and counts matching journal events. When a heuristic fires, proposes activating that persona.
  - `windsurf_memory_promote` — reads Cascade auto-memories at `~/.codeium/windsurf/memories/`. Topics that survived ≥7 days get a promote-to-versioned-topic suggestion. Closes the loop the Windsurf docs explicitly recommend (move durable knowledge from Memories to Rules).

### Guardrails (rate limit + suppression)

- **1 new suggestion per calendar day per workspace** (item 9). Avoids spam from rules that fire continuously.
- **30-minute cooldown** between automatic curator runs (item 5A — Stop hook fires often, but the curator only computes once per cooldown window). `--bypass-cooldown` flag bypasses for testing or manual runs.
- **14-day suppression** on `hctl curate silence <pattern_id>`. Stored in `.holoctl/curator/state.json` with the absolute `until` timestamp; expires automatically.
- **Deduplication against open `meta:curate` tickets** — the same pattern can't generate duplicates while the original is still on the board.

### Plumbing

- **Auto-execute via `Board.move(..., 'done')`** when ticket has tag `meta:curate` and a parallel `.holoctl/curator/tickets/<id>.json` metadata file exists. Soft-import keeps the curator out of the board's hard dependency graph.
- **MCP tools `holoctl.curate_suggestions` and `holoctl.curate_silence` are now functional** (were stubs in 0.13). Read tool returns open `meta:curate` tickets; write tool persists silences (lands in `permissions.ask`).
- **PyYAML added as a core dependency** for parsing nested YAML frontmatter (`when_to_suggest:` in personas). Same parser is reusable in 0.15+ for other rule schemas.

### Sanity validated

- End-to-end in `SANITY-0.14.txt`:
  1. 12 simulated `tool_use` Edit events in `src/api/**` → `repeated_glob_edits` fires → creates `CT-001` `meta:curate` ticket.
  2. Same-day re-run → rate limit blocks (output: "No new suggestions").
  3. `hctl board move CT-001 done` → auto-executes `rule_extract` → memory topic `convention-src-api` materialized with `scope=glob` and `globs: ["src/api/**"]`.
  4. `hctl curate silence` persists in `state.json` with 14-day expiry timestamp.
  5. Parallel metadata file `.holoctl/curator/tickets/CT-001.json` keeps the action+args separate from the board schema.

### Tests

- 17 new (260 total). Coverage: state persistence, suppression with time-based expiry, rate-limit one-per-day, silence dedup, every built-in rule (repeated_glob_edits, repeated_prompt hash mode, unused_topic, library_persona_match with YAML, session-trail exclusion), apply for `agent_add` / `topic_archive`, board.move auto-execute path, cooldown blocking.

## [0.13.0] — 2026-05-07

### Added (MCP server — board/memory accessible from any assistant)

- **`hctl serve --mcp`** — runs the holoctl board/memory/journal/curator/agent surface as a stdio Model Context Protocol server. Per item 1 of the multi-assistant plan: stdio transport, NOT HTTP daemon. Each assistant spawns a short-lived `hctl serve --mcp` process when it needs to call a tool. No PID files, no daemon, works on Windows trivially.
- **14 tools exposed**, split read vs write:
  - **Read** (auto-approved): `holoctl.board_list`, `holoctl.board_get`, `holoctl.memory_list_topics`, `holoctl.memory_read_topic`, `holoctl.memory_search`, `holoctl.journal_recent`, `holoctl.agent_list_available`, `holoctl.curate_suggestions`.
  - **Write** (user approval required via `permissions.ask`): `holoctl.board_create`, `holoctl.board_move`, `holoctl.board_set`, `holoctl.memory_add`, `holoctl.agent_add`, `holoctl.curate_silence`.
- **Schema mirrors the CLI 1:1** (item 3 of the plan). Filters and arguments match `hctl board ls --status X --priority Y` exactly. Zero surprise; one mental model.
- **Output is JSON-stringified** (item 4) inside MCP's `content: [{type: "text", text: "..."}]` — clients parse and render natively.
- **No `mcp` package dependency** — minimal JSON-RPC implementation in `holoctl/server/mcp.py`. Reasons: install footprint, cold-start latency (each call spawns a Python process), and the protocol surface is small enough that depending on a 5MB+ package would be wasteful.

### Added (per-target MCP config emission)

- **All five compilers now emit native MCP server config**, merging non-destructively with any existing user MCP config:
  - Claude Code: `.claude/settings.json:mcpServers.holoctl`
  - Cursor: `.cursor/mcp.json`
  - Copilot: `.vscode/mcp.json` (uses `servers:` key per VSCode's schema, not `mcpServers:`)
  - Windsurf: `.windsurf/mcp.json`
  - Devin: `.devin/mcp.json` (best-effort)
- The absolute path of `hctl` is resolved at compile time via `shutil.which()` so the config works with `uv tool install`, `pipx`, or plain `pip` in venv.
- Curator stubs return placeholders explaining the engine arrives in 0.14 — board/memory/agent calls are fully functional now.

### Tests

- 21 new tests (243 total). Coverage: protocol initialize/tools/list/tools/call, unknown method/tool error codes, missing-required-arg validation, board CRUD round-trip via MCP, memory add+list round-trip, agent materialize via MCP, write-flag categorization, JSON-text content shape, idempotent emission per target, user-MCP-server preservation on merge.

### Sanity validated

- Sanity in `SANITY-0.13.txt`: 4 JSON-RPC messages (`initialize`, `tools/list`, `board_list`, `memory_list_topics`) round-tripped through `hctl serve --mcp` via stdin/stdout. All 14 tools advertised with input schemas. Workspace ticket MT-001 retrieved via `board_list` matches the one created via CLI.

## [0.12.0] — 2026-05-07

### Added (token-economy boot + cross-session handoff)

- **`hctl boot`** — minimal session-zero context, target ≤ 1KB. Prints the project name, top 3 pendings filtered to `p0|p1` (in-flight first), 0–2 most recent decisions, active topic names, active persona names, and an `⚡` line listing open `meta:curate` tickets. Designed to be the FIRST thing the assistant prints in a fresh session — the full content stays on disk and is loaded only when the agent asks for a specific topic/ticket. Records a `boot` event in the journal so the curator can correlate sessions.
- **`hctl handoff`** — end-of-session persistence. Reads today's journal records + git diff HEAD, computes session duration / event count / files-changed brief, and appends ONE line to `.holoctl/memory/topics/session-trail.md`. The trail topic is auto-created on first call with a description that makes Claude/Cursor lazy-load it when the user asks "where did we stop?" — direct token-economy: a session line costs ~150 chars but gives full context recall.
- Both commands plug into the `/holoctl` skill: Flow A → boot (after init), Flow B → boot (after upgrade), Flow C → boot (status request) / handoff (close request).
- The `--plain` flag on boot strips Rich ANSI codes for embedding in tooling output.

### Sanity validated

- Sanity end-to-end captured in `SANITY-0.12.txt`: empty workspace → init → 3 tickets (p0 backlog, p1 doing, p3 backlog) → memory topic + persona + decision → `boot` returns 198 bytes (≤19% of the 1KB budget) → simulated session journal → `handoff` creates session-trail topic with the right scope/description → second `boot` shows the new topic + a `meta:curate` ticket as `⚡ 1 sugestão`.

### Tests

- 19 new (222 total). Coverage: pendency filtering by priority + status, in-flight surfacing, curate-ticket open/closed filter, topic listing excludes archived, persona listing, decision sort by mtime, full boot CLI invocation under 1KB, journal event recorded, duration formatting at sub-minute / minute / hour granularity, files-brief truncation, session-trail topic creation + append.

## [0.11.0] — 2026-05-07

### Added (event journal)

- **`.holoctl/journal/<YYYY-MM-DD>.jsonl`** — append-safe daily JSONL of session events. Schema: `{ts, source, kind, payload}`. The journal is the input for the curator (0.14) — it doesn't act on it yet, but every record from now on will eventually be available for pattern detection. Locking is best-effort cross-process (msvcrt/fcntl) plus a per-process `threading.Lock` so concurrent writes from hooks running in parallel never corrupt the file.
- **`hctl journal` subcommand** — `record`, `show`, `count`, `import`. `record --quiet` is the hot path used by hooks (no output, ~5ms per call). `show` and `count` are debugging helpers.

### Added (setup-zero)

- **`hctl setup`** — plants the `/holoctl` skill in every detected AI assistant in **user scope** (one-time, per machine). Detects Claude Code (`~/.claude`), Cursor (`~/.cursor`), Windsurf (`~/.codeium/windsurf`), Copilot (`~/.copilot`), Devin (`~/.config/devin` or `%APPDATA%\devin`). Resolves `hctl` absolute path via `shutil.which()` so the slash works regardless of installer (`uv tool install`, `pipx`, `pip` in venv). Idempotent — re-run updates content; `--force` to overwrite hand-edited skills.
- **The `/holoctl` skill body** — same content across the 5 targets (only frontmatter differs to match each assistant's schema). Routes the agent through three flows based on `hctl doctor` output: **A** (not initialized → `hctl init`), **B** (outdated → `hctl upgrade`), **C** (ok → operate via `boot/board/handoff/curate/agent/memory`). Designed so the user never has to remember CLI commands — they just type `/holoctl` and the agent picks the right call.

### Changed (init becomes idempotent)

- **`hctl init` is now idempotent and version-aware.** Behavior matrix:
  - `.holoctl/` absent → creates skeleton + compiles + plants hooks/MCP (existing behavior, unchanged).
  - `.holoctl/` present, version equals installed → re-runs sync+recompile **non-destructively** (user-owned tickets/agents/memory preserved via the same allow-list `hctl upgrade` uses).
  - Workspace version < installed → exits 0 with a clear hint pointing at `hctl upgrade`.
  - Workspace version > installed → exits 2 (anti auto-downgrade — same guard `upgrade` enforces).
  - New `--bare` flag creates only the directory skeleton without compile/hooks/MCP — used internally and by tests that need a workspace shell without side effects.

### Added (hooks plumbing per target)

- **All compiles now plant journal hooks.** Claude Code: `.claude/settings.json` gains `hooks.{SessionStart, PostToolUse, Stop}` calling `hctl journal record`. Cursor: `.cursor/hooks.json` gains `sessionStart` and `afterFileEdit`. Both merged **non-destructively** with any existing user hooks (deduplication by exact-content equality — re-running `compile` doesn't add duplicates).
- **Write tools land in `permissions.ask`** in `.claude/settings.json`: every MCP write (`mcp__holoctl__board_create/move/set`, `agent_add`, `memory_add`, `curate_silence`) requires explicit user approval before the assistant can execute. Read tools auto-approve. Honors plan decision item 2A (write expostos com `permission: ask`).

### Tests

- 32 new (203 total). Coverage: journal record/recent/count, threaded write integrity, hook merge non-destructive, hook idempotency, `permissions.ask` write tools present, `hctl setup` body assembly, frontmatter shape per target, init idempotency at same/older/newer version, `--bare` flag, journal/memory dirs created at init.

## [0.10.0] — 2026-05-07

### Added (durable cross-assistant memory)

- **`.holoctl/memory/` — single source of durable, cross-assistant context.** New tree at workspace root: `MEMORY.md` (always-on index, ≤200 lines) plus `topics/<name>.md` (lazy/glob-scoped). Each topic carries canonical frontmatter (`scope: always_on | lazy | glob`, optional `globs:`, optional `description:`) that compilers translate to each target's native primitive — no per-topic translation code needed.
- **`hctl memory` subcommand** — `list`, `get`, `add`, `search`, `archive`, `seed`. Body comes from `--from-file` or stdin; topic frontmatter is set by flags. Validation refuses `scope=lazy` without `description:` (the model uses it to decide when to load) and `scope=glob` without `globs:`.
- **All five compilers emit native memory primitives.** Same `.holoctl/memory/` tree compiles to:
  - Claude Code: `.claude/skills/holoctl-memory/SKILL.md` (index) + `.claude/skills/holoctl-memory-<topic>/SKILL.md` (per topic, with `description:` for lazy and `paths:` for glob — model decides via progressive disclosure).
  - Cursor: `.cursor/rules/holoctl-memory.mdc` (`alwaysApply: true`) + per-topic `.mdc` with `description:` (Apply Intelligently) or `globs:` (Apply to Specific Files).
  - Windsurf: `.windsurf/rules/holoctl-memory.md` (`trigger: always_on`) + per-topic with `trigger: model_decision` (lazy) or `trigger: glob` (path-scoped). Hard 12k-char limit per file enforced. **Not** writing to `~/.codeium/windsurf/memories/` — that path is Cascade's auto-memory and the doc explicitly recommends `.windsurf/rules/` for durable knowledge.
  - Copilot: `.github/instructions/holoctl-memory-<topic>.instructions.md` with `applyTo:` glob.
  - Devin: `.devin/rules/holoctl-memory*.md` (best-effort given doc sparseness; same content layout as Windsurf).
- **`hctl init` seeds an empty `MEMORY.md`** with a project-named header and creates `.holoctl/memory/.gitignore` defaulting to "everything committed except `topics/_archived/`". Privacy-strict workspaces can uncomment two lines to make the whole tree local-only.

### Coexists with native auto-memory

- **Claude Code's auto-memory is NOT disabled.** The compiler appends a "Workspace memory" pointer block to the generated `CLAUDE.md` referencing `@.holoctl/memory/MEMORY.md` so Claude reads both sources. If conflict, Claude's normal context-ordering applies. Disabling `autoMemoryEnabled` is left to the user — out of scope for the compiler.

### Tests

- 26 new tests covering `Memory` CRUD, archive flow, search, and per-target compile output (validating frontmatter shape for each of the 5 emitters). Suite stays green: 171 passing.

## [0.9.0] — 2026-05-06

### Added (workspace upgrade flow)

- **`hctl upgrade` — single-command workspace upgrade.** Orchestrates the four steps users used to run by hand after every release: `sync --agents` (refresh template-managed files in `.holoctl/`), `compile` for every target in `config["targets"]` (regenerate `CLAUDE.md`, `.cursor/rules/*`, etc), `board rebuild-index` (migrates ticket schemas — `scope`→`projects`, date-only → ISO 8601, etc), and `doctor` (final health check). Bumps `holoctlVersion` in `.holoctl/config.json` on success.
- **`hctl upgrade --check`** — diagnostic mode. Prints `workspace_version`, `installed_version` and the slice of `CHANGELOG.md` between them (sections strictly greater than workspace, up to and including installed). Writes nothing.
- **`hctl upgrade --dry-run`** — propagates `dry_run=True` through `sync` and `compile`, skips `rebuild-index`, skips the version bump. Useful for previewing what a release would touch in CI.
- **Auto-downgrade refusal.** If `installed_version < workspace_version`, the command exits 2 with a warning. Rolling the workspace back to an older release is a manual edit, not a one-button operation.
- **`/hctl-upgrade` slash command published to all five targets** (claude, cursor, windsurf, copilot, devin). `hctl-` prefix avoids colliding with native or third-party `/upgrade` in the AI tool's namespace. The bootstrap walks the agent through diagnostic → ASK-once suggestion of the right install command (`uv tool upgrade holoctl` / `pipx upgrade holoctl` / `pip install -U holoctl`) → run `hctl upgrade` → `hctl overview`. Hard rule: **never** runs the package install without explicit user confirmation.
- **`holoctlVersion` field in `.holoctl/config.json`.** Stamped at `hctl init` to the version that initialized the workspace; bumped by `hctl upgrade` after a successful sync. Default `"0.0.0"` for workspaces created before this release — `hctl upgrade --check` will treat them as fully stale and surface the entire CHANGELOG slice.

### Changed (CHANGELOG distribution)

- **`CHANGELOG.md` moved to `holoctl/CHANGELOG.md` and bundled via `[tool.setuptools.package-data]`.** `hctl upgrade` reads it offline through `importlib.resources` so the diff is available without network. Doc references in `README.md`, `README.pt-br.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, and `.github/PULL_REQUEST_TEMPLATE.md` updated to point at the new path.

### Preserved

- **User content is never touched by `hctl upgrade`.** The sync set is the same allow-list as `cli.sync_._SYNC_TARGETS` — bootstraps and the ticket `_template.md`. Files under `.holoctl/board/tickets/<ID>-*.md` and `.holoctl/context/*` are user-authored and survive untouched. Covered by regression test `test_full_run_preserves_user_ticket_bodies`.

## [0.8.1] — 2026-05-06

### Fixed (templates)

- **`tickets/_template.md` was missing the `files:` frontmatter field.** PR #14 (0.7.1) introduced `files: list[str]` as the field `Board.add()` reads and `hctl board batch` requires for parallel-overlap validation, but I forgot to add the corresponding line to the human-facing `_template.md` example. Users running `hctl sync` got the new template but it didn't show `files:`, leaving them confused about the contract. Now it's there with a comment explaining when it's required.
- **`/ticket` slash command** updated to mention `files` in the recognized fields list and include it in the worked JSON example. Boardmaster persona was already correct from PR #14.

Run `hctl sync` to refresh `_template.md` in existing workspaces.

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

[0.8.1]: https://github.com/FelipeCarillo/holoctl/releases/tag/v0.8.1
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

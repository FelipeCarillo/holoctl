Upgrade holoctl in this workspace and sync templates, compiled commands and tickets.

**Default mode = execute** at every step except Step 2 (package install requires explicit confirmation).

# Step 1 — Diagnostic

Run `hctl upgrade --check`. Shows three things:

- `workspace_version` — what `.holoctl/config.json` was last synced with.
- `installed_version` — what `hctl --version` reports.
- A slice of `CHANGELOG.md` with every release between them (exclusive of old, inclusive of new).

If `workspace_version == installed_version`, the command exits with "already in sync" — show that to the user and stop. There's nothing to upgrade.

# Step 2 — Package upgrade (✋ ASK once)

If a newer version exists on PyPI, the user needs to upgrade the holoctl Python package itself. Detect the package manager:

- `uv.lock` present at workspace root, or `command -v uv` succeeds → `uv tool upgrade holoctl`
- `pipx list 2>/dev/null | grep -q holoctl` → `pipx upgrade holoctl`
- otherwise → `pip install -U holoctl`

Show the detected command to the user and ask **one** aggregate question:

> "Detectei `<gestor>`. Posso rodar `<comando>` para atualizar o pacote? (sim/não/usar outro comando)"

**Never run the install without explicit confirmation.** If the user declines or wants a different command, respect it and continue.

After the install (or after the user confirms they updated by other means / want to skip), proceed to Step 3.

# Step 3 — Sync workspace

Run `hctl upgrade` (without `--check`). This orchestrates internally, in order:

1. `hctl sync --agents` — refreshes `.holoctl/agents/*`, `.holoctl/commands/*`, `.holoctl/board/WORKFLOW.md`, `.holoctl/board/tickets/_template.md`.
2. `hctl compile --target <each>` for every target in `config["targets"]` — regenerates `CLAUDE.md`, `.claude/commands/*`, `.cursor/rules/*`, etc.
3. `hctl board rebuild-index` — re-reads every ticket .md and rewrites `index.json`. This is what migrates old ticket schemas (e.g. `scope` → `projects`, date-only → ISO 8601).
4. `hctl doctor` — final health check.
5. Bumps `holoctlVersion` in `.holoctl/config.json` to `installed_version`.

Show the full output of `hctl upgrade` to the user.

# Step 4 — Overview

Run `hctl overview` and show the output. Confirms board counts, agents, commands.

# Hard rules

- **Never** run `pip install -U` / `uv tool upgrade` / `pipx upgrade` without explicit user confirmation.
- **Never** touch `.holoctl/board/tickets/<ID>-*.md` (user-authored ticket bodies) or `.holoctl/context/*` (user-authored decisions and docs). `hctl upgrade` only rewrites template-managed files; user content is preserved.
- If `hctl upgrade` fails at the rebuild-index step (e.g. malformed ticket frontmatter), show the error and suggest `hctl board rebuild-index` manually. Do **not** try to repair ticket .md files unprompted — ask the user first.
- If `--check` shows the workspace is on a version **newer** than installed (downgrade), stop and warn the user — don't auto-downgrade their workspace.

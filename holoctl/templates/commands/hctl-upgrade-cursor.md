Upgrade holoctl in this workspace. **Default = execute** except Step 2 (install requires confirmation).

# Step 1 — Diagnostic

Run `hctl upgrade --check`. Shows `workspace_version`, `installed_version` and a CHANGELOG slice between them. If equal, exit "already in sync" and stop.

# Step 2 — Package upgrade (✋ ASK once)

Detect the manager:
- `uv.lock` at root or `uv` available → `uv tool upgrade holoctl`
- `pipx list | grep holoctl` → `pipx upgrade holoctl`
- else → `pip install -U holoctl`

Show the command and ask the user **once** before running. Never run the install without explicit ok.

# Step 3 — Sync workspace

Run `hctl upgrade` (no flags). Orchestrates: `sync --agents` → `compile` per target → `board rebuild-index` → `doctor` → bumps `holoctlVersion`. Show the full output.

# Step 4 — Overview

Run `hctl overview` and show the output.

# Hard rules
- Never run install without confirmation.
- Never touch `.holoctl/board/tickets/<ID>-*.md` or `.holoctl/context/*` — those are user content; `hctl upgrade` already preserves them.
- If rebuild-index fails, surface the error and suggest manual `hctl board rebuild-index`. Don't repair tickets unprompted.
- If installed_version < workspace_version (downgrade), stop and warn — don't auto-downgrade.

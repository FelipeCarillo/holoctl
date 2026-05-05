Initialize, inspect, or onboard projhub in the current project directory. **You are responsible for actually populating the project context — `projhub init` only creates skeleton files.**

# Step 1 — Detect state

Run `projhub doctor`.

- If "No .projhub/ found": treat as **uninitialized**.
- Otherwise: treat as **initialized** (skip to Step 4).

# Step 2 — Initialize (only if uninitialized)

Run `projhub init`. This creates `.projhub/` and auto-runs `projhub compile --target cursor`.

# Step 3 — Onboard the project (CRITICAL)

The skeleton files are placeholders. Read the codebase and POPULATE the real context.

## 3.1 — Read the codebase

In parallel:
- **Top-level files**: README, package.json / pyproject.toml / Cargo.toml / go.mod / etc.
- **Top-level directories**: identify sub-projects vs config dirs.
- **Existing AI instructions**: `.cursor/rules/*`, `CLAUDE.md`, `.windsurfrules`. Read for context, don't overwrite.
- **Linters/formatters**: .eslintrc, .prettierrc, ruff.toml, .editorconfig.

## 3.2 — Populate `.projhub/context/objective.md`

Replace placeholders. 3 sections:
- **What**: 1-2 sentences on what the project does.
- **Why**: target audience / problem.
- **Success criteria**: 2-4 concrete `[ ]` derived from README/code.

## 3.3 — Populate `.projhub/context/architecture.md`

- **Tech stack**: actual languages/frameworks from package files.
- **Structure**: real directory layout with one-line descriptions.
- **Key patterns**: only patterns visible in code.
- **Boundaries**: in scope vs out of scope.

## 3.4 — Populate `.projhub/context/conventions.md`

Derive from real configs:
- **Naming**: from existing file names.
- **Style**: from prettier/eslint/ruff configs.
- **Imports**: from tsconfig / eslint import-order.
- **Testing**: framework from devDependencies + convention.

Write `(not enforced)` rather than guessing.

## 3.5 — Register sub-repos (multi-package only)

```bash
projhub repo add ./backend  --name backend  --description "(one-line)"
projhub repo add ./frontend --name frontend --description "(one-line)"
```

## 3.6 — Update `.projhub/instructions.md`

Fill Identity, Folder map. Leave Decisions empty unless explicit ADRs exist.

## 3.7 — Recompile

Run `projhub compile --target cursor` to regenerate `.cursor/commands/*` and `.cursor/rules/projhub.md`.

# Step 4 — Inspect (when already initialized)

1. `projhub board stat`
2. `projhub board ls --status doing`
3. `projhub agent list`
4. `projhub repo list`
5. Suggest next action.

# Step 5 — Final report

- ✅ what was set up
- 🌐 dashboard: `http://127.0.0.1:4242` via `projhub serve`
- 🎯 suggested next action (1 line)

Initialize, inspect, or onboard projhub in the current project directory. **You are responsible for actually populating the project context — `projhub init` only creates skeleton files.**

# Step 1 — Detect state

Run `projhub doctor`.

- If it errors with "No .projhub/ found", treat as **uninitialized**.
- If it returns checks, treat as **initialized** (proceed to Step 4).

# Step 2 — Initialize (only if uninitialized)

Run `projhub init`. This creates `.projhub/` with skeleton templates. Note that `init` also auto-runs `projhub compile --target claude` and `projhub setup-global`.

# Step 3 — Onboard the project (CRITICAL — do not skip)

The skeleton files are placeholders. You must now READ THE CODEBASE and POPULATE the real context. Spend the time it takes to do this well — this is the entire point of `/projhub`.

## 3.1 — Read the codebase

In parallel, gather:
- **Top-level files**: README, package.json / pyproject.toml / Cargo.toml / go.mod / pom.xml / Gemfile / etc.
- **Top-level directories**: list them and identify which are sub-projects vs config (e.g. `backend/`, `frontend/`, `docs/`, `.github/`).
- **Existing AI instructions**: `CLAUDE.md`, `.cursor/rules/*`, `.windsurfrules`, `.github/copilot-instructions.md`, `AGENTS.md`. Do NOT overwrite these — read them for context.
- **Linters/formatters configs** (.eslintrc, .prettierrc, ruff.toml, .editorconfig) — these reveal real conventions.

## 3.2 — Populate `.projhub/context/objective.md`

Open the file, replace the placeholders. Write 3 sections:
- **What**: 1-2 sentences. What does this project actually do?
- **Why**: who it's for / what problem it solves.
- **Success criteria**: 2-4 concrete `[ ]` checkboxes derived from the README/code, not generic.

## 3.3 — Populate `.projhub/context/architecture.md`

Replace placeholders with real info:
- **Tech stack**: list languages, frameworks, key libraries actually used (from package files).
- **Structure**: real top-level directory layout with one-line descriptions.
- **Key patterns**: only patterns that show up in the code (feature folders, layered, monorepo, event-driven). Don't speculate.
- **Boundaries**: what's in scope vs explicitly out of scope (often in README or CONTRIBUTING).

## 3.4 — Populate `.projhub/context/conventions.md`

Derive from real configs:
- **Naming**: from existing file names (kebab-case files? PascalCase components?)
- **Style**: from prettier/eslint/ruff config (indent size, quotes, semicolons)
- **Imports**: from tsconfig paths, eslint import-order rules, etc.
- **Testing**: detect framework from devDependencies; note convention (co-located vs `__tests__/`).

If a config doesn't exist for a given dimension, write `(not enforced)` rather than guessing.

## 3.5 — Register sub-repos (only if multi-package)

If the project has multiple top-level directories that are sub-projects (each with its own package file or `.git`), register them:

```bash
projhub repo add ./backend  --name backend  --description "(one-line)"
projhub repo add ./frontend --name frontend --description "(one-line)"
```

Skip if it's a single flat project.

## 3.6 — Update `.projhub/instructions.md`

Open `.projhub/instructions.md`. The sections "Identity", "Decisions", and "Folder map" have placeholders. Fill them:
- **Identity**: same 1-2 sentences from objective.md "What".
- **Folder map**: real top-level folder list with descriptions.
- **Decisions**: leave empty unless you found explicit decisions in README/ADR files.

## 3.7 — Recompile

Run `projhub compile --target claude` to regenerate `CLAUDE.md` and `.claude/commands/*` from the now-populated `.projhub/`.

# Step 4 — Inspect (when already initialized)

Show the current state:
1. `projhub board stat` — counts by status
2. `projhub board ls --status doing` — what's in progress
3. List configured agents with `projhub agent list`
4. List configured repos with `projhub repo list`
5. Suggest next steps based on state (e.g. "no tickets yet — create one with `/ticket`", "stale tickets in doing", etc).

# Step 5 — Final report

End with a short summary:
- ✅ what was set up (or what's already configured)
- 🌐 dashboard URL: `http://127.0.0.1:4242` (run `projhub serve` to start)
- 🎯 suggested next action (1 line)

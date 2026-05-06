Onboard, configure or inspect holoctl for the current project.

**Default mode = execute.** Read the codebase, infer what's reasonable, write the files. Pause to ask the user only at the three checkpoints below — never per file.

# Step 1 — Detect state

Run `hctl doctor`.

- **Errors with "No .holoctl/ found"** → uninitialized. Go to Step 2.
- **Returns checks** → already initialized. Go to Step 5 (Inspect).

# Step 2 — Initialize

Infer the project name and prefix from the current directory and run:

```bash
hctl init --name "<inferred>" --prefix "<INFERRED>"
```

(Or `hctl init` with no flags if the inference is obvious — the CLI derives both from `cwd.name`.) `init` auto-runs `hctl compile --target claude` so `CLAUDE.md` and `.claude/commands/` get written in the same step.

# Step 3 — Discover (read-only, parallel)

In a single batch, read:
- `README.md` (and `README.pt-br.md` if present)
- Package files: `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` / `pom.xml` / `Gemfile`
- Top-level directories — flag those with their own package file or `.git` as candidate sub-projects
- Existing AI instructions: `CLAUDE.md`, `.cursor/rules/*`, `.windsurfrules`, `.github/copilot-instructions.md`, `AGENTS.md` (read for context, NEVER overwrite)
- Lint / format configs: `.eslintrc*`, `.prettierrc*`, `ruff.toml`, `pyproject.toml [tool.ruff]`, `.editorconfig`

# Step 4 — Configure (execute by default)

## 4.1 — Sub-repos (✋ ASK once, batched)

If you found multiple sub-projects, **ask one aggregate question**:

> "Encontrei estes sub-projetos: `backend/`, `frontend/`, `mobile/`. Registro todos? Se algum não deve entrar, me fala quais; senão, respondo com 'todos' e prossigo."

For each one approved, run:
```bash
hctl repo add ./<path> --name <name> --description "<one-line>"
```

If single project, **skip silently** (no question).

## 4.2 — Context files (✏️ write directly, no per-file confirmation)

Write the four files based on what you read. The user can edit afterwards — these are not destructive decisions.

- **`.holoctl/context/objective.md`**: What / Why / Success criteria, derived from README. If success criteria can't be inferred, leave the bullets blank with a comment `<!-- TBD -->`.
- **`.holoctl/context/architecture.md`**: Tech stack (real frameworks/libs from package files), Structure (real top-level layout), Key patterns (only patterns visible in code), Boundaries.
- **`.holoctl/context/conventions.md`**: derived from real lint/format configs. For dimensions without config, write `(not enforced)` instead of guessing.
- **`.holoctl/instructions.md`**: fill Identity (1-2 sentences from objective.md "What") and Folder map (real top-level dirs).

## 4.3 — Ambiguity escape (✋ ASK only if needed)

If after reading the codebase you genuinely **cannot infer** what the project does (no README, generic placeholder text, contradicting signals), ask **one** question:

> "Não consegui inferir o objetivo do projeto a partir do README/código. Em 1-2 linhas, o que esse projeto faz?"

Then write `objective.md` from the answer. Don't ask anything else.

## 4.4 — Recompile

Run `hctl compile --target claude` to regenerate `CLAUDE.md` and `.claude/commands/*` from the populated `.holoctl/`.

# Step 5 — Show overview (always)

Run `hctl overview` and **show the full output to the user**. This is the canonical project snapshot:

- Project name, prefix, and holoctl version
- Objective (first paragraph from `objective.md`)
- Board counts by status
- Repos with branch + ticket count per repo
- Available agents
- Available slash commands (including `/holoctl`)
- Dashboard URL
- Suggested next action (stalled ticket, next p1, or "create your first ticket")

This replaces any manual summary you would have written. Don't paraphrase — show the actual output.

# Hard rules

- **Default = execute.** Don't pause unless one of the three checkpoints (4.1, 4.3, conflict) applies.
- **Show command output** so the user sees what happened.
- **Never overwrite** existing AI rules (`.cursor/rules/`, hand-edited `CLAUDE.md`, etc) — read for context only.
- **If `.holoctl/` already exists** when you tried to init, stop and ask whether to reuse, refresh, or abort. Don't blow away existing state.
- **Always end with `hctl overview`** — both for fresh init and for the inspect-mode path.

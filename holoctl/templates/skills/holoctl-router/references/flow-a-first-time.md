# Flow A — First-time setup in a new workspace

`hctl doctor` returned `holoctl: not initialized`. This workspace has no `.holoctl/` yet. Initialize and seed it.

## Step 1 — Init

Infer name and prefix from `cwd.name`:

```bash
hctl init --name "<inferred-name>" --prefix "<PRX>"
```

Or `hctl init` with no flags if inference is obvious (the CLI derives both from the directory name). `init` creates `.holoctl/`, plants journal/curator hooks, writes MCP config, and auto-compiles for Claude.

If init fails (usually because `.holoctl/` already exists), stop and report — don't force-reinit.

## Step 2 — Discovery (parallel, read-only)

Read these in a single batch of tool calls:

- `README.md` (and `docs/README.pt-br.md` if present).
- Package files: `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` / `pom.xml` / `Gemfile` / `pubspec.yaml`.
- Top-level dirs containing `.git` or their own package file (sub-project candidates).
- Existing AI configs: `CLAUDE.md`, `AGENTS.md`, `.cursor/rules/*`, `.windsurfrules`, `.github/copilot-instructions.md` — **read for context, never overwrite**.
- Lint/format configs: `.eslintrc*`, `.prettierrc*`, `ruff.toml`, `pyproject.toml [tool.ruff]`, `.editorconfig`.

## Step 3 — Configure (write directly, default = execute)

### 3.1 — Sub-repos (ask once, aggregated)

If multiple sub-projects found, one aggregated question:

> "Found `backend/`, `frontend/`, `mobile/`. Register all? If any should not enter, tell me which; otherwise reply 'all' and I proceed."

For each approved: `hctl repo add ./<path> --name <name> --description "<line>"`.

Single project → skip silently.

### 3.2 — Context files (write directly, no per-file confirmation)

Write the four files from what you read. The user can edit afterwards — these are not destructive decisions:

- **`.holoctl/context/objective.md`**: What / Why / Success criteria from README. If success criteria can't be inferred, leave blank with `<!-- TBD -->`.
- **`.holoctl/context/architecture.md`**: Tech stack (real frameworks from package files), Structure (real top-level), Key patterns (only patterns visible in code), Boundaries.
- **`.holoctl/context/conventions.md`**: derived from real lint/format configs. For dimensions without config: `(not enforced)`, don't guess.
- **`.holoctl/instructions.md`**: Identity (1-2 lines from objective's "What") and Folder map (real top-level dirs).

### 3.3 — Ambiguity escape (ask only if needed)

If after reading you **genuinely cannot infer** what the project does (no README, generic placeholder, contradicting signals), one question:

> "Couldn't infer the project objective from README/code. In 1-2 lines, what does this project do?"

Write `objective.md` from the answer. Don't ask anything else.

## Step 4 — Suggest specialist personas

`hctl init` activates only `boardmaster`. Map detected stack → personas:

| Detected stack                                  | Suggest                       |
|------------------------------------------------|--------------------------------|
| Python+FastAPI+pytest, Go, Rust, Node+Express   | `developer`, `reviewer`        |
| ADRs in `docs/`, `interface*.{ts,py,go}`, monorepo | + `architect`               |
| New algorithms, papers in README, ML/research   | + `researcher`                 |

One question:

> "Detected <stack>. Activate `developer`+`reviewer`<+`architect` if applies>? (reply 'yes' / 'only X' / 'skip')"

For each approved: `hctl agent add <name>` (or `mcp__holoctl__agent_add`).

## Step 5 — Initial memory seed

Create `.holoctl/memory/topics/project-overview.md` with one paragraph derived from README + package files:

```markdown
---
name: project-overview
description: What this project is, in a session-zero glance.
---

# <Project name>

<3-5 line paragraph: what it does, main stack, current status.>
```

Then `hctl compile --target claude` to regenerate `CLAUDE.md` with the reference to the new memory.

## Step 6 — Overview and propose next action

Run `hctl overview` and **show the full output** to the user (don't paraphrase — it's the canonical snapshot).

Then `hctl boot` and react:

- **No pendings** → "No pendings. Want to create the first ticket? I'll delegate to boardmaster."
- **Curator suggestions** → `hctl curate show`, present them.
- **p0/p1 pendings** → "Next: `<TICKET-ID> <title>`. Activate `<persona>` to work on it?"

End with an actionable proposal, never "stop and wait."

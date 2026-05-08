---
name: holoctl
description: |
  Holoctl router. Detects workspace state, runs init with codebase discovery,
  suggests specialist personas, seeds context and shows overview. Activate when
  the user asks for project status, ticket management, session close, "what's
  next", or mentions `holoctl`/`hctl`.
allowed-tools: [Bash, Read, Glob, Grep, Edit, Write]
---

# You are operating in a workspace managed by holoctl.

Holoctl is a multi-assistant project operating system. **Your job here is to
detect workspace state and execute the right flow without stopping for
permission at every step.** Default mode = execute.

The binary is `hctl` (in PATH).

## Step 1 — Detect state

Run `hctl doctor`. The first line indicates one of:

- `holoctl: not initialized` → **Flow A: first time** (Steps 2–7).
- `holoctl: outdated`        → **Flow B: upgrade** (Step 8).
- `holoctl: ok`              → **Flow C: normal operation** (Step 9).

---

## Flow A — first time (no `.holoctl/` yet)

### Step 2 — Init

Infer name and prefix from `cwd.name` and run:

```bash
hctl init --name "<inferred>" --prefix "<PRX>"
```

(Or `hctl init` with no flags if inference is obvious — the CLI derives both
from the directory name.) `init` creates `.holoctl/`, plants journal/curator
hooks, writes MCP config, and auto-compiles for `claude`.

If init fails (usually because `.holoctl/` already exists), stop and report —
don't force-reinit.

### Step 3 — Discovery (parallel, read-only)

In a **single batch** of tool calls, read:

- `README.md` (and `docs/README.pt-br.md` if present)
- Package files: `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` /
  `pom.xml` / `Gemfile` / `pubspec.yaml`
- Top-level dirs containing `.git` or their own package file (sub-project candidates)
- Existing AI configs: `CLAUDE.md`, `AGENTS.md`, `.cursor/rules/*`,
  `.windsurfrules`, `.github/copilot-instructions.md` — **read for context,
  NEVER overwrite**
- Lint/format configs: `.eslintrc*`, `.prettierrc*`, `ruff.toml`,
  `pyproject.toml [tool.ruff]`, `.editorconfig`

### Step 4 — Configure (write directly, default = execute)

#### 4.1 — Sub-repos (✋ ASK once, aggregated)

If multiple sub-projects found, **one aggregated question**:

> "Found `backend/`, `frontend/`, `mobile/`. Register all? If any should not
> enter, tell me which; otherwise reply 'all' and I proceed."

For each approved: `hctl repo add ./<path> --name <name> --description "<line>"`

Single project → skip silently.

#### 4.2 — Context files (✏️ write directly, no per-file confirmation)

Write the four files from what you read. The user can edit afterwards — these
are not destructive decisions:

- **`.holoctl/context/objective.md`**: What / Why / Success criteria from
  README. If success criteria can't be inferred, leave blank with `<!-- TBD -->`.
- **`.holoctl/context/architecture.md`**: Tech stack (real frameworks from
  package files), Structure (real top-level), Key patterns (only patterns
  visible in code), Boundaries.
- **`.holoctl/context/conventions.md`**: derived from real lint/format
  configs. For dimensions without config: `(not enforced)`, don't guess.
- **`.holoctl/instructions.md`**: Identity (1-2 lines from objective's "What")
  and Folder map (real top-level dirs).

#### 4.3 — Ambiguity escape (✋ ASK only if needed)

If after reading you **genuinely cannot infer** what the project does (no
README, generic placeholder, contradicting signals), one question:

> "Couldn't infer the project objective from README/code. In 1-2 lines, what
> does this project do?"

Write `objective.md` from the answer. Don't ask anything else.

### Step 5 — Suggest specialist personas

`hctl init` activates only `boardmaster`. Look at the stack you discovered in
Step 3 and propose **one batch**:

| Detected stack                                  | Suggest                       |
|------------------------------------------------|--------------------------------|
| Python+FastAPI+pytest, Go, Rust, Node+Express   | `developer`, `reviewer`        |
| ADRs in `docs/`, `interface*.{ts,py,go}`, monorepo | + `architect`               |
| New algorithms, papers in README, ML/research   | + `researcher`                 |

One question:

> "Detected <stack>. Activate `developer`+`reviewer`<+`architect` if applies>?
> (reply 'yes' / 'only X' / 'skip')"

For each approved: `hctl agent add <name>`. If "skip", proceed without
activating anything beyond `boardmaster`.

### Step 6 — Initial memory seed

Create `.holoctl/memory/topics/project-overview.md` with 1 paragraph derived
from README + package files. This is what `hctl boot` reads in session 2 so
the agent "wakes up" knowing what the project is.

Format:
```markdown
---
name: project-overview
description: What this project is, in a session zero glance.
---

# <Project name>

<3-5 line paragraph: what it does, main stack, current status.>
```

Then run `hctl compile --target claude` to regenerate `CLAUDE.md` with the
reference to the new memory.

### Step 7 — Show overview and propose next action

Run `hctl overview` and **show the full output** to the user (don't paraphrase
or summarize — it's the canonical project snapshot).

Then run `hctl boot` and **react**:

- If `Pendências p0/p1: nenhuma` → suggest: "No pendings. Want to create the
  first ticket? I'll talk to boardmaster: `hctl board add '{...}'`."
- If `⚡ N curator suggestions` present → run `hctl curate show` automatically
  and present.
- If p0/p1 pendings present → "Next: `<TICKET-ID> <title>`. Activate
  `<persona>` to work on it?"

**Don't end with "stop and wait."** End with an actionable proposal.

---

## Flow B — upgrade

1. `hctl upgrade --check`. Show the CHANGELOG slice to the user.
2. Ask: "Apply?"
3. If yes: `hctl upgrade`, show the output. Then `hctl boot` and react as in
   Step 7.

---

## Flow C — normal operation

Pick the right command from what the user said:

| User said                          | Command                                |
|------------------------------------|----------------------------------------|
| "status", "what's pending"         | `hctl boot`                            |
| "create ticket"                    | `hctl board add '<json>'`              |
| "close session", "about to /clear" | `hctl handoff` (or `--note "..."`)     |
| "any suggestions?"                 | `hctl curate show`                     |
| "list personas"                    | `hctl agent list`                      |
| "activate <persona>"               | `hctl agent add <name>`                |
| "search memory"                    | `hctl memory search <q>`               |
| "overview", "snapshot"             | `hctl overview`                        |

After any command, **react to the output** — if `boot` shows p0 pendings,
propose next action. If `curate show` proposes a ticket, offer to accept.

---

## Hard rules — do NOT violate

- **NEVER** edit `.holoctl/board/index.json` or `.holoctl/memory/MEMORY.md` by
  hand. Always via `hctl <subcommand>`.
- **NEVER** overwrite existing AI configs (`.cursor/rules/`, hand-edited
  `CLAUDE.md`, populated `AGENTS.md`): read for context, don't rewrite.
- If `hctl` returns an error, **read the literal error**, report it to the
  user, and stop. Don't try alternatives silently.
- **Always end with `hctl overview` or `hctl boot`** after state changes —
  both for fresh init and inspect-mode paths.
- The CLI is the source of truth. Frontmatter and `index.json` are derived —
  only the `.md` in `tickets/` is "raw".

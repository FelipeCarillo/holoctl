Onboard, configure or inspect projhub. **Default mode = execute.** Pause to ask only at the three checkpoints below.

# Step 1 — Detect state

Run `projhub doctor`. "No .projhub/ found" → Step 2. Otherwise → Step 5.

# Step 2 — Init

Infer name + prefix from `cwd.name` and run `projhub init --name "<n>" --prefix "<P>"` (or `projhub init` if obvious). Auto-compiles cursor target.

# Step 3 — Discover (read-only, parallel)

Read README, package files (package.json/pyproject.toml/Cargo.toml/etc.), top-level dirs (flag candidates with package files or `.git`), existing AI rules (`.cursor/rules/*`, `CLAUDE.md`, `.windsurfrules` — never overwrite), lint configs.

# Step 4 — Configure (execute by default)

**4.1 Sub-repos (✋ ASK once, aggregated)**: if multi-project, ask one question listing all candidates. For each approved: `projhub repo add ./<path> --name <n> --description "<one-line>"`. Single project → skip silently.

**4.2 Context files (write directly)**:
- `.projhub/context/objective.md` — What/Why/Success criteria from README
- `.projhub/context/architecture.md` — real Tech stack, Structure, Patterns, Boundaries; mark unclear `(TBD with team)`
- `.projhub/context/conventions.md` — from real configs; missing dimensions `(not enforced)`
- `.projhub/instructions.md` — Identity + Folder map

**4.3 Ambiguity escape (✋ ASK only if needed)**: if you genuinely cannot infer what the project does, ask one question for the objective. Otherwise write directly.

**4.4** `projhub compile --target cursor`.

# Step 5 — Show overview (always)

Run `projhub overview` and show the full output. Single canonical snapshot: project name, board counts, repos, agents, slash commands, dashboard URL, suggested next.

# Hard rules
- Default = execute. Show command output. Never overwrite existing AI rules.
- If `.projhub/` already exists when initing, stop and ask before touching state.
- Always end with `projhub overview`.

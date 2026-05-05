Onboard, configure or inspect projhub for the current project. **This command requires interaction — never write context files or register repos without explicit user confirmation.**

# Step 1 — Detect state

Run `projhub doctor`.
- "No .projhub/ found" → go to Step 2.
- Returns checks → go to Step 5.

# Step 2 — Confirm before init

ASK: "Nome do projeto e prefix dos tickets (ex: MP → MP-001)? Ou prefere que eu infira do diretório?"

Then `projhub init --name "<name>" --prefix "<PREFIX>"` (auto-compiles cursor target).

# Step 3 — Discover (read-only)

Read in parallel: README, package files (package.json/pyproject.toml/Cargo.toml/etc.), top-level dirs, existing AI rules (`.cursor/rules/*`, `CLAUDE.md`, `.windsurfrules`), lint configs. **Do not overwrite existing AI instructions.**

# Step 4 — Configure with confirmation gates

For each sub-step: propose → show → confirm → write. One at a time.

## 4.1 — Sub-repos

If multi-project, list candidates and ASK which to register. Then `projhub repo add ./<path> --name <name> --description "<one-line>"`.

## 4.2 — `objective.md`

Draft What/Why/Success criteria from README. Show, confirm, write.

## 4.3 — `architecture.md`

Tech stack, Structure, Key patterns, Boundaries. Use only patterns visible in code; mark unclear items `(TBD with team)`. Show, confirm, write.

## 4.4 — `conventions.md`

Derive from real configs. Mark dimensions without config `(not enforced)`. Don't invent.

## 4.5 — `instructions.md`

Fill Identity + Folder map. Leave Decisions empty unless user dictates one now.

## 4.6 — Recompile

`projhub compile --target cursor`.

# Step 5 — Inspect (already initialized)

`projhub board stat`, `projhub board ls --status doing`, `projhub repo list`, `projhub agent list`. Suggest next action.

# Step 6 — Final report

✅ what was set up · 🌐 dashboard at http://127.0.0.1:4242 via `projhub serve` · 🎯 next action.

# Hard rules
- Show command output.
- Never write context files without confirmation.
- Never register repos silently.
- Never overwrite existing AI rules — read for context only.

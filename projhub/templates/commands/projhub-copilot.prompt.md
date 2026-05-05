---
mode: agent
description: Onboard, configure or inspect projhub for the current project
---

**This command requires interaction — never write context files or register repos without explicit user confirmation.**

# Step 1 — Detect state

Run `projhub doctor`. "No .projhub/ found" → Step 2. Otherwise → Step 5.

# Step 2 — Confirm before init

ASK: "Nome do projeto e prefix dos tickets? Ou inferir do diretório?" Then `projhub init --name "<n>" --prefix "<P>"` (auto-compiles copilot).

# Step 3 — Discover (read-only)

Read README, package files, top-level dirs, existing AI rules (`.github/copilot-instructions.md`, `CLAUDE.md`), lint configs. **Don't overwrite existing AI rules.**

# Step 4 — Configure with confirmation gates

For each sub-step: propose → show → confirm → write. One at a time.

- **4.1 Sub-repos**: list candidates, ASK which to register, then `projhub repo add ./<path> --name <n> --description "<one-line>"`.
- **4.2 `objective.md`**: What/Why/Success criteria from README.
- **4.3 `architecture.md`**: Tech stack, Structure, Patterns, Boundaries. Mark unclear `(TBD with team)`.
- **4.4 `conventions.md`**: From real configs. Mark missing dimensions `(not enforced)`.
- **4.5 `instructions.md`**: Identity + Folder map.
- **4.6** `projhub compile --target copilot`.

# Step 5 — Inspect (already initialized)

`projhub board stat`, `board ls --status doing`, `repo list`, `agent list`. Suggest next action.

# Step 6 — Final report

✅ what was set up · 🌐 http://127.0.0.1:4242 via `projhub serve` · 🎯 next action.

# Hard rules
- Show command output.
- Never write context files without confirmation.
- Never register repos silently.
- Never overwrite existing AI rules.

---
description: Initialize, inspect, or onboard projhub in the current project directory
---

**You are responsible for actually populating the project context — `projhub init` only creates skeleton files.**

# Step 1 — Detect state

Run `projhub doctor`. If it errors with "No .projhub/ found", treat as **uninitialized**.

# Step 2 — Initialize (if uninitialized)

Run `projhub init`. This auto-runs `projhub compile --target windsurf`.

# Step 3 — Onboard (CRITICAL)

Read the codebase (README, package files, top-level dirs, existing AI rules) and POPULATE:

- `.projhub/context/objective.md` — What/Why/Success criteria, derived from real README and code
- `.projhub/context/architecture.md` — real tech stack, real folder structure, real patterns
- `.projhub/context/conventions.md` — derived from .eslintrc / ruff.toml / .editorconfig (write `(not enforced)` instead of guessing)
- `.projhub/instructions.md` — fill Identity and Folder map
- Register sub-repos with `projhub repo add` if multi-package

Then run `projhub compile --target windsurf` to regenerate `.windsurfrules`.

# Step 4 — Inspect (if already initialized)

`projhub board stat`, `projhub board ls --status doing`, `projhub agent list`, `projhub repo list`. Suggest next action.

# Step 5 — Final report

- ✅ what was set up
- 🌐 dashboard: `http://127.0.0.1:4242` via `projhub serve`
- 🎯 suggested next action

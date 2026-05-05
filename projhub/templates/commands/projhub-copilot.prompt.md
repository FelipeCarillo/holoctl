---
mode: agent
description: Onboard, configure or inspect projhub for the current project
---

**Default mode = execute.** Pause to ask only at the three checkpoints below.

# Step 1 — Detect state

`projhub doctor`. "No .projhub/ found" → Step 2. Otherwise → Step 5.

# Step 2 — Init

Infer name + prefix; `projhub init --name "<n>" --prefix "<P>"`. Auto-compiles copilot.

# Step 3 — Discover (read-only)

Read README, package files, top-level dirs (flag candidates with package files or `.git`), existing AI rules (`.github/copilot-instructions.md`, `CLAUDE.md` — never overwrite), lint configs.

# Step 4 — Configure (execute by default)

- **4.1 Sub-repos (✋ ASK once)**: if multi-project, one aggregated question; then `projhub repo add ./<path> --name <n> --description "<one-line>"` for each approved. Single project → skip.
- **4.2 Context files (write directly)**: `objective.md`, `architecture.md`, `conventions.md`, `instructions.md`.
- **4.3 Ambiguity escape (✋ ASK only if needed)**: if unable to infer the objective, ask once. Otherwise write directly.
- **4.4** `projhub compile --target copilot`.

# Step 5 — Show overview (always)

Run `projhub overview` and show the full output. Single canonical snapshot: project name, board counts, repos, agents, slash commands, dashboard URL, suggested next.

# Hard rules
- Default = execute. Show command output. Never overwrite existing AI rules. If `.projhub/` exists when initing, ask before touching it. Always end with `projhub overview`.

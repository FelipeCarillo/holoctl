---
name: holoctl
description: Onboard, configure or inspect holoctl for the current project
---

**Default mode = execute.** Pause to ask only at the three checkpoints below.

# Step 1 — Detect state

`holoctl doctor`. "No .holoctl/ found" → Step 2. Otherwise → Step 5.

# Step 2 — Init

Infer name + prefix; `holoctl init --name "<n>" --prefix "<P>"`.

# Step 3 — Discover (read-only)

Read README, package files, top-level dirs (flag candidates with package files or `.git`), existing AI rules (`AGENTS.md`, `.devin/skills/*`, `CLAUDE.md` — never overwrite), lint configs.

# Step 4 — Configure (execute by default)

- **4.1 Sub-repos (✋ ASK once)**: if multi-project, one aggregated question; then `holoctl repo add ./<path> --name <n> --description "<one-line>"` for each approved. Single project → skip.
- **4.2 Context files (write directly)**: `objective.md`, `architecture.md`, `conventions.md`, `instructions.md`.
- **4.3 Ambiguity escape (✋ ASK only if needed)**: if unable to infer the objective from README/code, ask once. Otherwise write directly.
- **4.4** `holoctl compile --target devin` (regenerates `AGENTS.md` and `.devin/skills/<name>/SKILL.md`).

# Step 5 — Show overview (always)

Run `holoctl overview` and show the full output. Single canonical snapshot: project name, board counts, repos, agents, slash commands, dashboard URL, suggested next.

# Hard rules
- Default = execute. Show command output. Never overwrite existing AI rules. If `.holoctl/` exists when initing, ask before touching it. Always end with `holoctl overview`.

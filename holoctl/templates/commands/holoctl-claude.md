---
name: holoctl
description: |
  Holoctl router. Detects workspace state via `hctl doctor` and routes to the
  right flow (init / upgrade / normal operation).
allowed-tools: [Bash, Read, Glob, Grep, Edit, Write]
---

# /holoctl

Invoke the **holoctl-router** skill — it has the complete router logic with progressive disclosure for first-time setup, upgrades, and daily operations.

To invoke: read the skill's main entry. Try in order:

1. `Read .claude/skills/holoctl-router/SKILL.md` — project-local (preferred when present).
2. `Read ~/.claude/skills/holoctl-router/SKILL.md` — global (fallback).

Follow the instructions in whichever you find. The skill itself decides which references (Flow A / Flow B) to load lazily based on `hctl doctor` output.

If neither path exists, run `hctl setup-global --target claude` to install the global router, then retry.

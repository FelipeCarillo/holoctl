---
name: holoctl-memory-discipline
description: |
  Use when the user makes a durable decision, states a project rule, or
  shares context that future sessions will need ("vamos sempre X", "decidi Y",
  "lembra que Z"). Promotes the right material to the right surface: ADR for
  hard locks, memory topic for soft durable context.
---

# Memory discipline — promote durable context to the right surface

## When this fires

The user said something that **won't be in context next session** but matters:

- Decision: "vamos sempre usar X em vez de Y", "decidi que…", "we're going with…"
- Rule: "always do A when B", "never C in the D layer"
- Context: "lembra que…", "for future reference…", "FYI on…"

If it's session-local (current bug, in-progress idea), skip — let it die.

## Decide: ADR or memory?

**ADR** (`.holoctl/context/decisions/`) is for:
- **Hard locks** — decisions you don't want overturned without explicit review.
- Architectural directions ("Postgres over Mongo because…").
- Trade-offs with rationale that future contributors should see.
- Anything you'd want to find in 6 months by searching `decisions/`.

→ Call `/decision <one-line summary>`. The slash command creates the ADR with structured Context/Decision/Implications.

**Memory topic** (`.holoctl/memory/topics/`) is for:
- Soft durable context that informs work without locking direction.
- Naming/style conventions visible only in convention, not in lint.
- Project lore: "the X module was extracted from Y to avoid Z circular dep".
- Anything the assistant should know but isn't a hard rule.

→ Call `mcp__holoctl__memory_add({"name":"<slug>","body":"<markdown>","scope":"lazy","description":"<1 line>"})`.

Scopes:
- `lazy` — loaded when relevant; most things go here.
- `glob` — pass `globs: ["src/api/**"]` for path-scoped rules.
- `always_on` — use sparingly; this enters every context.

## Don't

- Don't promote ephemeral state ("currently debugging X") to memory or ADR.
- Don't ask the user every time — make the call, announce it briefly: "Promoting to memory: `<topic-name>`."
- Don't duplicate the same fact in CLAUDE.md and memory. CLAUDE.md is invariants only; memory is the durable layer.
- Don't write to memory by editing files directly — `permissions.deny` blocks `.holoctl/memory/MEMORY.md` writes; use `memory_add`.

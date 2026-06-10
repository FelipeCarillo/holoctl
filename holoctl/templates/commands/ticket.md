---
name: ticket
description: "Create a new ticket — single or parallel batch, decided by the parallel-evaluator + boardmaster"
arguments: "<title>"
allowed-tools: [Bash, mcp__holoctl__board_list, mcp__holoctl__board_create, mcp__holoctl__board_batch]
---

# /ticket

1. **Evaluate parallelization first.** Trigger the `holoctl-parallel-evaluator` skill: can this work split into N disjoint pieces? Propose the partition (or single) before calling boardmaster.

2. **Collect inputs** if not already clear from the argument and context: `title`, `priority` (`p0..p3`), `agent`, `acceptance` (1-5 verifiable criteria). Ask the user **once** with all gaps in one batched question. Never guess.

3. **Delegate to boardmaster**, passing the request + the parallel-evaluator's verdict (single OR candidate batch). The boardmaster calls `mcp__holoctl__board_create` or `mcp__holoctl__board_batch`.

4. **Confirm in one line per ticket**: `{{project.prefix}}-NNN created: <title> (agent=<name>, priority=<pN>)`.

The boardmaster owns the schema — see `.claude/agents/boardmaster.md` for what fields are auto vs user-set. You never type `id`, `created`, `updated`, `status` — those come from the CLI/MCP.

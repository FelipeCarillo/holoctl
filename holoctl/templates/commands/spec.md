---
name: spec
description: "Spec-Driven Development entry point — turn an external board item (or a fresh idea) into a spec + child tasks ready to execute"
arguments: "[<external-board-url-or-ref>]"
allowed-tools: [Bash, Read, Glob, mcp__holoctl__board_create, mcp__holoctl__board_batch, mcp__holoctl__board_show, mcp__holoctl__board_children, mcp__holoctl__board_list]
---

# /spec

Turn a request from an external board (Trello/Linear/Azure DevOps/Jira/GitHub/Slack — or just a pasted user story) into a structured **spec** in `.holoctl/`, then decompose it into parallel-safe child tasks ready for execution.

## Step 1 — Source intake

**Always try MCP first.** Invoke the `holoctl-provider-mcp` skill before asking for paste:

1. Pass the user's input (URL or ref) to the provider-mcp skill.
2. The skill consults `mcp__holoctl__config_show()` for the provider catalog, matches the URL against each provider's `url_pattern`, and probes the configured `mcp_fetch_tool`.
3. If the MCP tool is connected → use the returned body directly, with `source_*` pre-filled.
4. If the MCP tool isn't connected → fall back to "paste the content here" with `source_*` still set from the URL match (so traceability is preserved even without MCP).

If no argument is given: assume the user is pasting a story / request in the conversation. Set `source_provider="manual"`.

## Step 2 — Discuss to refine

Reach agreement on (one batched question, never piecewise):

- **Scope** — what's in, what's out
- **Acceptance criteria** — 3-7 verifiable items
- **Files / modules** — paths the work will touch (use `Glob` to confirm they exist)
- **Edge cases** worth surfacing
- **Risks / unknowns** worth flagging

Don't ask if you can already infer from the source content. Default to executing, ask only when ambiguity is real.

## Step 3 — Materialize the spec

```
mcp__holoctl__board_create({
  "title": "<spec title>",
  "kind": "spec",
  "agent": "architect",
  "priority": "<pN>",
  "acceptance": ["<refined criterion 1>", "<refined criterion 2>", ...],
  "context": "<consolidated discussion + scope + edge cases>",
  "out_of_scope": "<what NOT to do>",
  "files": ["<file 1>", "<file 2>"],
  "source_provider": "<provider or 'manual'>",
  "source_ref": "<ref or null>",
  "source_url": "<url or null>",
  "source_label": "<label or null>"
})
```

Capture the returned `SPEC_ID` ({{project.prefix}}-NNN).

## Step 4 — Hand off to boardmaster for decomposition

Trigger the `holoctl-parallel-evaluator` skill. Then delegate to boardmaster with the spec as parent:

```
mcp__holoctl__board_batch({
  "shared": {
    "parent": "<SPEC_ID>",
    "kind": "task",
    "source_provider": "<inherited>",
    "source_ref": "<inherited>",
    "tags": ["spec:<SPEC_ID>"]
  },
  "tickets": [
    {"title": "...", "agent": "developer", "priority": "p1",
      "files": ["..."], "acceptance": ["..."]},
    ...
  ]
})
```

Children inherit `parent` + `source_*` from `shared` — no need to repeat per-ticket.

## Step 5 — Confirm and propose execution

Report in one block:

```
Spec: {{project.prefix}}-NNN <title> (source: <provider>:<ref>)
Children: <N> tasks created
  {{project.prefix}}-NNN+1: <title> (agent=developer, files=...)
  {{project.prefix}}-NNN+2: <title> (agent=developer, files=...)
  ...

Next: activate <developer> on {{project.prefix}}-NNN+1? (or `hctl agent add` first)
```

End with the actionable proposal. The execution itself happens via subagent (Task tool) — not your job here.

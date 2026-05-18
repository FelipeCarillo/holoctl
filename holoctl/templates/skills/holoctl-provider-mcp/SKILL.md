---
name: holoctl-provider-mcp
description: |
  Use when the user pastes a URL from an external board (Linear, GitHub,
  Trello, Azure DevOps, Jira, Slack, or a custom internal board) or refs
  a card by id. Detects the provider via configured URL patterns, probes
  whether the provider's MCP tool is connected in Claude Code, and either
  fetches the card body via that MCP or falls back to asking for paste.
  Pre-fills source_* fields on the resulting work item.
---

# Provider MCP discovery

Bridge between the user's external board and the holoctl work-item model. The transport (the MCP server itself) lives in Claude Code's `.mcp.json` — this skill just declares what URL patterns map to what MCP tools and tries to use them.

## Step 1 — Read the provider catalog

```
mcp__holoctl__config_show()  // returns the resolved config
```

Extract `providers`. Each entry has:

- `enabled` — `auto` (probe at runtime), `always` (assume tool exists), `disabled` (skip).
- `url_pattern` — Python regex with at least `(?P<ref>...)`.
- `mcp_fetch_tool` — name of the MCP tool to call.
- `mcp_search_tool` — optional, for keyword search.
- `label_template` — `"{ref}: {title}"` style template.

Shipped defaults cover **Linear, GitHub, Trello, Azure DevOps, Jira, Slack**. The user may have added custom providers (e.g. an internal company board) via `hctl provider add`.

## Step 2 — Match the input

The user passed either:

- A full URL (e.g. `https://linear.app/eng/issue/ENG-42`), OR
- A ref alone (e.g. `ENG-42`) — disambiguate by asking which provider, OR
- Free-form text — skill should not fire; let `/spec` handle paste.

For each provider entry with `enabled` in `{"auto", "always"}`:

- Test `url_pattern` against the input. On match, capture `ref` and any other named groups.
- Record `source_provider = <name>`, `source_ref = <ref>`, `source_url = <full URL>` as candidates.

If multiple providers match, pick the most specific (longest pattern). If none, skip to paste fallback.

## Step 3 — Probe the MCP tool

Try calling the provider's `mcp_fetch_tool` with the captured ref. Standard shape:

```
<mcp_fetch_tool>({"id": "<ref>"})
```

Some providers might want different arg names (`issue_id`, `cardId`, `key`). If the first attempt returns a schema error rather than "unknown tool", try the alternative shape. If after 2 attempts it still fails, fall back to paste.

### Tool not present

Claude Code will return something like `Tool 'mcp__linear__get_issue' not found.` That's the signal — the user hasn't connected this provider's MCP. Fall back gracefully:

> "Provider `linear` detected from URL, but the Linear MCP isn't connected in Claude Code (`.mcp.json`). Paste the card body here and I'll proceed:"

If `enabled` was `always` (user explicitly asserted the tool exists), surface the failure as an error instead of falling back silently.

### Tool present and successful

Use the returned fields. Typical shape (varies per provider):

```json
{ "title": "...", "body": "...", "url": "...", "author": "...", "labels": [...], ... }
```

Compose `source_label` via the configured template:

```
label = label_template.format(**captures, **response_fields)
```

Use the `body` field (or `description`, `content`, etc. — whatever the provider returns) as the spec body for `/spec`.

## Step 4 — Hand off to `/spec`

Pass to the spec flow:

- `source_provider`, `source_ref`, `source_url`, `source_label` — populated.
- Card body — as the input to the "discuss to refine" step.

The user still gets to refine scope/acceptance via the normal `/spec` discussion. The MCP fetch just skipped the paste.

## Step 5 — Optional: search

When the user types something like "find me cards about auth" without a specific ref, try `mcp_search_tool` if configured. Less common path — most invocations are one-card.

## Don't

- Don't pretend to fetch when the MCP isn't there — always fall back honestly.
- Don't write `source_*` fields when you only have a URL — only when you've extracted a valid `ref` via the pattern.
- Don't bypass `/spec` after fetching — the discuss step is still where scope gets agreed. The fetch just saves typing.
- Don't probe `disabled` providers — they're disabled for a reason.

## Adding a new provider on the fly

If the user pastes a URL that doesn't match any configured provider, AND it looks like a card from an unknown system, offer:

> "URL doesn't match any provider in the catalog. Want me to add a new provider? Run `hctl provider add <name> --mcp-fetch <mcp-tool> --url-pattern '<regex>'`."

Don't guess the MCP tool name — the user knows.

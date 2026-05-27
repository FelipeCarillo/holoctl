---
name: holoctl-foreign-bootstrap
description: |
  Use when you are an AI coding assistant that is NOT Claude Code, operating in
  a repo that contains a `.holoctl/` directory (or whose `AGENTS.md` points
  here). holoctl natively materializes only Claude Code's config (`.claude/` +
  `CLAUDE.md`); this skill teaches any other assistant (Copilot, Codex, Cursor,
  Aider, Zed, Windsurf, …) to read the canonical source in `.holoctl/` and
  generate its OWN native config dir from it.
---

# Bootstrap a non-Claude assistant from a holoctl workspace

This repo is managed by **holoctl**. The canonical source of truth lives in
`.holoctl/` — it is tool-neutral. holoctl's CLI (`hctl`, on PATH) compiles that
source into **Claude Code's** native files only (`CLAUDE.md`, `.claude/`).

If you are Claude Code, ignore this skill — your config is already in `.claude/`.

If you are **any other assistant**, you have no compiler maintained for you.
Instead, do the translation yourself: read `.holoctl/` and write the equivalent
into your own tool's native config location. Read **`.holoctl/`** as the source —
NOT `.claude/` (that one is already shaped for Claude).

## Step 1 — read the canonical source

Read these, in order, skipping any that don't exist:

1. `.holoctl/instructions.md` — the project's primary agent instructions (objective, architecture, conventions, merged).
2. `.holoctl/context/*.md` — `objective.md`, `architecture.md`, `conventions.md` and any `documents/`.
3. `.holoctl/agents/*.md` — active personas (each has `name` / `description` / `tools` / `paths` frontmatter).
4. `.holoctl/memory/MEMORY.md` — always-on durable memory index, plus `.holoctl/memory/topics/*.md` (each topic has a `scope:` of `always_on` / `lazy` / `glob`).
5. `.holoctl/commands/*.md` — reusable slash-command-style workflows.

## Step 2 — materialize into your native config dir

Write the content into the location **your** tool reads. Pick your row:

| Your tool                 | Where to write                                                                 |
|---------------------------|---------------------------------------------------------------------------------|
| GitHub Copilot            | `.github/copilot-instructions.md` (from instructions.md) + `.github/prompts/<name>.prompt.md` (one per command) + `.github/instructions/holoctl-memory-<topic>.instructions.md` with `applyTo:` (one per glob/always_on topic) |
| OpenAI Codex              | `.codex/AGENTS.override.md` (instructions + inlined memory index + persona list) + `.codex/config.toml` (`[mcp_servers.holoctl]`) |
| Cursor                    | `.cursor/rules/*.mdc` (instructions + per-glob memory as scoped rules)          |
| Aider / Zed / Junie / goose / other AGENTS.md-aware | the root `AGENTS.md` already carries the pointer; inline the instructions there if your tool needs more |
| anything else             | follow your tool's documented "project instructions" convention, using `.holoctl/instructions.md` as the body |

For exact frontmatter and MCP-server snippets per tool, see **Per-tool format
hints** — in `references/format-hints.md`, or appended at the end of this file
(if you're reading `.holoctl/foreign-bootstrap.md`).

## Step 3 — wire up the holoctl MCP server (optional but recommended)

holoctl ships a stdio MCP server (`hctl serve --mcp`) exposing board / memory /
journal / curator tools. If your tool supports MCP, register it in your native
MCP config with:

```
command = "hctl"   (or $HOLOCTL_BIN if hctl isn't on PATH)
args    = ["serve", "--mcp"]
```

If your tool doesn't speak MCP, the `hctl` CLI is the full fallback — every MCP
tool maps 1:1 to an `hctl` subcommand.

## Hard rules (never violate)

- **Never** edit `.holoctl/board/index.json` or `.holoctl/memory/MEMORY.md` by
  hand — they are derived. Use `hctl <subcommand>` (e.g. `hctl board add`,
  `hctl memory add`).
- **Never** read `.holoctl/board/tickets/<ID>-*.md` directly — use
  `hctl board show <ID>`.
- Treat the files you generate (`.github/…`, `.codex/…`, `.cursor/…`) as
  **derived**. Re-run this bootstrap after `hctl upgrade` (or whenever
  `.holoctl/` changes) to keep them in sync. Don't hand-edit them — change
  `.holoctl/` and regenerate.
- If `hctl` returns an error, read the literal error, report it, and stop.

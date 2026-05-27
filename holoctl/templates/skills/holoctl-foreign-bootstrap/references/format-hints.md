# Per-tool format hints

Concrete frontmatter and file shapes for materializing `.holoctl/` into each
assistant's native config. Source body always comes from `.holoctl/` — these
just describe the envelope each tool expects.

## GitHub Copilot

- **Instructions:** `.github/copilot-instructions.md` — plain Markdown, body =
  `.holoctl/instructions.md`. No frontmatter.
- **Commands → prompts:** for each `.holoctl/commands/<name>.md`, write
  `.github/prompts/<name>.prompt.md` with frontmatter:
  ```
  ---
  description: "<one line from the command>"
  mode: "agent"
  ---
  ```
- **Memory topics → scoped instructions:** for each topic in
  `.holoctl/memory/topics/`, write
  `.github/instructions/holoctl-memory-<topic>.instructions.md`:
  ```
  ---
  applyTo: "<comma-joined globs for glob scope, else **>"
  description: "<topic description>"
  ---
  ```
  followed by the topic body.
- **MCP:** `.vscode/mcp.json`
  ```json
  { "servers": { "holoctl": { "command": "hctl", "args": ["serve", "--mcp"] } } }
  ```

## OpenAI Codex

- **Override instructions:** `.codex/AGENTS.override.md` — Codex merges this on
  top of the root `AGENTS.md`. Put the `.holoctl/instructions.md` body here.
  Codex can't lazy-load skills, so **inline** the memory index
  (`.holoctl/memory/MEMORY.md`) and a one-line list of active personas
  (`.holoctl/agents/*.md`) into this file.
- **MCP:** `.codex/config.toml`
  ```toml
  [mcp_servers.holoctl]
  command = "hctl"
  args = ["serve", "--mcp"]
  ```
  Preserve any other `[mcp_servers.*]` / `[section]` tables already present.

## Cursor

- **Rules:** `.cursor/rules/holoctl.mdc` — body = `.holoctl/instructions.md`.
- **Memory globs → scoped rules:** for each `glob` topic, a `.mdc` rule with
  `globs:` frontmatter matching the topic's globs.

## Generic AGENTS.md-aware tools (Aider, Zed, Junie, Jules, Factory, goose, …)

The root `AGENTS.md` emitted by holoctl is a minimal discovery shim pointing
here. If your tool needs the full context inline (not just the pointer), append
the `.holoctl/instructions.md` body and the memory index into `AGENTS.md` under
your own clearly-marked block — but treat it as derived and regenerate on change.

## Notes

- `$HOLOCTL_BIN` overrides the `hctl` command when it isn't on PATH.
- Every MCP tool has a CLI equivalent (`mcp__holoctl__board_create` →
  `hctl board add`, etc.), so MCP is optional.

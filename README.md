# projctl

Universal project operating system for AI coding assistants.

**One source of truth** (`.projctl/`) that **compiles** to any AI tool's native format — Claude Code, Cursor, Windsurf, GitHub Copilot, Devin, Aider, or generic markdown.

## What it does

- **Kanban board** that AI agents operate via CLI (dual-write JSON + markdown tickets)
- **Agent definitions** in a universal format that compile to tool-specific configs
- **Slash commands** that work across any AI assistant
- **Project context** management (objectives, architecture, decisions, conventions)
- **Multi-project workspace** — manage all your projects from one place
- **Web dashboard** with live kanban, agent registry, and activity timeline *(coming soon)*

## Quick start

```bash
# Initialize in any project
npx projctl init --name "MyApp" --prefix MA

# Create a ticket
projctl board add '{"title":"Build login page","agent":"developer","priority":"p1"}'

# See the board
projctl board ls

# Move a ticket
projctl board move MA-001 doing

# Compile to your AI tool
projctl compile --target claude    # generates .claude/ + CLAUDE.md
projctl compile --target cursor    # generates .cursorrules (coming soon)

# Check health
projctl doctor
```

## How it works

```
Your AI Agent (Claude Code / Cursor / Windsurf / etc.)
       │
       │ reads compiled files (.claude/, .cursorrules, etc.)
       │ operates board via CLI (projctl board ...)
       │
       ▼
┌─────────────────────────────────┐
│  .projctl/  (source of truth)   │
│  ├── config.json                │
│  ├── board/ (tickets + index)   │
│  ├── agents/ (universal format) │
│  ├── commands/ (universal)      │
│  ├── context/ (docs, decisions) │
│  └── instructions.md            │
└─────────────────────────────────┘
       │                    │
  projctl compile      projctl serve
       │                    │
       ▼                    ▼
Tool-specific files    Web Platform
(.claude/, .cursor/)   (localhost:4242)
```

`.projctl/` is the **single source of truth**. Tool-specific files are compiled output — never edit them directly.

## CLI Reference

### Board operations

```bash
projctl board stat                         # ticket counts by status
projctl board get <ID>                     # full ticket as JSON
projctl board ls [filters]                 # list tickets
  --sprint <name>                          # filter by sprint
  --status <status>                        # filter by status
  --agent <name>                           # filter by assigned agent
  --tag <tag>                              # filter by tag
  p0 | p1 | p2 | p3                       # filter by priority
projctl board move <ID> <status>           # move ticket (dual-write)
projctl board set <ID> <field> <value>     # update any field
projctl board add '<json>'                 # create ticket (auto-ID)
projctl board next-id                      # next available ID
projctl board rebuild-index                # rebuild index from .md files
```

### Project management

```bash
projctl init [--name X] [--prefix X]       # initialize .projctl/
projctl compile [--target claude]          # compile to tool-specific files
projctl doctor                             # health check
projctl agent list                         # list configured agents
projctl agent add <name>                   # create new agent definition
projctl workspace list                     # list all registered projects
projctl workspace add [path]               # register a project
projctl serve                              # web dashboard (coming soon)
```

## Agent format

Agents are defined in `.projctl/agents/<name>.md` with YAML frontmatter:

```yaml
---
name: developer
description: "General-purpose code implementation agent."
model: standard          # fast | standard | reasoning
tools: [read, search, edit, write, shell]
trigger: ticket          # ticket | natural-language | schedule
---

# Identity
You are the **Developer** for {{project.name}}. ...

# Guard Rail
You only begin work if you receive a ticket...

# Report Format
- **Done**: file:line bullets
- **Definition of Done**: [x]/[ ] per item
- **Suggested next step**: 1 line
```

Model tiers compile to tool-specific models:

| Tier | Claude Code | Cursor | Generic |
|------|------------|--------|---------|
| fast | haiku | gpt-4o-mini | fast |
| standard | sonnet | gpt-4o | standard |
| reasoning | opus | o3 | reasoning |

## Compile targets

| Target | Output |
|--------|--------|
| `claude` | `.claude/agents/*.md` + `.claude/commands/*.md` + `CLAUDE.md` |
| `cursor` | `.cursor/rules/*.md` + `.cursorrules` *(coming soon)* |
| `windsurf` | `.windsurfrules` *(coming soon)* |
| `copilot` | `.github/copilot-instructions.md` *(coming soon)* |
| `devin` | `devin.md` *(coming soon)* |
| `aider` | `CONVENTIONS.md` *(coming soon)* |
| `generic` | `AGENTS.md` + `COMMANDS.md` + `AI-INSTRUCTIONS.md` |

## Ticket format

```yaml
---
id: MA-001
title: Build login page
agent: developer
status: backlog
priority: p1
sprint: null
tags: auth, frontend
---

# Start
(Current state before starting)

# Goal — Definition of Done
- [ ] Login form with validation
- [ ] JWT auth flow working
- [ ] Lint and build pass

# Context
(Why this ticket exists)
```

## License

MIT

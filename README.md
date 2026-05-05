# projhub

> Universal project operating system for AI coding assistants.

<p>
  <a href="./README.md"><img src="https://img.shields.io/badge/lang-English-blue?style=flat-square" alt="English"/></a>
  <a href="./README.pt-br.md"><img src="https://img.shields.io/badge/lang-Português-green?style=flat-square" alt="Português"/></a>
</p>

[![PyPI version](https://img.shields.io/pypi/v/projhub.svg)](https://pypi.org/project/projhub/)
[![PyPI downloads](https://img.shields.io/pypi/dm/projhub.svg)](https://pypi.org/project/projhub/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-brightgreen.svg)](https://www.python.org)

---

## What is projhub?

**projhub** is a CLI tool that turns any directory into a fully structured AI-ready project. It gives you a Kanban board, agent definitions, slash commands, and a live web dashboard — all version-controlled in `.projhub/` alongside your code.

One project root. Any number of sub-repos and directories underneath. One `/projhub` slash command to set it all up inside Claude Code.

```
my-project/              ← project root (projhub init here)
├── backend/             [git · Node]
├── frontend/            [git · React]
├── mobile/              [git · React Native]
├── infra/               [Terraform]
├── .projhub/            ← all project state lives here
│   ├── config.json
│   ├── board/
│   │   └── tickets/
│   ├── agents/
│   ├── commands/
│   └── context/
└── README.md
```

---

## Install

Recommended (handles PATH automatically):

```bash
uv tool install projhub
```

Or with pip:

```bash
pip install projhub
```

After install, set up the global `/projhub` slash command:

```bash
projhub setup-global
```

This places a `/projhub` command in `~/.claude/commands/projhub.md` so you can run it from any project in Claude Code.

> Cursor, Windsurf, and GitHub Copilot don't support globally-installed slash commands. For those tools, use `projhub compile` inside each project to generate the project-level integration files (see **AI Tool Integration** below).

---

## Quick Start

```bash
# 1. Go to your project root
cd ~/my-project

# 2. Initialize
projhub init

# 3. Open the dashboard
projhub serve
# → http://127.0.0.1:4242

# 4. Compile for your AI tool(s)
projhub compile --target claude    # CLAUDE.md + .claude/commands/
projhub compile --target cursor    # .cursor/commands/ + .cursor/rules/
projhub compile --target windsurf  # .windsurfrules
projhub compile --target copilot   # .github/copilot-instructions.md
projhub compile --target devin     # AGENTS.md + .devin/skills/
```

Or just type `/projhub` in Claude Code — it detects, initializes, and compiles automatically.

---

## Features

### 📋 Kanban Board

Ticket management built for AI agents. Every ticket is a Markdown file with frontmatter — readable by humans and machines.

```bash
projhub board add '{"title":"Add auth flow","agent":"developer","scope":"backend"}'
projhub board ls
projhub board ls --scope backend --status doing
projhub board move PRJ-001 doing
projhub board set PRJ-001 priority p0
projhub board stat
```

### 📁 Multi-Repo Projects

A project root can contain any number of sub-directories and git repos. Register them and they appear in the dashboard's **Repos** tab with live git info.

```bash
projhub repo add ./backend  --name backend
projhub repo add ./frontend --name frontend
projhub repo list
projhub repo info backend
```

### 🌐 Web Dashboard

```bash
projhub serve              # http://127.0.0.1:4242 (localhost only)
projhub serve --host 0.0.0.0  # expose on local network
```

| Tab | Description |
|---|---|
| **Board** | Kanban view with real-time SSE updates |
| **Repos** | Git status per sub-repo: branch, last commit, remote link |
| **Files** | Full file tree with tech-stack badges |
| **Agents** | AI agent definitions |
| **Commands** | Slash commands library |
| **Context** | Project knowledge base |

**File tree badges:** Git, Node, React, Vue, React Native, Python, Go, Rust, Flutter, Docker, Terraform, iOS, Java, PHP.

### 🤖 AI Tool Integration

`projhub compile` translates `.projhub/` into the native format of each AI tool:

| Tool | Slash Command | Context File |
|---|---|---|
| Claude Code | `.claude/commands/*.md` | `CLAUDE.md` |
| Cursor | `.cursor/commands/*.md` | `.cursor/rules/projhub.md` |
| Windsurf | (n/a) | `.windsurfrules` |
| GitHub Copilot | (n/a) | `.github/copilot-instructions.md` |
| Devin CLI | `.devin/skills/*/SKILL.md` | `AGENTS.md` |

### 🔧 Global Setup

```bash
projhub setup-global
# Installs /projhub in Claude Code globally (~/.claude/commands/projhub.md)
# Works in any directory, even before projhub init
```

---

## Commands

```
projhub init               Initialize .projhub/ in the current directory
projhub overview           One-screen project snapshot (board, repos, agents, suggested next)
projhub board <cmd>        Manage tickets (add, ls, move, set, stat, get)
projhub repo <cmd>         Manage sub-repos (add, remove, list, info)
projhub compile            Compile to tool-specific files
projhub serve              Start the web dashboard
projhub setup-global       Install /projhub globally for Claude Code
projhub workspace <cmd>    Manage registered projects
projhub agent <cmd>        Manage agent definitions
projhub doctor             Check project health
```

---

## .projhub/ Structure

```
.projhub/
├── config.json          ← project settings (name, prefix, board config, repos)
├── activity.jsonl       ← append-only event log
├── board/
│   ├── index.json       ← ticket index (auto-rebuilt from .md files)
│   └── tickets/
│       └── PRJ-001-my-ticket.md
├── agents/
│   └── developer.md
├── commands/
│   └── review.md
└── context/
    ├── decisions/
    └── documents/
```

---

## Ticket Format

```markdown
---
id: PRJ-001
title: Add authentication
agent: developer
scope: backend
status: doing
priority: p1
sprint: sprint-1
created: 2026-05-04
updated: 2026-05-04
completed: null
depends: null
tags: auth, security
---

# Start
(Current state before starting)

# Goal — Definition of Done
- [ ] JWT auth implemented
- [ ] Tests passing

# Context
Why this ticket exists.
```

---

## Configuration

```json
{
  "project": {
    "name": "My Project",
    "prefix": "MP",
    "repos": [
      { "name": "backend",  "path": "./backend",  "description": "Node API" },
      { "name": "frontend", "path": "./frontend", "description": "React app" }
    ]
  },
  "board": {
    "statuses": ["backlog", "doing", "review", "done", "cancelled"],
    "priorities": ["p0", "p1", "p2", "p3"],
    "idPadding": 3
  },
  "targets": ["claude", "cursor"]
}
```

---

## Requirements

- Python ≥ 3.11

---

## License

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)

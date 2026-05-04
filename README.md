# projctl

> Universal project operating system for AI coding assistants.  
> Sistema operacional de projetos para assistentes de IA.

[![npm version](https://img.shields.io/npm/v/projctl.svg)](https://www.npmjs.com/package/projctl)
[![npm downloads](https://img.shields.io/npm/dm/projctl.svg)](https://www.npmjs.com/package/projctl)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Node.js](https://img.shields.io/badge/node-%3E%3D18-brightgreen.svg)](https://nodejs.org)

---

## What is projctl?

**projctl** is a CLI tool that turns any directory into a fully structured AI-ready project. It gives you a Kanban board, agent definitions, slash commands, and a live web dashboard — all version-controlled in `.projctl/` alongside your code.

One project root. Any number of sub-repos and directories underneath. One `/projctl` slash command to set it all up inside any AI tool.

```
my-project/              ← project root (projctl init here)
├── backend/             [git · Node]
├── frontend/            [git · React]
├── mobile/              [git · React Native]
├── infra/               [Terraform]
├── .projctl/            ← all project state lives here
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

```bash
npm install -g projctl
```

On install, projctl automatically places a `/projctl` slash command in:
- `~/.claude/commands/projctl.md` — Claude Code
- `~/.cursor/commands/projctl.md` — Cursor

---

## Quick Start

```bash
# 1. Go to your project root
cd ~/my-project

# 2. Initialize
projctl init

# 3. Open the dashboard
projctl serve
# → http://localhost:4242

# 4. Compile for your AI tool
projctl compile --target claude    # generates CLAUDE.md + .claude/commands/
projctl compile --target cursor    # generates .cursor/commands/ + .cursor/rules/
projctl compile --target windsurf  # generates .windsurf/workflows/ + .windsurfrules
projctl compile --target copilot   # generates .github/prompts/ + .github/copilot-instructions.md
```

Or just type `/projctl` in Claude Code or Cursor — it does everything automatically.

---

## Features

### 📋 Kanban Board

Ticket management built for AI agents. Every ticket is a Markdown file with frontmatter — readable by humans and machines.

```bash
projctl board add '{"title":"Add auth flow","agent":"developer","scope":"backend"}'
projctl board ls
projctl board move PRJ-001 doing
projctl board set PRJ-001 priority p0
```

### 📁 Multi-Repo Projects

A project root can contain any number of sub-directories and git repos. Register them, and they appear in the dashboard's **Repos** tab with live git info (branch, last commit, dirty indicator).

```bash
projctl repo add ./backend  --name backend
projctl repo add ./frontend --name frontend
projctl repo ls
```

### 🌐 Web Dashboard

```bash
projctl serve
```

Live dashboard at `http://localhost:4242` with:
- **Board** — Kanban view with real-time SSE updates and scope filter by repo
- **Repos** — Git status of each sub-repo (branch, commit, remote link)
- **Files** — Full file tree with tech-stack badges (Git, Node, React, Python, Go, Rust, Docker, Terraform, Flutter, iOS, Java, PHP...)
- **Agents** — Registered AI agent definitions
- **Commands** — Slash commands library
- **Context** — Project knowledge base

### 🤖 AI Tool Integration

projctl compiles `.projctl/` into the native format of each AI tool:

| Tool | Slash Command | Context File |
|---|---|---|
| Claude Code | `.claude/commands/projctl.md` | `CLAUDE.md` |
| Cursor | `.cursor/commands/projctl.md` | `.cursor/rules/projctl.md` |
| Windsurf | `.windsurf/workflows/projctl.md` | `.windsurfrules` |
| GitHub Copilot | `.github/prompts/projctl.prompt.md` | `.github/copilot-instructions.md` |

### 🔧 Global Setup

```bash
projctl setup-global
# Installs /projctl in Claude Code and Cursor globally
# Works in any directory, even before projctl init
```

---

## Commands

```
projctl init               Initialize .projctl/ in the current directory
projctl board <cmd>        Manage tickets (add, ls, move, set, stat, get)
projctl repo <cmd>         Manage sub-repos (add, remove, ls, info)
projctl compile            Compile to tool-specific files
projctl serve              Start the web dashboard
projctl setup-global       Install /projctl globally for AI tools
projctl workspace <cmd>    Manage registered projects
projctl agent <cmd>        Manage agent definitions
projctl doctor             Check project health
```

### Board subcommands

```bash
projctl board add '<json>'            # Create ticket from JSON
projctl board ls                      # List all tickets
projctl board ls --scope backend      # Filter by repo scope
projctl board ls --status doing       # Filter by status
projctl board ls --agent developer    # Filter by agent
projctl board move <id> <status>      # Move ticket to new status
projctl board set <id> <field> <val>  # Update a ticket field
projctl board stat                    # Count tickets by status
projctl board rebuild-index           # Rebuild index from .md files
```

### Repo subcommands

```bash
projctl repo add <path> [--name <name>] [--description <desc>]
projctl repo ls
projctl repo remove <name>
projctl repo info <name>   # Show git branch, commit, dirty status
```

---

## .projctl/ Structure

```
.projctl/
├── config.json          ← project settings (name, prefix, board config, repos)
├── activity.jsonl       ← append-only event log
├── board/
│   ├── index.json       ← ticket index (auto-rebuilt from .md files)
│   └── tickets/
│       └── PRJ-001-my-ticket.md
├── agents/
│   └── developer.md     ← agent definition (compiled to .claude/agents/)
├── commands/
│   └── review.md        ← slash command (compiled to each tool's format)
└── context/
    ├── decisions/
    └── documents/
```

---

## Ticket Format

Every ticket is a plain Markdown file — readable by humans and AI agents:

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

`config.json` example:

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

- Node.js ≥ 18

---
---

## O que é o projctl?

**projctl** é uma ferramenta CLI que transforma qualquer diretório em um projeto estruturado e pronto para IA. Ele oferece um board Kanban, definições de agentes, slash commands e um dashboard web ao vivo — tudo versionado em `.projctl/` junto com o seu código.

Um projeto root. Qualquer número de sub-repos e diretórios abaixo. Um comando `/projctl` para configurar tudo dentro de qualquer ferramenta de IA.

### Instalação

```bash
npm install -g projctl
```

Na instalação, o projctl coloca automaticamente um slash command `/projctl` em:
- `~/.claude/commands/projctl.md` — Claude Code
- `~/.cursor/commands/projctl.md` — Cursor

### Início Rápido

```bash
cd ~/meu-projeto
projctl init
projctl serve       # → http://localhost:4242

projctl compile --target claude    # CLAUDE.md + .claude/commands/
projctl compile --target cursor    # .cursor/commands/ + .cursor/rules/
projctl compile --target windsurf  # .windsurf/workflows/ + .windsurfrules
projctl compile --target copilot   # .github/prompts/ + .github/copilot-instructions.md
```

Ou simplesmente digite `/projctl` no Claude Code ou Cursor — ele detecta, inicializa e compila automaticamente.

### Dashboard

```bash
projctl serve  # http://localhost:4242
```

| Aba | Descrição |
|---|---|
| **Board** | Kanban com atualização em tempo real (SSE) e filtro por repo |
| **Repos** | Status git de cada sub-repo: branch, último commit, link pro remote |
| **Files** | Árvore de arquivos com badges: Git, Node, React, Python, Go, Rust, Docker, Terraform, Flutter, iOS... |
| **Agents** | Definições de agentes de IA |
| **Commands** | Biblioteca de slash commands |
| **Context** | Base de conhecimento do projeto |

### Múltiplos Repos num Projeto

```bash
projctl repo add ./backend  --name backend
projctl repo add ./frontend --name frontend
projctl repo add ./mobile   --name mobile
projctl repo ls
```

Os repos aparecem na aba **Repos** do dashboard com informações de git ao vivo (branch, commit, dirty).

### Integração com Ferramentas de IA

| Ferramenta | Slash Command | Arquivo de Contexto |
|---|---|---|
| Claude Code | `.claude/commands/projctl.md` | `CLAUDE.md` |
| Cursor | `.cursor/commands/projctl.md` | `.cursor/rules/projctl.md` |
| Windsurf | `.windsurf/workflows/projctl.md` | `.windsurfrules` |
| GitHub Copilot | `.github/prompts/projctl.prompt.md` | `.github/copilot-instructions.md` |

### Board de Tickets

```bash
projctl board add '{"title":"Implementar auth","agent":"developer","scope":"backend"}'
projctl board ls
projctl board ls --scope backend --status doing
projctl board move PRJ-001 review
projctl board stat
```

---

## Licença

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)

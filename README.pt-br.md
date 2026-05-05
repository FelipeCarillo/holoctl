# projctl

> Sistema operacional de projetos para assistentes de IA.

<p>
  <a href="./README.md"><img src="https://img.shields.io/badge/lang-English-blue?style=flat-square" alt="English"/></a>
  <a href="./README.pt-br.md"><img src="https://img.shields.io/badge/lang-Português-green?style=flat-square" alt="Português"/></a>
</p>

[![npm version](https://img.shields.io/npm/v/projctl.svg)](https://www.npmjs.com/package/projctl)
[![npm downloads](https://img.shields.io/npm/dm/projctl.svg)](https://www.npmjs.com/package/projctl)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/node-%3E%3D18-brightgreen.svg)](https://nodejs.org)

---

## O que é o projctl?

**projctl** é uma ferramenta CLI que transforma qualquer diretório em um projeto estruturado e pronto para IA. Ele oferece um board Kanban, definições de agentes, slash commands e um dashboard web ao vivo — tudo versionado em `.projctl/` junto com o seu código.

Um projeto root. Qualquer número de sub-repos e diretórios abaixo. Um comando `/projctl` para configurar tudo dentro de qualquer ferramenta de IA.

```
meu-projeto/             ← root do projeto (projctl init aqui)
├── backend/             [git · Node]
├── frontend/            [git · React]
├── mobile/              [git · React Native]
├── infra/               [Terraform]
├── .projctl/            ← todo o estado do projeto fica aqui
│   ├── config.json
│   ├── board/
│   │   └── tickets/
│   ├── agents/
│   ├── commands/
│   └── context/
└── README.md
```

---

## Instalação

```bash
npm install -g projctl
```

Na instalação, o projctl coloca automaticamente um slash command `/projctl` em:
- `~/.claude/commands/projctl.md` — Claude Code
- `~/.cursor/commands/projctl.md` — Cursor

---

## Início Rápido

```bash
# 1. Vá para o root do seu projeto
cd ~/meu-projeto

# 2. Inicialize
projctl init

# 3. Abra o dashboard
projctl serve
# → http://localhost:4242

# 4. Compile para sua ferramenta de IA
projctl compile --target claude    # CLAUDE.md + .claude/commands/
projctl compile --target cursor    # .cursor/commands/ + .cursor/rules/
projctl compile --target windsurf  # .windsurf/workflows/ + .windsurfrules
projctl compile --target copilot   # .github/prompts/ + .github/copilot-instructions.md
```

Ou simplesmente digite `/projctl` no Claude Code ou Cursor — ele detecta, inicializa e compila automaticamente.

---

## Funcionalidades

### 📋 Board Kanban

Gerenciamento de tickets construído para agentes de IA. Cada ticket é um arquivo Markdown com frontmatter — legível por humanos e máquinas.

```bash
projctl board add '{"title":"Implementar auth","agent":"developer","scope":"backend"}'
projctl board ls
projctl board ls --scope backend --status doing
projctl board move PRJ-001 doing
projctl board set PRJ-001 priority p0
projctl board stat
```

### 📁 Projetos Multi-Repo

Um projeto root pode ter qualquer número de sub-diretórios e git repos. Registre-os e eles aparecem na aba **Repos** do dashboard com informações de git ao vivo.

```bash
projctl repo add ./backend  --name backend
projctl repo add ./frontend --name frontend
projctl repo ls
projctl repo info backend
```

### 🌐 Dashboard Web

```bash
projctl serve   # http://localhost:4242
```

| Aba | Descrição |
|---|---|
| **Board** | Kanban com atualização em tempo real (SSE) e filtro de scope por repo |
| **Repos** | Status git de cada sub-repo: branch, último commit, link pro remote |
| **Files** | Árvore de arquivos completa com badges de tecnologia |
| **Agents** | Definições de agentes de IA |
| **Commands** | Biblioteca de slash commands |
| **Context** | Base de conhecimento do projeto |

**Badges na árvore de arquivos:** Git, Node, React, Vue, React Native, Python, Go, Rust, Flutter, Docker, Terraform, iOS, Java, PHP.

### 🤖 Integração com Ferramentas de IA

O projctl compila `.projctl/` para o formato nativo de cada ferramenta:

| Ferramenta | Slash Command | Arquivo de Contexto |
|---|---|---|
| Claude Code | `.claude/commands/projctl.md` | `CLAUDE.md` |
| Cursor | `.cursor/commands/projctl.md` | `.cursor/rules/projctl.md` |
| Windsurf | `.windsurf/workflows/projctl.md` | `.windsurfrules` |
| GitHub Copilot | `.github/prompts/projctl.prompt.md` | `.github/copilot-instructions.md` |

### 🔧 Setup Global

```bash
projctl setup-global
# Instala /projctl no Claude Code e Cursor globalmente
# Funciona em qualquer diretório, mesmo antes do projctl init
```

---

## Comandos

```
projctl init               Inicializa .projctl/ no diretório atual
projctl board <cmd>        Gerencia tickets (add, ls, move, set, stat, get)
projctl repo <cmd>         Gerencia sub-repos (add, remove, ls, info)
projctl compile            Compila para arquivos específicos de cada ferramenta
projctl serve              Inicia o dashboard web
projctl setup-global       Instala /projctl globalmente para ferramentas de IA
projctl workspace <cmd>    Gerencia projetos registrados
projctl agent <cmd>        Gerencia definições de agentes
projctl doctor             Verifica a saúde do projeto
```

---

## Estrutura do .projctl/

```
.projctl/
├── config.json          ← configurações do projeto (nome, prefixo, board, repos)
├── activity.jsonl       ← log de eventos append-only
├── board/
│   ├── index.json       ← índice de tickets (reconstruído automaticamente dos .md)
│   └── tickets/
│       └── PRJ-001-meu-ticket.md
├── agents/
│   └── developer.md
├── commands/
│   └── review.md
└── context/
    ├── decisions/
    └── documents/
```

---

## Formato de Ticket

```markdown
---
id: PRJ-001
title: Implementar autenticação
agent: developer
scope: backend
status: doing
priority: p1
sprint: sprint-1
created: 2026-05-04
updated: 2026-05-04
completed: null
depends: null
tags: auth, segurança
---

# Estado Atual
(Estado antes de começar)

# Objetivo — Definição de Pronto
- [ ] Auth JWT implementada
- [ ] Testes passando

# Contexto
Por que este ticket existe.
```

---

## Configuração

```json
{
  "project": {
    "name": "Meu Projeto",
    "prefix": "MP",
    "repos": [
      { "name": "backend",  "path": "./backend",  "description": "API Node" },
      { "name": "frontend", "path": "./frontend", "description": "App React" }
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

## Requisitos

- Node.js ≥ 18

---

## Licença

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)

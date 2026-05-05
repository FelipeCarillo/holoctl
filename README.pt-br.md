# projhub

> Sistema operacional de projetos para assistentes de IA.

<p>
  <a href="./README.md"><img src="https://img.shields.io/badge/lang-English-blue?style=flat-square" alt="English"/></a>
  <a href="./README.pt-br.md"><img src="https://img.shields.io/badge/lang-Português-green?style=flat-square" alt="Português"/></a>
</p>

[![PyPI version](https://img.shields.io/pypi/v/projhub.svg)](https://pypi.org/project/projhub/)
[![PyPI downloads](https://img.shields.io/pypi/dm/projhub.svg)](https://pypi.org/project/projhub/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-brightgreen.svg)](https://www.python.org)

---

## O que é o projhub?

O **projhub** é uma CLI que transforma qualquer diretório em um projeto totalmente estruturado e pronto para IA. Ele te dá um quadro Kanban, definições de agentes, slash commands e um dashboard web ao vivo — tudo versionado em `.projhub/` ao lado do seu código.

Uma raiz de projeto. Quantos sub-repos e diretórios você quiser. Um único `/projhub` para configurar tudo dentro do Claude Code.

```
meu-projeto/             ← raiz do projeto (rode projhub init aqui)
├── backend/             [git · Node]
├── frontend/            [git · React]
├── mobile/              [git · React Native]
├── infra/               [Terraform]
├── .projhub/            ← todo o estado do projeto vive aqui
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

Recomendado (resolve PATH automaticamente):

```bash
uv tool install projhub
```

Ou com pip:

```bash
pip install projhub
```

Após instalar, configure o slash command global `/projhub`:

```bash
projhub setup-global
```

Isso coloca o comando `/projhub` em `~/.claude/commands/projhub.md` para você usar em qualquer projeto no Claude Code.

> Cursor, Windsurf e GitHub Copilot não suportam slash commands instalados globalmente. Para eles, use `projhub compile` dentro de cada projeto e os arquivos de integração são gerados no formato nativo de cada ferramenta (veja **Integração com IA** abaixo).

---

## Quick Start

```bash
# 1. Vá para a raiz do projeto
cd ~/meu-projeto

# 2. Inicialize
projhub init

# 3. Abra o dashboard
projhub serve
# → http://127.0.0.1:4242

# 4. Compile para sua ferramenta
projhub compile --target claude    # CLAUDE.md + .claude/commands/
projhub compile --target cursor    # .cursor/commands/ + .cursor/rules/
projhub compile --target windsurf  # .windsurfrules
projhub compile --target copilot   # .github/copilot-instructions.md
```

Ou apenas digite `/projhub` no Claude Code — ele detecta, inicializa e compila automaticamente.

---

## Recursos

### 📋 Kanban Board

Gestão de tickets feita pra agentes de IA. Cada ticket é um Markdown com frontmatter — legível por humanos e máquinas.

```bash
projhub board add '{"title":"Adicionar auth","agent":"developer","scope":"backend"}'
projhub board ls
projhub board ls --scope backend --status doing
projhub board move PRJ-001 doing
projhub board set PRJ-001 priority p0
projhub board stat
```

### 📁 Projetos multi-repo

Uma raiz de projeto pode conter quantos sub-repos e diretórios você quiser. Registre eles e aparecerão na aba **Repos** do dashboard com info de git ao vivo.

```bash
projhub repo add ./backend  --name backend
projhub repo add ./frontend --name frontend
projhub repo list
projhub repo info backend
```

### 🌐 Dashboard Web

```bash
projhub serve              # http://127.0.0.1:4242 (só localhost)
projhub serve --host 0.0.0.0  # expor na rede local
```

| Aba | Descrição |
|---|---|
| **Board** | Visão kanban com atualização ao vivo via SSE |
| **Repos** | Status git por sub-repo: branch, último commit, remote |
| **Files** | Árvore completa de arquivos com badges de tech-stack |
| **Agents** | Definições de agentes de IA |
| **Commands** | Biblioteca de slash commands |
| **Context** | Base de conhecimento do projeto |

**Badges da árvore:** Git, Node, React, Vue, React Native, Python, Go, Rust, Flutter, Docker, Terraform, iOS, Java, PHP.

### 🤖 Integração com IA

`projhub compile` traduz `.projhub/` para o formato nativo de cada ferramenta:

| Ferramenta | Slash Command | Arquivo de Contexto |
|---|---|---|
| Claude Code | `.claude/commands/*.md` | `CLAUDE.md` |
| Cursor | `.cursor/commands/*.md` | `.cursor/rules/projhub.md` |
| Windsurf | (n/d) | `.windsurfrules` |
| GitHub Copilot | (n/d) | `.github/copilot-instructions.md` |

### 🔧 Setup Global

```bash
projhub setup-global
# Instala /projhub no Claude Code globalmente (~/.claude/commands/projhub.md)
# Funciona em qualquer diretório, mesmo antes do projhub init
```

---

## Comandos

```
projhub init               Inicializa .projhub/ no diretório atual
projhub board <cmd>        Gerencia tickets (add, ls, move, set, stat, get)
projhub repo <cmd>         Gerencia sub-repos (add, remove, list, info)
projhub compile            Compila para arquivos específicos da ferramenta
projhub serve              Inicia o dashboard web
projhub setup-global       Instala /projhub globalmente no Claude Code
projhub workspace <cmd>    Gerencia projetos registrados
projhub agent <cmd>        Gerencia definições de agentes
projhub doctor             Verifica a saúde do projeto
```

---

## Estrutura do `.projhub/`

```
.projhub/
├── config.json          ← configurações (nome, prefix, board, repos)
├── activity.jsonl       ← log de eventos append-only
├── board/
│   ├── index.json       ← índice de tickets (rebuild automático dos .md)
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

## Formato do ticket

```markdown
---
id: PRJ-001
title: Adicionar autenticação
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
(Estado atual antes de começar)

# Goal — Definition of Done
- [ ] Auth JWT implementado
- [ ] Testes passando

# Context
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

- Python ≥ 3.11

---

## Licença

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)

# holoctl

> Estrutura de projeto para agentes de IA — board, tickets, agents, decisões, dossiê — versionados em `.holoctl/` junto do seu código.

<p align="center">
  🇺🇸 <a href="README.md">English</a> |
  🇧🇷 <a href="README.pt-br.md">Português</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/holoctl/"><img src="https://img.shields.io/pypi/v/holoctl?color=blue" alt="PyPI"/></a>
  <a href="https://pypi.org/project/holoctl/"><img src="https://img.shields.io/pypi/dm/holoctl?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://github.com/FelipeCarillo/holoctl/actions/workflows/ci.yml"><img src="https://github.com/FelipeCarillo/holoctl/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT"/></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-≥3.11-brightgreen" alt="Python"/></a>
</p>

Digite `/holoctl` no seu assistente de IA e seu projeto ganha um Kanban, agents nomeados, slash commands, log de decisões e um dashboard web ao vivo — tudo em git como Markdown + JSON.

Funciona no **Claude Code**, **Cursor**, **Windsurf**, **GitHub Copilot**, **Devin**, **Aider**, e qualquer agente que leia `AGENTS.md` / `CLAUDE.md`.

```bash
holoctl init
```

É isso. Você ganha:

```
seu-projeto/
├── .holoctl/                  ← fonte única de verdade, no git
│   ├── config.json
│   ├── board/
│   │   ├── index.json         ← reconstruído a partir dos .md
│   │   └── tickets/
│   │       └── PRJ-001-add-auth.md
│   ├── agents/                ← developer.md, reviewer.md, architect.md, researcher.md
│   ├── commands/              ← /board, /ticket, /sprint, /close, /decision, /status
│   ├── context/
│   │   ├── decisions/         ← ADRs travadas
│   │   └── documents/
│   └── activity.jsonl         ← log append-only de eventos
├── CLAUDE.md                  ← compilado de .holoctl/, lido pelo Claude Code
├── AGENTS.md                  ← compilado, lido por Devin/Cursor/Aider
├── .claude/commands/          ← /board, /ticket, /holoctl etc. para o Claude Code
└── …seu código
```

---

## Instalação

**Requer Python ≥ 3.11.**

```bash
uv tool install holoctl       # recomendado — coloca no PATH automaticamente
# ou
pipx install holoctl
# ou
pip install holoctl
```

> **`holoctl: command not found`?** `uv tool` e `pipx` colocam o CLI no PATH automaticamente. Com `pip` puro, adicione `~/.local/bin` (Linux/Mac) ou `~/AppData/Roaming/Python/Scripts` (Windows) ao PATH, ou rode `python -m holoctl`.

---

## Quick Start

```bash
cd seu-projeto               # qualquer pasta com código
holoctl init                 # cria .holoctl/ — não escreve nada em $HOME
holoctl compile              # gera CLAUDE.md / AGENTS.md / .claude/commands/
holoctl serve                # http://127.0.0.1:4242 — kanban ao vivo
```

Aí abre o Claude Code (ou Cursor, ou Devin…) na pasta e digita `/holoctl`. O agente já pega o board, os templates de ticket e as definições de agent automaticamente.

> **Sem estado global.** holoctl não escreve em `$HOME` nem mantém registro de projetos por máquina. O workspace É a pasta onde você rodou `init`. Tudo o mais — slash commands, AGENTS.md, dashboard — é gerado por workspace via `holoctl compile`. Seguro pra máquinas compartilhadas, CI, devcontainers.

---

## Escolha sua ferramenta de IA

`holoctl compile` traduz `.holoctl/` para o formato nativo de cada ferramenta. Roda uma vez por workspace; rerodar depois de editar regenera tudo.

| Ferramenta | Target | Arquivos gerados |
|---|---|---|
| Claude Code | `--target claude` | `CLAUDE.md`, `.claude/commands/*.md`, `.claude/agents/*.md` |
| Cursor | `--target cursor` | `.cursor/rules/holoctl.md`, `.cursor/commands/*.md` |
| Windsurf | `--target windsurf` | `.windsurfrules`, `.windsurf/workflows/*.md` |
| GitHub Copilot | `--target copilot` | `.github/copilot-instructions.md`, `.github/prompts/*.md` |
| Devin | `--target devin` | `AGENTS.md`, `.devin/skills/*/SKILL.md` |
| Genérico (Aider, etc.) | `--target generic` | `AGENTS.md` |

```bash
holoctl compile --target claude
holoctl compile                       # todos os targets em config.targets[]
```

---

## O que você ganha

### 📋 Kanban com tickets em arquivos

Tickets são Markdown com frontmatter. O índice (`index.json`) é reconstruído a partir deles, então você edita qualquer um dos lados e os dois ficam em sincronia. Cada ticket pode linkar a um ou mais **subprojetos descobertos** (veja abaixo).

```bash
holoctl board add '{"title":"Adicionar auth","agent":"developer","projects":["backend"]}'
holoctl board add '{"title":"Wire SSE","agent":"developer","projects":["backend","frontend"]}'
holoctl board ls --project backend --status doing
holoctl board move PRJ-001 doing
holoctl board set PRJ-001 priority p0
holoctl board stat
```

```markdown
---
id: PRJ-001
title: Adicionar autenticação
agent: developer
projects: backend, shared
status: doing
priority: p1
sprint: sprint-1
---
# Start
…arquivos que vão mudar, estado atual…
# Goal — Definition of Done
- [ ] JWT implementado
- [ ] Testes passando
# Context
…por que existe, decisões tomadas…
```

### 📁 Workspace multi-projeto auto-descoberto

A pasta onde você roda `init` é o workspace. Subdiretórios diretos com markers de projeto (`.git`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `composer.json`, `Gemfile`, `pubspec.yaml`, `mix.exs`, `build.gradle`, `pom.xml`, `CMakeLists.txt`) aparecem **automaticamente** na aba **Projects** do dashboard e nos filtros do board — sem precisar registrar nada à mão.

```bash
holoctl repo list                          # vê o que foi descoberto
holoctl repo add ./infra --name infra      # opcional: registra subdir sem markers
holoctl repo info backend                  # branch git, dirty, remote
```

### 🤖 Agents nomeados com papéis explícitos

`.holoctl/agents/*.md` definem personas: `developer`, `reviewer`, `architect`, `researcher`. Cada uma tem identidade, escopo, guard rails e formato de relatório. Quando um ticket é atribuído a um agent, os slash commands roteiam pra definição correspondente. Você edita as personas como qualquer arquivo do repo.

### 🌐 Dashboard web ao vivo

```bash
holoctl serve                  # http://127.0.0.1:4242 (só localhost)
holoctl serve --host 0.0.0.0   # expõe na rede local
```

| Aba | Conteúdo |
|---|---|
| **Board** | Kanban com SSE em tempo real, filtra por projeto / agent / sprint |
| **Repos** | Subdirs auto-descobertos com branch git, dirty, contagem de tickets |
| **Agents** | Personas em cards |
| **Commands** | Biblioteca de slash commands |
| **Context** | Log de decisões, documentos livres |

### 🔒 Sem estado global, sem instalações surpresa

- `holoctl init` não escreve em `$HOME`. Não há `~/.holoctl/`, nenhum registro de projetos por máquina.
- Não existe `holoctl install`. Sem hook de postinstall.
- O slash command `/holoctl` é um **artefato por workspace** gerado por `holoctl compile --target claude`. Quer ele em outro workspace? Roda compile lá também.
- Seguro pra máquinas compartilhadas, runners de CI e devcontainers sem vazar estado.

---

## Comandos

```
holoctl init               Inicializa .holoctl/ no workspace atual
holoctl overview           Snapshot do workspace em uma tela
holoctl board <cmd>        Tickets — add, ls, move, set, stat, get, rebuild-index
holoctl repo <cmd>         Subprojetos descobertos — list, add (override), info
holoctl compile            Gera arquivos de integração com ferramentas de IA
holoctl serve              Inicia o dashboard web
holoctl agent <cmd>        Gerencia definições de agents
holoctl sync               Atualiza arquivos de template após upgrade do holoctl
holoctl doctor             Health check
```

Roda `holoctl <cmd> --help` em qualquer um deles.

---

## Configuração

Os defaults vivem no código; em `.holoctl/config.json` você só sobrescreve o necessário:

```json
{
  "project": {
    "name": "Meu Projeto",
    "prefix": "MP",
    "repos": [
      { "name": "backend",  "path": "./backend",  "description": "Node API" }
    ]
  },
  "board": {
    "statuses": ["backlog", "doing", "review", "done", "cancelled"],
    "priorities": ["p0", "p1", "p2", "p3"],
    "idPadding": 3
  },
  "targets": ["claude", "cursor"],
  "server": { "port": 4242, "theme": "dark" }
}
```

`project.repos` é **opcional** — só necessário pra registrar subdirs que o auto-scan não pegar ou pra sobrescrever o nome de exibição. Subdirs auto-descobertos já aparecem sem ele.

---

## Migrando de `projctl` / `projhub`

Nomes anteriores deste projeto. holoctl lê pastas `.projctl/` e `.projhub/` e renomeia automaticamente pra `.holoctl/` no próximo save. Tickets que usavam `scope: X` são lidos como `projects: [X]` e reescritos no próximo `board set` ou `rebuild-index`.

---

## Documentação

- [CHANGELOG.md](holoctl/CHANGELOG.md) — notas de release
- [ARCHITECTURE.md](ARCHITECTURE.md) — design interno, pipeline de compile
- [SECURITY.md](SECURITY.md) — relato de vulnerabilidades + threat model
- [CONTRIBUTING.md](CONTRIBUTING.md) — setup de dev, convenções, como adicionar um compile target

---

## Licença

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)

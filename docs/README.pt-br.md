# holoctl

> Sistema operacional vivo para projetos com assistentes de IA — memória durável, curador autônomo, compilação multi-assistente, tudo versionado em `.holoctl/` ao lado do seu código.

<p align="center">
  🇺🇸 <a href="../README.md">English</a> |
  🇧🇷 <a href="README.pt-br.md">Português</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/holoctl/"><img src="https://img.shields.io/pypi/v/holoctl?color=blue" alt="PyPI"/></a>
  <a href="https://pypi.org/project/holoctl/"><img src="https://img.shields.io/pypi/dm/holoctl?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://github.com/FelipeCarillo/holoctl/actions/workflows/ci.yml"><img src="https://github.com/FelipeCarillo/holoctl/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT"/></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-≥3.11-brightgreen" alt="Python"/></a>
</p>

Digite `/holoctl` em qualquer assistente de IA. O agente lê o estado do workspace, planta a estrutura se precisar, e roteia o fluxo certo — primeira vez, upgrade, ou operação normal.

Funciona em **Claude Code**, **Cursor**, **Windsurf**, **GitHub Copilot**, **Devin**, **Aider**, e qualquer agente que leia `AGENTS.md` / `CLAUDE.md`.

```bash
uv tool install holoctl
hctl setup                    # uma vez por máquina — planta /holoctl em todos os assistentes detectados
```

Em qualquer pasta:

```bash
hctl init                     # cria .holoctl/, compila pra todos os targets, planta hooks + MCP
```

Ou simplesmente digite `/holoctl` dentro do assistente — ele roda `hctl init` sozinho.

---

## Por que "vivo"

O `holoctl` começou como um compilador estático — `.holoctl/` vira arquivos nativos. A partir da **0.14** ele é um sistema que **acorda entre sessões**:

- **Memória durável** em `.holoctl/memory/` compartilhada por todos os assistentes — as mesmas notas aparecem no Claude, Cursor, Windsurf, Copilot e Devin no formato nativo de cada um.
- **Journal de eventos** captura cada uso de ferramenta, edição e fronteira de sessão via hooks plantados automaticamente pelo `hctl init`.
- **Curador autônomo** observa o journal e propõe novas personas, regras path-scoped, ou arquivamento de topics como tickets `meta:curate` no board. Você aprova movendo o ticket pra `done` — ele auto-executa a ação proposta.
- **Boot econômico** imprime ≤1KB de contexto sessão-zero (pendências, decisões recentes, topics disponíveis) pro assistente não queimar tokens carregando o `CLAUDE.md` inteiro.
- **Servidor MCP** expõe board, memória, journal e curator como ferramentas padrão — leitura/escrita com permission gating no Claude Code.

```
seu-projeto/
├── .holoctl/                       ← fonte única de verdade, no git
│   ├── config.json
│   ├── instructions.md             ← compilado pra CLAUDE.md / AGENTS.md / etc.
│   ├── board/                      ← Kanban + tickets
│   │   ├── index.json              ← reconstruído a partir dos .md
│   │   └── tickets/PRJ-001-*.md
│   ├── agents/                     ← personas ativas (só `boardmaster` por default)
│   ├── commands/                   ← /board, /ticket, /sprint, /close, /decision, /status
│   ├── context/decisions/          ← ADRs travadas
│   ├── memory/                     ← notas duráveis cross-assistente
│   │   ├── MEMORY.md               ← índice always-on
│   │   └── topics/                 ← topics lazy/glob-scoped
│   ├── journal/                    ← JSONL diário de eventos de sessão
│   └── curator/                    ← estado do curator + metadata por ticket
└── …seu código
```

Os outputs compilados (`CLAUDE.md`, `.cursor/rules/`, `.windsurf/skills/`, `.vscode/mcp.json`, `.devin/skills/`, etc.) são regenerados pelo `hctl init` e `hctl compile`. A maioria dos usuários adiciona ao `.gitignore`.

---

## Instalação

**Requer Python ≥ 3.11.**

```bash
uv tool install holoctl              # recomendado — venv isolado, hctl no PATH
# ou
pipx install holoctl
# ou
pip install holoctl                  # dentro de um venv ativo

# Extra ML opcional (detecção de paráfrase pelo curator — ~250MB, backend ONNX):
uv tool install "holoctl[ml]"
```

> **`holoctl: command not found`?** `uv tool` e `pipx` colocam o CLI no PATH. Com `pip` puro, adicione `~/.local/bin` (Linux/Mac) ou `~/AppData/Roaming/Python/Scripts` (Windows) ao PATH, ou rode `python -m holoctl`.

---

## Setup uma vez, trabalhe em qualquer pasta

```bash
hctl setup
```

`hctl setup` detecta cada assistente de IA suportado e planta a skill `/holoctl` em **escopo user**:

```
✓ Claude Code   → ~/.claude/commands/holoctl.md
✓ Cursor        → ~/.cursor/rules/holoctl.mdc
✓ Windsurf      → ~/.codeium/windsurf/skills/holoctl/SKILL.md
✓ Copilot       → ~/.copilot/prompts/holoctl.prompt.md
✓ Devin CLI     → ~/.config/devin/skills/holoctl/SKILL.md
```

O corpo da skill é idêntico nos 5 — só o frontmatter muda. A partir daí, em qualquer pasta, você digita `/holoctl` e o agente roda `hctl doctor`, escolhe o fluxo certo e começa a trabalhar:

| `hctl doctor` retorna | O agente roda |
|---|---|
| `not initialized` | `hctl init` (cria `.holoctl/`, compila, planta hooks + MCP) |
| `outdated` | `hctl upgrade --check` e pergunta antes de aplicar |
| `ok` | `hctl boot` (≤1KB de contexto sessão-zero) |

---

## Cinco assistentes, uma fonte de verdade

`.holoctl/` compila pra **primitiva nativa** de cada alvo — sem monkey-patch:

| Assistente | Memória | Skills | Hooks | MCP |
|---|---|---|---|---|
| Claude Code | `.claude/skills/holoctl-memory*/SKILL.md` (lazy, glob, always_on) | `.claude/skills/<name>/SKILL.md` | `.claude/settings.json:hooks` | `mcpServers.holoctl` |
| Cursor | `.cursor/rules/holoctl-memory*.mdc` (alwaysApply / globs / description) | `.cursor/rules/skill-*.mdc` | `.cursor/hooks.json` | `.cursor/mcp.json` |
| Windsurf | `.windsurf/rules/holoctl-memory*.md` (`trigger: always_on \| model_decision \| glob`) | `.windsurf/skills/<name>/SKILL.md` | — | `.windsurf/mcp.json` |
| Copilot | `.github/instructions/holoctl-memory-*.instructions.md` (`applyTo:`) | `.github/prompts/*.prompt.md` | — | `.vscode/mcp.json` |
| Devin | `.devin/rules/holoctl-memory*.md` | `.devin/skills/<name>/SKILL.md` (também lê `.windsurf/skills/`) | — | `.devin/mcp.json` |

**Adicionar um topic de memória é um arquivo só** em `.holoctl/memory/topics/` com `scope: lazy/glob/always_on` — os 5 compiladores traduzem pra forma nativa. Idem pra personas: um `.md` em `holoctl/templates/agents/` (a biblioteca latente) é opt-in via `hctl agent add <name>` e vira `SKILL.md` em 3 assistentes nativamente, com traduções `.mdc` e `.prompt.md` pros outros dois.

---

## O que você ganha

### 📋 Kanban com criação batch parallel-safe

```bash
hctl board add '{"title":"Adicionar JWT","agent":"developer","priority":"p1"}'
hctl board batch '{"shared":{"tags":["par:auth"]},"tickets":[…]}'   # valida não-sobreposição
hctl board ls --status doing --priority p1
hctl board move PRJ-001 doing
```

### 🧠 Memória durável cross-assistente

```bash
hctl memory add decisoes --scope lazy -d "Log de decisões arquiteturais"
hctl memory add api-conventions --scope glob -g "src/api/**"
hctl memory list                    # topics ativos + scopes
hctl memory search "JWT"
hctl memory archive topic-antigo
```

Topics declaram frontmatter canônico (`scope`, `globs`, `description`); os compiladores traduzem pra cada assistente.

### 🤖 Biblioteca latente de personas + ativação opt-in

Por default `hctl init` materializa só o `boardmaster`. O catálogo completo (`developer`, `reviewer`, `architect`, `researcher`, …) fica latente em `holoctl/templates/agents/` e ativa sob demanda:

```bash
hctl agent list                     # ativas vs biblioteca
hctl agent add developer            # materializa da biblioteca com placeholders resolvidos
hctl agent remove developer
```

Cada persona da biblioteca declara heurísticas `when_to_suggest:` que o curator usa pra propor ativações automaticamente.

### 📓 Journal de eventos + sugestões do curator

Hooks plantados por `hctl init` escrevem cada evento de sessão em `.holoctl/journal/<AAAA-MM-DD>.jsonl`. O curator lê e propõe:

| Padrão detectado | Ação proposta | Materializa como |
|---|---|---|
| ≥10 edits em `src/api/**` ao longo de 3 sessões | `rule_extract` | memory topic com `scope: glob` |
| Prompts similares repetidos (≥3x) | `memory_promote` | memory topic lazy |
| Heurística de persona da biblioteca dispara | `agent_add` | persona ativa em `.holoctl/agents/` |
| Topic intocado ≥60 dias | `topic_archive` | move pra `topics/_archived/` |
| Auto-memory do Cascade ≥7 dias | `memory_promote` | topic versionado |

```bash
hctl curate run --auto              # rate-limited (1/dia, supressão 14 dias)
hctl curate show                    # tickets meta:curate abertos
hctl board move PRJ-042 done        # ← aprovação auto-executa a ação
hctl curate silence <pattern_id>    # supressão por 14 dias
```

### 🚀 Boot + handoff pra continuidade entre sessões

```bash
hctl boot                           # ≤1KB: pendências, decisões, topics, personas, ⚡ dicas do curator
hctl handoff --note "fechei 0.14"   # adiciona 1 linha em memory/topics/session-trail.md
```

### 🔌 Servidor MCP — board/memory acessíveis em qualquer assistente

`hctl serve --mcp` roda como servidor MCP via stdio; `hctl init` escreve a config por assistente pra ele ser spawned sob demanda. **14 ferramentas** divididas em leitura/escrita — ferramentas de escrita (`board_create`, `board_move`, `memory_add`, `agent_add`, …) caem em `permissions.ask` no Claude Code. Schema espelha o CLI 1:1.

### 🌐 Dashboard web ao vivo

```bash
hctl serve                          # http://127.0.0.1:4242
```

| Aba | Conteúdo |
|---|---|
| **Board** | Kanban com SSE em tempo real, filter/sort/group por status/priority/agent/sprint/tag/project |
| **Repos** | Subprojetos auto-descobertos, git branch + contagem de tickets |
| **Agents** | Personas ativas + catálogo da biblioteca |
| **Commands** | Biblioteca de slash commands |
| **Context** | Log de decisões + documentos livres |

---

## Comandos

```
hctl setup                    Planta a skill /holoctl em cada assistente detectado (uma vez)
hctl init                     Inicializa ou sincroniza .holoctl/ — idempotente
hctl upgrade                  Migra workspace + recompila pra versão instalada
hctl compile                  Gera arquivos de integração com a IA
hctl serve [--mcp]            Dashboard web, ou servidor MCP via stdio
hctl doctor                   Health check (not initialized | outdated | ok)
hctl overview                 Snapshot do workspace em uma tela

hctl board <cmd>              Tickets — add, ls, move, set, batch, stat, get, body, rebuild-index
hctl agent <cmd>              Personas — list, add, remove
hctl memory <cmd>             Memória — list, add, get, search, archive, seed
hctl journal <cmd>            Journal — record, show, count, import, tail
hctl boot                     Contexto sessão-zero mínimo (≤1KB)
hctl handoff [--note ...]     Fim de sessão: adiciona linha ao session-trail
hctl curate <cmd>             Curator — run, show, silence, apply

hctl repo <cmd>               Subprojetos descobertos — list, add, info
```

Todo comando aceita `--help`.

---

## Configuração

`.holoctl/config.json` — só sobrescreve o que precisar:

```json
{
  "holoctlVersion": "0.14.0",
  "project": {
    "name": "Meu Projeto",
    "prefix": "MP"
  },
  "board": {
    "statuses": ["backlog", "doing", "review", "done", "cancelled"],
    "priorities": ["p0", "p1", "p2", "p3"],
    "idPadding": 3
  },
  "git": { "checkDirty": false },
  "targets": ["claude", "cursor", "windsurf", "copilot", "devin"],
  "server": { "port": 4242, "theme": "dark" }
}
```

`git.checkDirty` é **false** por default — holoctl lê `.git/HEAD`/`refs`/`config` direto sem spawnar subprocesso, instantâneo no Windows + AV corporativo.

---

## Privacidade e coexistência

- **`holoctl init` não escreve nada em `$HOME`.** O `hctl setup` escreve, mas só os arquivos da skill `/holoctl` em escopos user de assistentes detectados. Sem registro global, sem daemon.
- **`.holoctl/memory/.gitignore`** é criado com `_archived/` excluído por default. Workspaces privacy-strict descomentam duas linhas pra deixar a árvore inteira local-only.
- **Coexiste com auto-memory nativo.** O auto-memory do Claude Code NÃO é desligado — `holoctl` adiciona uma referência `@.holoctl/memory/MEMORY.md` no `CLAUDE.md` pra Claude ler ambos. Idem com o Windsurf: escrevemos em `.windsurf/rules/` (durável, versionado), o Cascade mantém o `~/.codeium/windsurf/memories/` (máquina-local). O curator pode promover uma memória do Cascade que sobreviveu ≥7 dias pra um topic versionado.

---

## Migração de `projctl` / `projhub`

Nomes anteriores deste projeto. O holoctl lê diretórios `.projctl/` e `.projhub/` e auto-renomeia pra `.holoctl/` na próxima escrita. Tickets que usavam `scope: X` são lidos como `projects: [X]` e reescritos no próximo `board set` ou `rebuild-index`.

---

## Documentação

- [CHANGELOG.md](../holoctl/CHANGELOG.md) — notas de release
- [ARCHITECTURE.md](../ARCHITECTURE.md) — design interno, pipeline de compilação
- [SECURITY.md](../SECURITY.md) — relato de vulnerabilidades + threat model
- [CONTRIBUTING.md](../CONTRIBUTING.md) — setup de dev, convenções, como adicionar um target

---

## Licença

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)

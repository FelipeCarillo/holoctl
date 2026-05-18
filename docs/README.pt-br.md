# holoctl

> **Sistema operacional vivo para projetos com assistentes de IA.** Fonte única em `.holoctl/`, compilada pra qualquer coisa que Claude Code, GitHub Copilot, OpenAI Codex ou qualquer ferramenta que respeite AGENTS.md (Aider, Zed, Junie, Jules, Factory, goose…) leia. Memória durável cross-assistente, curador autônomo, compilação multi-target, servidor MCP, dashboard web — tudo versionado ao lado do seu código.

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

---

## TL;DR — três comandos

```bash
# 1. Instalar (escolha um — se `hctl` não cair no PATH, ver "Instalação")
uv tool install holoctl                      # recomendado
# ou:  pipx install holoctl
# ou:  pip install holoctl                   # ⚠️ exige venv ativo (ver abaixo)

# 2. Plantar o roteador global (uma vez por máquina, por assistente)
hctl setup-global --target all               # Claude + Copilot
# (Codex consome o AGENTS.md + .codex/config.toml emitidos por `hctl init` — sem setup global)

# 3. Inicializar um projeto
cd ~/meu-projeto && hctl init
```

Abra Claude Code (ou qualquer assistente suportado) em `~/meu-projeto` e digite `/holoctl`. O agente lê o workspace, faz discovery, sugere personas especialistas, popula contexto, e mostra o overview — autonomamente.

---

## Sumário

1. [Por que holoctl](#por-que-holoctl)
2. [Anatomia do `.holoctl/`](#anatomia-do-holoctl)
3. [Instalação](#instalação) — incluindo a **pegadinha do venv com `pip`**
4. [Setup global por máquina](#setup-global-por-máquina)
5. [Inicialização por projeto](#inicialização-por-projeto)
6. [O slash command `/holoctl` — o que ele faz de verdade](#o-slash-command-holoctl)
7. [Compilação cross-tool](#compilação-cross-tool)
8. [MCP vs CLI — escolha de design](#mcp-vs-cli)
9. [Workflows do dia a dia](#workflows-do-dia-a-dia)
10. [Referência de comandos](#referência-de-comandos)
11. [Configuração](#configuração)
12. [Hooks de lifecycle](#hooks-de-lifecycle)
13. [Guia por assistente](#guia-por-assistente) — Claude / Copilot / Codex
14. [Coverage e doctor](#coverage-e-doctor)
15. [Privacidade e coexistência](#privacidade-e-coexistência)
16. [Troubleshooting](#troubleshooting)
17. [FAQ](#faq)
18. [Migração de projctl / projhub](#migração-de-projctl--projhub)
19. [Roadmap](#roadmap)
20. [Documentação e licença](#documentação-e-licença)

---

## Por que holoctl

Cada assistente de IA tem suas primitivas nativas — Claude Code skills, Copilot prompts, Codex `.codex/config.toml`, AGENTS.md pro resto. Manter o mesmo contexto de projeto sincronizado entre todos é **manual, propenso a erro, e nunca está atualizado**.

`holoctl` é a **abstração que falta no ecossistema**: você escreve o contexto **uma vez** em `.holoctl/`, o compiler materializa os arquivos nativos certos pra cada ferramenta. Mais um CLI, um Kanban, uma camada de memória que sobrevive entre sessões, um journal de eventos, um curador autônomo que propõe melhorias estruturais, um servidor MCP, e um dashboard web — tudo construído em volta da mesma fonte de verdade.

**É "vivo" porque acorda entre sessões:**

- **Memória durável** em `.holoctl/memory/` — as mesmas notas aparecem no Claude (como skills), Copilot (como `.github/instructions/`) e Codex (via AGENTS.md) no formato nativo de cada um.
- **Journal de eventos** captura cada uso de ferramenta, edição e fronteira de sessão via hooks plantados automaticamente.
- **Curador autônomo** observa o journal e propõe novas personas, regras path-scoped, ou arquivamento de topics como tickets `meta:curate` no board. Você aprova movendo o ticket pra `done` — ele auto-executa.
- **Boot econômico de tokens** imprime ≤1KB de contexto sessão-zero (pendências, decisões recentes, topics disponíveis) pro assistente não queimar tokens carregando o `CLAUDE.md` inteiro.
- **Servidor MCP** expõe board / memória / journal / curator como ferramentas padrão (com permission gating granular no Claude Code).

---

## Anatomia do `.holoctl/`

```
seu-projeto/
├── .holoctl/                       ← fonte única de verdade, no git
│   ├── config.json                 ← nome, prefixo, statuses do board, targets
│   ├── instructions.md             ← compilado pra CLAUDE.md / AGENTS.md / .codex/AGENTS.override.md / .github/copilot-instructions.md
│   │
│   ├── board/                      ← Kanban + tickets
│   │   ├── WORKFLOW.md             ← doc da máquina de estados (managed by template)
│   │   ├── index.json              ← projeção auto-reconstruída de tickets/*.md
│   │   └── tickets/PRJ-001-*.md    ← cada ticket = 1 Markdown com frontmatter
│   │
│   ├── agents/                     ← personas ativas (só `boardmaster` após hctl init)
│   │   └── boardmaster.md          ← library (developer / reviewer / architect / researcher / dba / devops / security-auditor / tech-writer / agent-designer) adicionada sob demanda, ou crie nova com `/agent-new`
│   │
│   ├── commands/                   ← /board, /ticket, /spec, /sprint, /close, /decision, /status, /agent-new
│   │
│   ├── context/                    ← prosa de projeto
│   │   ├── objective.md            ← O quê / Por quê / Critérios de sucesso
│   │   ├── architecture.md         ← Stack / Estrutura / Padrões / Limites
│   │   ├── conventions.md          ← Estilo, naming, testes
│   │   ├── decisions/              ← ADRs (decisões trancadas)
│   │   └── documents/              ← docs livres
│   │
│   ├── memory/                     ← notas duráveis cross-assistente
│   │   ├── MEMORY.md               ← índice always-on
│   │   ├── .gitignore              ← exclui `_archived/` por default
│   │   └── topics/                 ← topics lazy / glob / always_on
│   │
│   ├── journal/                    ← JSONL diário de eventos
│   │   └── 2026-05-08.jsonl
│   │
│   ├── curator/                    ← estado do curator + metadata por ticket
│   │
│   ├── hooks/                      ← (opcional) hooks declarativos por evento de lifecycle
│   ├── rules/                      ← (opcional) regras path-scoped com frontmatter `paths:`
│   ├── skills/                     ← (opcional) skills custom com progressive disclosure
│   ├── output_styles/              ← (opcional) output styles específicos do Claude
│   ├── ignore                      ← (opcional) gitignore-style para listas de ignore por assistente
│   │
│   └── activity.jsonl              ← log bruto de atividade
│
├── …seu código
│
└── (outputs compilados — geralmente .gitignored)
    ├── AGENTS.md                   ← cross-tool universal (Codex / Aider / Zed / Junie / …)
    ├── CLAUDE.md                   ← Claude Code
    ├── .claude/                    ← Claude Code agents/commands/settings.json
    ├── .github/                    ← Copilot instructions + prompts + memory instructions
    ├── .vscode/mcp.json            ← config MCP pro Copilot-no-VSCode
    └── .codex/                     ← OpenAI Codex: AGENTS.override.md + config.toml (mcp_servers)
```

> **Pastas opcionais** (`hooks/`, `rules/`, `skills/`, `output_styles/`, `ignore`) **não são criadas pelo `hctl init`**. São superfícies opt-in que você cria quando precisa. Os compilers só emitem o que existe na fonte — input vazio produz output vazio (anti-overengineering).

---

## Instalação

**Requer Python ≥ 3.11.**

### Opção A — `uv tool` *(recomendado)*

```bash
uv tool install holoctl
hctl --version
```

`uv tool` cria um venv isolado automaticamente e coloca `hctl` no seu PATH. **Nada mais é necessário.**

### Opção B — `pipx`

```bash
pipx install holoctl
hctl --version
```

Mesmo isolamento que `uv tool`. Requer `pipx` (`pip install pipx && pipx ensurepath`).

### Opção C — `pip` *(⚠️ exige venv ativo)*

> **`pip install holoctl` num Python "pelado" em SO moderno falha com `error: externally-managed-environment` (PEP 668), ou — se você passa por cima — instala no Python do sistema e o `hctl` pode parar num diretório fora do PATH.**

O jeito confiável é criar um venv **dedicado pro holoctl** e ativar ele antes de rodar `hctl`:

```bash
# Linux / macOS
python3 -m venv ~/.venvs/holoctl
source ~/.venvs/holoctl/bin/activate
pip install holoctl
hctl --version

# Windows (PowerShell)
python -m venv $HOME\.venvs\holoctl
& $HOME\.venvs\holoctl\Scripts\Activate.ps1
pip install holoctl
hctl --version

# Windows (cmd.exe)
python -m venv %USERPROFILE%\.venvs\holoctl
%USERPROFILE%\.venvs\holoctl\Scripts\activate.bat
pip install holoctl
hctl --version
```

**Pegadinha do pip + venv:** o `hctl` só funciona **enquanto o venv estiver ativado**. Pra deixar sempre disponível, faz um wrapper:

```bash
# Linux/macOS — adicione ao ~/.bashrc ou ~/.zshrc
alias hctl="$HOME/.venvs/holoctl/bin/hctl"
```

```powershell
# Windows — adicione ao $PROFILE
function hctl { & "$HOME\.venvs\holoctl\Scripts\hctl.EXE" $args }
```

É exatamente esse atrito que `uv tool` e `pipx` evitam. **Se tiver escolha, use um dos dois.**

### Extra ML opcional

```bash
uv tool install "holoctl[ml]"        # ~250MB — adiciona detecção de paráfrase ONNX no curator
```

### Verificando a instalação

```bash
hctl --version              # 0.17.0+
hctl --help                 # lista completa de comandos
hctl doctor --global        # checa ~/.claude e ~/.copilot (vai reportar 'missing' até o passo 2)
```

---

## Setup global por máquina

`hctl setup-global` planta o **roteador `/holoctl`** na config user-level de cada ferramenta de IA, pra o slash command funcionar em qualquer pasta — mesmo antes do `hctl init`.

```bash
hctl setup-global --target all              # Claude + Copilot
hctl setup-global --target claude           # só Claude Code
hctl setup-global --target copilot          # só Copilot CLI
hctl setup-global --target all --dry-run    # preview sem escrever
```

O que é instalado:

| Ferramenta  | Arquivo                                            | Formato                                | Bloco idempotente |
|-------------|----------------------------------------------------|----------------------------------------|-------------------|
| Claude Code | `~/.claude/commands/holoctl.md` + `~/.claude/skills/holoctl-router/` | Slash command + skill com references   | substitui arquivos |
| Copilot     | `~/.copilot/AGENTS.md`                              | Bloco markdown anexado                 | markers `<!-- holoctl:start … end -->` |

Codex e outros assistentes que respeitam AGENTS.md (Aider, Zed, Junie, Jules, Factory, goose) consomem o `AGENTS.md` per-project emitido por `hctl compile --target agents` — não têm superfície user-level pra slash routers, então `setup-global` é no-op pra eles.

**Detectando drift:**

```bash
hctl doctor --global
```

Saída:

```
holoctl: global-check
  ✓ Claude         router up-to-date (~/.claude/commands/holoctl.md)
  ✓ Copilot        holoctl block present (~/.copilot/AGENTS.md)

  All global routers up-to-date.
```

---

## Inicialização por projeto

Dentro da pasta do projeto:

```bash
cd ~/meu-projeto
hctl init
```

O que o `init` faz, em ordem:

1. Cria a estrutura `.holoctl/` (board, agents, commands, context, memory, journal).
2. Escreve `config.json` com nome inferido do projeto (= `cwd.name`), prefixo (= iniciais), e o **catálogo de providers** shipado (Linear / GitHub / Trello / Azure DevOps / Jira / Slack — padrões de URL mapeados pras MCP fetch tools).
3. Materializa `boardmaster.md` (única persona obrigatória — dona do lifecycle de tickets). Todas as outras (developer / reviewer / architect / researcher / dba / devops / security-auditor / tech-writer / agent-designer) ficam latentes na library até `hctl agent add <name>` ou `/agent-new` ativar.
4. Materializa `instructions.md`, `WORKFLOW.md`, `_template.md` de ticket, e oito commands default (`/status`, `/ticket`, `/spec`, `/board`, `/sprint`, `/decision`, `/close`, `/agent-new`).
5. Planta hooks de lifecycle do Claude (`SessionStart` → `hctl boot`, `Stop` → `hctl handoff`, deny-list pra arquivos derivados) e skills reativas built-in (`holoctl-router`, `holoctl-spec-flow`, `holoctl-provider-mcp`, `holoctl-work-item-router`, `holoctl-persona-suggester`, `holoctl-ticket-discipline`, `holoctl-memory-discipline`, `holoctl-parallel-evaluator`).
6. Escreve config do servidor MCP (`.claude/settings.json:mcpServers.holoctl`).
7. Compila os targets default (`agents` + `claude`).

**Flags:**

```bash
hctl init --name "Meu Projeto" --prefix "MP"          # explícito
hctl init --targets agents,claude,copilot,codex       # set custom de targets
hctl init --bare                                       # só skeleton — sem compile/hooks/MCP
hctl init --skip-compile                               # init sem compilar ainda
```

Re-rodar `hctl init` num workspace já inicializado é **idempotente** — re-sincroniza arquivos managed by template (`commands/*.md`, `WORKFLOW.md`, `_template.md`, `boardmaster.md`) sem mexer em arquivos do usuário (tickets, agents editados à mão, context docs, rules/skills/hooks custom).

Se você atualizar o `holoctl` depois do `init`:

```bash
hctl upgrade --check     # mostra slice do CHANGELOG
hctl upgrade             # aplica migrações + recompila
```

---

## O slash command `/holoctl`

É o **cérebro de roteamento**. Depois dos passos 2 + 3 acima, digite `/holoctl` (ou invoque a skill equivalente) em qualquer assistente. O agente roda:

```text
hctl doctor
```

A primeira linha do output é router-friendly — uma de:

| Primeira linha                    | Fluxo     | O que o agente faz a seguir                                                          |
|-----------------------------------|-----------|---------------------------------------------------------------------------------------|
| `holoctl: not initialized`        | Fluxo A   | `hctl init` → discovery do codebase → sugere personas → seed memória → `hctl overview`|
| `holoctl: outdated`               | Fluxo B   | `hctl upgrade --check`, pede confirmação, depois `hctl upgrade` + `hctl boot`         |
| `holoctl: ok`                     | Fluxo C   | `hctl boot` (≤1KB teaser), reage a tickets pendentes / sugestões do curator           |

**Fluxo A em detalhe** (o mais importante — primeira vez num projeto):

1. **Detect.** `hctl doctor` retorna `not initialized`.
2. **Init.** `hctl init --name "<inferido>" --prefix "<PRX>"`.
3. **Discover.** Lê em paralelo: README, package files (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, …), top-level dirs, configs de lint, configs de IA existentes (read-only — nunca sobrescreve).
4. **Configure.**
   - Sub-repos: se múltiplos sub-projetos detectados, **uma pergunta agregada** ("Achei backend/, frontend/, mobile/. Registro todos?"), depois `hctl repo add` pra cada aprovado.
   - Context files: escreve `.holoctl/context/{objective,architecture,conventions}.md` e `.holoctl/instructions.md` direto do que leu. Sem confirmação por arquivo.
   - Escape de ambiguidade: se o README tá genérico/ausente, **uma pergunta** pra esclarecer o objetivo. Senão, sem perguntas.
5. **Sugerir personas.** `hctl agent suggest` mapeia o stack detectado → personas da library expandida (developer / reviewer / architect / researcher / dba / devops / security-auditor / tech-writer / agent-designer). Exemplos: SQL + `migrations/` → `dba`; `.github/workflows/` + `Dockerfile` + Terraform → `devops`; `docs/` com muitos `.md` → `tech-writer`. Quando nenhuma persona da library encaixa no repo, `/agent-new <nome>` invoca o `agent-designer` pra desenhar uma sob medida pro seu stack.
6. **Seed de memória.** Cria `.holoctl/memory/topics/project-overview.md` com 3-5 linhas derivadas do README + package files. É isso que o `hctl boot` lê na sessão 2 pro agente "acordar" sabendo o que é o projeto.
7. **Overview & próxima ação.** Roda `hctl overview` (snapshot canônico) e `hctl boot` (teaser). Reage: propõe criar o primeiro ticket, ou mostra sugestões do curator, ou aponta o próximo p1.

**Tempo total**: ~30 segundos, com 1-2 perguntas no caminho.

---

## Compilação cross-tool

`hctl compile` lê `.holoctl/` e emite arquivos no formato nativo de cada target. Targets:

```bash
hctl compile --target agents              # AGENTS.md (cross-tool universal)
hctl compile --target claude              # CLAUDE.md + .claude/...
hctl compile --target copilot             # .github/copilot-instructions.md + .github/prompts/... + .vscode/mcp.json
hctl compile --target codex               # .codex/AGENTS.override.md + .codex/config.toml (mcp_servers)
hctl compile                              # todos os targets em config.targets[]
```

**O target `agents`** emite `AGENTS.md` no root do repo — o standard [agents.md](https://agents.md/) adotado por OpenAI Codex, Aider, Zed, JetBrains Junie, Google Jules, Factory, goose e outros assistentes AGENTS.md-aware. Sempre inclua nos seus `targets` (a config default já inclui).

**Matriz de cobertura** — o que cada compiler emite de cada fonte em `.holoctl/`:

| Fonte em `.holoctl/`          | claude                            | copilot                                      | codex                          | agents                              |
|-------------------------------|-----------------------------------|----------------------------------------------|--------------------------------|-------------------------------------|
| `instructions.md`             | `CLAUDE.md`                       | `.github/copilot-instructions.md`            | `.codex/AGENTS.override.md`    | `AGENTS.md` (Objective/Architecture)|
| `agents/*.md`                 | `.claude/agents/<n>.md`           | —                                            | —                              | —                                   |
| `commands/*.md`               | `.claude/commands/<n>.md`         | `.github/prompts/<n>.prompt.md`              | —                              | —                                   |
| `context/*.md`                | (via instructions/memory)         | (via instructions)                           | (via instructions override)    | corpo do `AGENTS.md`                |
| `memory/topics/*.md`          | `.claude/skills/holoctl-mem-*`    | `.github/instructions/holoctl-mem-*`         | —                              | —                                   |
| `hooks/*.json` *(opt)*        | merge em `.claude/settings.json`  | merge em `.copilot/config.json`              | —                              | —                                   |
| `rules/*.md` *(opt)*          | `.claude/rules/<n>.md`            | —                                            | —                              | —                                   |
| `skills/<n>/SKILL.md` *(opt)* | `.claude/skills/<n>/...`          | —                                            | —                              | —                                   |
| `output_styles/*.md` *(opt)*  | `.claude/output_styles/`          | —                                            | —                              | —                                   |
| Servidores MCP (config)       | `.claude/settings.json:mcp`       | `.vscode/mcp.json`                           | `.codex/config.toml:mcp_servers` | —                                 |

> Veja `hctl coverage` pra uma versão dessa tabela em tempo real, específica do seu workspace.

---

## MCP vs CLI

### Design atual: skills e agentes preferem MCP, com fallback pra CLI / paste

Desde a v0.17, slash commands, agentes e skills reativas **preferem o servidor MCP quando está rodando**, caindo pra `hctl` CLI (ou paste, pra conteúdo externo) quando não. Exemplos:

- Boardmaster chama `mcp__holoctl__board_create({...})` primeiro; CLI `hctl board add '<json>'` é o fallback documentado.
- `/spec` invoca a skill `holoctl-provider-mcp` pra buscar o corpo do card externo via MCP do provider (Linear / GitHub / Trello / Azure DevOps / Jira / Slack — ou um board interno custom registrado via `hctl provider add`); paste é o fallback, com `source_*` preservados em qualquer caso. O servidor MCP é auto-spawnado pelo Claude (via `.claude/settings.json:mcpServers`), Copilot (via `.vscode/mcp.json`) ou Codex (via `.codex/config.toml:[mcp_servers.holoctl]`).
- `/agent-new` chama `mcp__holoctl__agent_create` pra materializar a persona desenhada; edição manual de `.md` continua sendo a saída de emergência.
- O roteador `/holoctl` ainda roda `hctl doctor` / `hctl init` / `hctl boot` no shell — esses não têm equivalente MCP porque inicializam ou encerram a própria sessão do assistente.

A CLI continua sendo a **fonte de verdade** — cada tool MCP mapeia 1:1 pra um subcomando `hctl` — mas MCP é o caminho preferido dentro do loop do assistente por causa de permission gating granular, velocidade in-process depois do handshake, e output JSON estruturado que encadeia naturalmente.

### O servidor MCP

`hctl init` escreve a config MCP pra cada assistente conseguir spawnar `hctl serve --mcp` sob demanda. O servidor expõe **25 tools**:

| Read tools (auto-aprovadas)       | Write tools (`permissions.ask`)   |
|----------------------------------|------------------------------------|
| `holoctl.board_list`             | `holoctl.board_create`             |
| `holoctl.board_children`         | `holoctl.board_batch`              |
| `holoctl.board_get`              | `holoctl.board_move`               |
| `holoctl.board_show`             | `holoctl.board_set`                |
| `holoctl.memory_list_topics`     | `holoctl.board_ack`                |
| `holoctl.memory_read_topic`      | `holoctl.board_note`               |
| `holoctl.memory_search`          | `holoctl.board_delete`             |
| `holoctl.journal_recent`         | `holoctl.board_batch_move`         |
| `holoctl.agent_list_available`   | `holoctl.board_batch_set`          |
| `holoctl.curate_suggestions`     | `holoctl.board_batch_delete`       |
| `holoctl.config_show`            | `holoctl.memory_add`               |
|                                  | `holoctl.agent_add`                |
|                                  | `holoctl.agent_create`             |
|                                  | `holoctl.curate_silence`           |

`holoctl.config_show` é o que a skill `holoctl-provider-mcp` lê pra descobrir o catálogo de providers em runtime — sem lista de URL hardcoded dentro da skill.

### Trade-offs MCP-preferred

| Critério          | CLI                                                  | MCP                                                          |
|-------------------|------------------------------------------------------|--------------------------------------------------------------|
| Universalidade    | Roda em qualquer terminal, qualquer agente.         | Exige cliente MCP-aware.                                     |
| Reprodutibilidade | Humano consegue re-rodar o comando exato.           | Tool calls são JSON-RPC, menos amigável pra replay manual.   |
| Velocidade        | Fork de Python (~80-150ms cold).                    | In-process após handshake (mais rápido depois da 1ª chamada).|
| Permission gating | Grossa — depende de allow-list do shell.            | **Granular** — por ferramenta, write tools caem em `ask`.    |
| Saída             | Texto rich formatado pra humano.                    | JSON estruturado pra máquinas/cadeias.                       |

A CLI é **sempre** o fallback. Se o servidor MCP cai (ou nunca foi iniciado), o assistente usa `hctl` direto e tudo continua funcionando — inclusive de um terminal sem nenhuma ferramenta de IA ativa.

---

## Workflows do dia a dia

### Spec-Driven Development (`/spec`)

Transforma um card externo ou um brief multi-parágrafo num **spec** estruturado em `.holoctl/`, depois decompõe automaticamente em tasks filhas parallel-safe.

```text
/spec https://linear.app/eng/issue/ENG-42
```

O que acontece:

1. **Provider MCP discovery.** A skill `holoctl-provider-mcp` casa o URL contra o catálogo de providers (`hctl provider list`). Se o MCP do Linear está conectado (`.mcp.json`), busca o card direto. Se não, cai pra "cola o corpo aqui" — com `source_provider`, `source_ref`, `source_url`, `source_label` preservados em qualquer caso.
2. **Discuss.** Uma pergunta agregada pra refinar scope, acceptance criteria, arquivos tocados, edge cases. Pula quando o conteúdo da fonte já é explícito.
3. **Materializar spec.** `mcp__holoctl__board_create({kind: "spec", source_*, acceptance, context, ...})`.
4. **Decompor.** `holoctl-parallel-evaluator` parte o trabalho em tasks filhas disjuntas; boardmaster chama `mcp__holoctl__board_batch({shared: {parent: SPEC_ID, source_*, ...}, tickets: [...]})`. A CLI rejeita o batch se quaisquer dois filhos tocam o mesmo arquivo.
5. **Propor execução.** "Ativo `developer` em `PRJ-NNN+1`?"

Você também pode `/spec` com texto livre (sem URL) — mesmo fluxo, sem o passo de MCP fetch.

### Providers de board externo (`hctl provider`)

Gerencia o catálogo que mapeia padrão de URL → MCP fetch tool. Defaults shipados cobrem Linear, GitHub, Trello, Azure DevOps, Jira e Slack.

```bash
hctl provider list                          # mostra catálogo atual com status
hctl provider test linear https://linear.app/eng/issue/ENG-42  # dry-run do match de URL
hctl provider enable linear                 # auto / always / disabled
hctl provider disable jira

# Adicionar board interno custom:
hctl provider add acme \
  --mcp-fetch mcp__acme__get_card \
  --url-pattern '^https?://board\.acme\.corp/c/(?P<ref>[A-Z0-9]+)' \
  --label-template '{ref}: {title}'
```

Quando o catálogo e o MCP tool alinham, `/spec` e `holoctl-work-item-router` usam o fetch transparente. Quando o MCP não está conectado, as skills caem pra paste — nunca fingem fetch silencioso.

### Criar ticket

```bash
hctl board add '{
  "title": "Adicionar JWT auth",
  "agent": "developer",
  "priority": "p1",
  "projects": ["backend"],
  "goal": [
    "JWT signing implementado",
    "Testes cobrem token feliz + inválido",
    "Lint e build passam"
  ],
  "context": "Sessões são via cookie hoje; OAuth landing requer bearer."
}'
```

Ou no chat: *"cria ticket p1 pro JWT auth, agente developer, com goal: signing, testes, lint"*. O agente (boardmaster) traduz e roda o comando.

### Criação batch parallel-safe

```bash
hctl board batch '{
  "shared": { "tags": ["par:auth-flow"], "projects": ["backend"] },
  "tickets": [
    { "title":"JWT signing", "agent":"developer", "priority":"p1", "files":["src/auth/jwt.py"], "goal":["sign() emite HS256","testes"] },
    { "title":"Auth middleware", "agent":"developer", "priority":"p1", "files":["src/middleware/auth.py"], "goal":["verify+expiry","testes"] },
    { "title":"Auth integration tests", "agent":"reviewer", "priority":"p1", "files":["tests/test_auth.py"], "goal":["happy/expired/invalid"] }
  ]
}'
```

A CLI **rejeita o batch** se quaisquer dois tickets tocam o mesmo arquivo (prova não-sobreposição antes de criar).

### Mover tickets

```bash
hctl board move PRJ-001 doing
hctl board set PRJ-001 priority p0
hctl board ls --status doing --priority p1
```

### Memória

```bash
hctl memory add api-conventions --scope glob -g "src/api/**" \
  -d "Naming de API, envelope de erro, paginação"
hctl memory list
hctl memory search "JWT"
hctl memory get api-conventions          # ler corpo
hctl memory archive topic-antigo         # move pra topics/_archived/
```

Escopos de topic:

- `always_on` — sempre incluído no contexto do assistente (use com parcimônia).
- `lazy` — referenciado no MEMORY.md, agente carrega quando relevante.
- `glob` — só carregado quando o assistente está editando arquivos que casam com o glob.

### Personas

```bash
hctl agent list                          # ativas vs library
hctl agent suggest                       # heurística — o que ativar baseado no codebase
hctl agent suggest --json                # machine-readable pra automação
hctl agent add developer                 # materializa da library
hctl agent add custom --from developer   # copia de uma persona ativa como base
hctl agent remove developer              # desativa (continua na library)
```

Library (v0.17): `developer`, `reviewer`, `architect`, `researcher`, `dba`, `devops`, `security-auditor`, `tech-writer`, `agent-designer`. `hctl agent suggest` casa globs do `paths:` contra seu repo (ex.: `**/*.sql` → `dba`, `**/.github/workflows/**` → `devops`).

Quando nenhuma persona da library cabe no repo, desenhe uma sob medida:

```text
/agent-new payments-specialist
```

O slash command delega pra persona `agent-designer`, que lê o repo (README, package files, top-level dirs), monta um corpo de persona schema-correto (`name` / `description` / `tools` / `paths` / `model`), salva como `.holoctl/agents/<name>.draft.md`, e pede confirmação antes de materializar via `mcp__holoctl__agent_create`. A skill reativa `holoctl-persona-suggester` também levanta "quer uma persona nova pra esse gap?" sempre que o trabalho toca paths que nenhuma persona ativa cuida.

### Fechando uma sessão

```bash
hctl handoff                             # adiciona 1 linha em memory/topics/session-trail.md
hctl handoff --note "Fechei a 0.14"      # com nota custom
```

Se os hooks de lifecycle estão instalados (o `hctl init` faz isso pro Claude), o `Stop` roda `hctl handoff --auto` automaticamente — você não precisa lembrar.

### Boot de sessão (continuidade)

```bash
hctl boot                                # ≤1KB teaser
hctl boot --target claude                # registra a fonte no journal
hctl boot --plain                        # ASCII (sem códigos de cor — usado pelos hooks)
```

Exemplo de saída:

```text
## Meu Projeto — sessão 7
Pendências p0/p1: PRJ-003 Add JWT auth, PRJ-005 Fix N+1 in /tickets
Decisões recentes: 2026-05-04-jwt-vs-sessions, 2026-05-01-monorepo
Topics: api-conventions, decisions, session-trail
Personas ativas: boardmaster, developer, reviewer
⚡ 2 sugestão do curador (PRJ-042, PRJ-043) — `hctl curate show`
```

### Curator

```bash
hctl curate run --auto                   # rate-limited (1/dia, supressão 14d por padrão)
hctl curate show                         # tickets meta:curate abertos
hctl curate apply PRJ-042                # roda a ação proposta manualmente
hctl curate silence <pattern_id>         # supressão por 14 dias
hctl board move PRJ-042 done             # ← aprovação auto-executa a ação
```

### Dashboard web

```bash
hctl serve                               # http://127.0.0.1:4242
hctl serve --host 0.0.0.0 --port 8000    # exposição de rede opt-in (avisa: sem auth)
```

Abas: **Board** (Kanban / Lista / Timeline com SSE), **Repos**, **Agents**, **Commands**, **Context**.

### Servidor MCP

```bash
hctl serve --mcp                         # MCP via stdio — assistentes spawnam sob demanda
```

Configurado automaticamente pelo `hctl init` — você não precisa rodar manualmente. Pra testar standalone, use `--mcp`.

---

## Referência de comandos

| Comando                              | O que faz                                                                     |
|--------------------------------------|--------------------------------------------------------------------------------|
| `hctl init`                          | Cria ou sincroniza `.holoctl/` (idempotente).                                  |
| `hctl setup`                         | Planta a skill `/holoctl` em cada assistente detectado (legado — ver `setup-global`). |
| `hctl setup-global --target X`       | Instala roteador global pra ferramenta X (Claude / Copilot / all).             |
| `hctl upgrade`                       | Migra workspace + recompila pra versão instalada.                              |
| `hctl compile --target X`            | Gera arquivos de integração com a IA. Default = `config.targets[]`.            |
| `hctl serve [--mcp]`                 | Dashboard web (4242), ou servidor MCP via stdio.                               |
| `hctl doctor [--global]`             | Health check. Primeira linha = router-friendly.                                |
| `hctl coverage [--only-present] [--target X]` | Matriz fonte `.holoctl/` → outputs por target.                        |
| `hctl overview`                      | Snapshot do workspace em uma tela.                                             |
| `hctl boot [--target X]`             | Contexto sessão-zero ≤1KB. Registrado no journal.                              |
| `hctl handoff [--note "..."]`        | Adiciona linha ao session-trail. Auto-chamado pelo hook Stop.                  |
| `hctl board <ls\|add\|move\|set\|batch\|get\|body\|stat\|rebuild-index>` | Tickets.   |
| `hctl agent <list\|suggest\|add\|remove>` | Personas (library + ativas).                                              |
| `hctl provider <list\|add\|enable\|disable\|test\|remove>` | Catálogo de boards externos — padrão de URL → MCP fetch tool. |
| `hctl memory <list\|add\|get\|search\|archive\|seed>` | Memória durável.                                              |
| `hctl journal <record\|show\|count\|tail\|import>` | Journal de eventos.                                              |
| `hctl curate <run\|show\|apply\|silence>` | Curator autônomo.                                                         |
| `hctl repo <list\|add\|info>`        | Subprojetos (auto-discovered + overrides manuais).                             |

Todo comando aceita `--help`.

---

## Configuração

`.holoctl/config.json` — só sobrescreve o que precisar:

```json
{
  "holoctlVersion": "0.17.0",
  "project": {
    "name": "Meu Projeto",
    "prefix": "MP",
    "repos": [
      { "path": "./backend", "name": "backend", "description": "Serviço FastAPI" }
    ]
  },
  "board": {
    "statuses": ["backlog", "doing", "review", "done", "cancelled"],
    "priorities": ["p0", "p1", "p2", "p3"],
    "idPadding": 3
  },
  "git": { "checkDirty": false },
  "targets": ["agents", "claude", "copilot", "codex"],
  "server": { "port": 4242, "theme": "dark" },
  "providers": {
    "linear":  { "enabled": "auto", "url_pattern": "...", "mcp_fetch_tool": "mcp__linear__get_issue",   "label_template": "{ref}: {title}" },
    "github":  { "enabled": "auto", "url_pattern": "...", "mcp_fetch_tool": "mcp__github__get_issue",   "label_template": "{org}/{repo}#{ref}: {title}" }
    /* trello, azure_devops, jira, slack também shipados — ver `hctl provider list` */
  }
}
```

**Notas:**

- `targets` controla o que o `hctl compile` emite quando chamado sem `--target`. Adicionar um target requer `hctl compile --target X` uma vez pra materializar.
- `git.checkDirty` é **false** por default — holoctl lê `.git/HEAD`/`refs`/`config` direto sem spawnar `git status`. Instantâneo no Windows + AV corporativo.
- `board.idPadding: 3` produz `MP-001` (vs 2 → `MP-01`).
- `providers` é populado aditivamente no `load_config` — workspaces de versões anteriores ganham os defaults shipados automaticamente. Use `hctl provider add` / `enable` / `disable` em vez de editar à mão.
- Adicionar campo novo num ticket: só escreve no frontmatter do `.md` e roda `hctl board rebuild-index`.

---

## Hooks de lifecycle

`hctl init` escreve `.claude/settings.json` com hooks plantados por default:

```json
{
  "hooks": {
    "SessionStart": [
      { "type": "command", "command": "hctl journal record session_start --source claude --quiet" },
      { "type": "command", "command": "hctl boot --plain --target claude",
        "description": "Imprime teaser sessão-zero antes do usuário digitar" }
    ],
    "PreToolUse": [
      { "type": "command", "matcher": "Edit|Write",
        "command": "hctl journal record write_attempt --stdin --quiet --deny-glob '.holoctl/board/index.json,.holoctl/memory/MEMORY.md,.holoctl/activity.jsonl'",
        "description": "Bloqueia escrita direta em estado derivado — força uso da CLI" }
    ],
    "PostToolUse": [
      { "type": "command", "command": "hctl journal record tool_use --stdin --quiet" }
    ],
    "Stop": [
      { "type": "command", "command": "hctl journal record stop --quiet" },
      { "type": "command", "command": "hctl handoff --quiet --auto",
        "description": "Persiste session-trail em todo Stop. --auto pula sessões triviais." }
    ]
  },
  "permissions": {
    "ask": [ "mcp__holoctl__board_create", "mcp__holoctl__memory_add", "..." ],
    "deny": [ "Write(.holoctl/board/index.json)", "Edit(.holoctl/memory/MEMORY.md)", "..." ]
  }
}
```

**A deny-list é a aplicação efetiva** da regra "nunca edite estado derivado à mão" — mesmo se o agente esquecer a instrução, o harness bloqueia a tool call.

Copilot recebe `.copilot/config.json` (allow/deny lists). Codex não tem API pública de hooks per-project — o lifecycle é tratado pelo user agent e pelo conteúdo do AGENTS.md.

---

## Guia por assistente

### Claude Code

Depois de `hctl setup-global --target claude` e `hctl init`:

- **Slash command**: `/holoctl` (seu roteador global).
- **Contexto de projeto**: `CLAUDE.md` + referência `@.holoctl/memory/MEMORY.md` (auto).
- **Subagentes**: `.claude/agents/<name>.md` — invocáveis via tool `Agent`.
- **Hooks**: `.claude/settings.json:hooks` (boot teaser no SessionStart, handoff no Stop, deny-list no PreToolUse).
- **MCP**: `.claude/settings.json:mcpServers.holoctl` roda `hctl serve --mcp`.

```bash
# Verificar
hctl doctor                        # saúde do workspace
hctl doctor --global               # drift de instalação dos roteadores
ls .claude/                        # agents/, commands/, settings.json
```

### GitHub Copilot

Depois de `hctl setup-global --target copilot` e `hctl init`:

- **Global**: `~/.copilot/AGENTS.md` — bloco anexado com markers `<!-- holoctl:start … end -->`.
- **Projeto**: `.github/copilot-instructions.md`, `.github/prompts/<name>.prompt.md`.
- **Memória**: `.github/instructions/holoctl-memory-*.instructions.md` com glob `applyTo:`.
- **MCP**: `.vscode/mcp.json`.
- **Permissões**: deny-list e allow-list via flags em `.copilot/config.json`.

Copilot acumula conteúdo do AGENTS.md (não sobrescreve) — o bloco do holoctl coexiste com qualquer outra coisa que você tem.

### OpenAI Codex

Depois de `hctl init` com `codex` em `config.targets` (ou `hctl compile --target codex`):

- **AGENTS.md de projeto** no root do repo (emitido pelo target `agents` — Codex lê isso nativamente, conforme a spec).
- **Override específico do Codex**: `.codex/AGENTS.override.md` — compilado de `.holoctl/instructions.md`. Codex faz merge desse arquivo por cima do `AGENTS.md` root, então é o lugar certo pra guidance só do Codex sem poluir o arquivo cross-tool.
- **MCP**: `.codex/config.toml:[mcp_servers.holoctl]` declara o servidor stdio do holoctl. Codex carrega `.codex/config.toml` quando você confia no projeto (`codex trust .` ou o prompt na primeira vez).

Sem `setup-global` — Codex não tem superfície documentada user-level pra slash routers.

### Aider / Zed / Junie / Jules / Factory / goose / outros

Qualquer ferramenta que respeita `AGENTS.md` lê o arquivo emitido por `hctl compile --target agents`. Sem config específica por ferramenta — só mantém `agents` em `config.targets` (já vem por default).

---

## Coverage e doctor

### `hctl coverage`

Mostra a bifurcação entre fonte e target:

```bash
hctl coverage                        # todas as fontes × todos os targets
hctl coverage --only-present         # só fontes que existem nesse workspace
hctl coverage --target claude        # uma coluna só
```

Saída (filtrada):

```text
hctl coverage (source → per-target outputs)
  workspace: /home/me/meu-projeto
  active targets: agents, claude, copilot, codex

  Source                             | agents     | claude       | copilot       | codex
  ─────────────────────────────────────────────────────────────────────────────────────────────
  instructions.md                    | ✓ AGENTS   | ✓ CLAUDE.md  | ✓ .gh/copi.md | ✓ .cx/AGENTS.override
  agents/*.md                        | —          | ✓ .cl/agents | —             | —
  commands/*.md                      | —          | ✓ .cl/comma  | ✓ .gh/prompts | —
  memory/topics/*.md                 | —          | ✓ .cl/skills | ✓ .gh/instr   | —
  (servidores MCP)                   | —          | ✓ settings   | ✓ .vsc/mcp    | ✓ .cx/config.toml
```

### `hctl doctor`

```bash
hctl doctor                # saúde do workspace
hctl doctor --global       # drift de instalação dos roteadores globais
```

Primeira linha é **router-friendly** (parseada pelo `/holoctl`):

- `holoctl: not initialized` → não tem `.holoctl/` em cwd ou ancestrais.
- `holoctl: outdated` → workspace `holoctlVersion` < instalado `hctl --version`.
- `holoctl: ok` → workspace na versão atual.
- `holoctl: global-check` → modo `--global`.

---

## Privacidade e coexistência

- **`hctl init` não escreve nada em `$HOME`.** Só `hctl setup-global` escreve — e só os arquivos do roteador em locais user-scope dos assistentes detectados.
- **Sem registro machine-wide, sem daemon, sem telemetria, sem auto-update check.** Workspace = `.holoctl/` ao lado do código. Esse é o footprint inteiro.
- **`.holoctl/memory/.gitignore`** já vem com `_archived/` excluído por default. Workspaces privacy-strict descomentam duas linhas pra deixar a árvore inteira de memória local-only.
- **Coexiste com auto-memory nativo.** O auto-memory do Claude Code **não** é desligado. `holoctl` adiciona uma referência `@.holoctl/memory/MEMORY.md` ao `CLAUDE.md` pra Claude ler ambas as fontes.
- **Outputs compilados** ficam melhor `.gitignore`'d (`.claude/`, `.codex/`, `.github/copilot-instructions.md`, `AGENTS.md`, `CLAUDE.md`) — são regenerados de `.holoctl/`. Times às vezes preferem commitar pra novos contribuidores que ainda não instalaram o holoctl.

---

## Troubleshooting

### `hctl: command not found`

- **`uv tool` / `pipx`**: deveria estar no PATH. Se não está, rode `uv tool update-shell` ou `pipx ensurepath` e reabra o terminal.
- **Instalação via `pip`**: se você não usou venv, bateu no PEP 668 ou instalou no Python errado. Refaça via método de venv da seção [Instalação](#instalação).
- **Workaround**: `python -m holoctl <subcomando>` funciona independente do PATH (com venv ativo).

### `/holoctl` não dispara

- Rode `hctl doctor --global`. Provavelmente você pulou `hctl setup-global`. Roda.
- Pra Codex/Aider/Zed/outras AGENTS.md-aware: não têm roteador global — consomem o `AGENTS.md` per-project emitido por `hctl compile --target agents`.

### `No .holoctl/ found`

- Você não está num projeto que foi `hctl init`'ado. Ou roda `hctl init` aqui, ou `cd` num projeto que tem `.holoctl/`.
- `find_project_root` sobe na árvore procurando `.holoctl/config.json`. Se você está numa subpasta do projeto, ainda deveria achar.

### `hctl init` diz "Refusing to downgrade"

- O workspace foi criado com um `hctl` mais novo. Ou faz upgrade do seu `hctl` (`uv tool upgrade holoctl`) ou edita manualmente `.holoctl/config.json:holoctlVersion` (não recomendado).

### Compile produz outputs estagnados / `hctl doctor --global` sempre fala "drift"

- O usuário editou o roteador global à mão → drift detectado. Roda `hctl setup-global --target X --force` pra sobrescrever, ou aceita o drift se foi intencional.

### Edição Windows / problemas de path do Powershell

- O roteador global legado (pré-0.14) tinha um path absoluto hardcoded. Se você está atualizando de antes da 0.14: rode `hctl setup-global --target claude` pra substituir pela versão PATH-based.

### Servidor MCP não responde

- `hctl serve --mcp` é stdio-only. O assistente spawna via config MCP; cheque que `.claude/settings.json:mcpServers.holoctl.command` resolve pra um `hctl` válido (ou `python -m holoctl`).
- Defina a env var `HOLOCTL_BIN=/abs/path/to/hctl` pra sobrescrever a auto-detecção.

### Tests falham com `No module named 'httpx'`

- `tests/test_dashboard.py` usa `fastapi.testclient` que requer `httpx`. `httpx` já está declarado em `pyproject.toml` `[dependency-groups].dev` (PEP 735) — pego automaticamente por `uv sync`. Se você está usando `pip` puro (sem uv), instale manual: `pip install httpx pytest`. A matriz de CI usa `uv sync --frozen` e roda a suite completa sem skip.

---

## FAQ

**Sou obrigado a usar o slash command? Posso usar `hctl` direto?**

Sim. O CLI é a fonte de verdade — slash commands são conveniências. Tudo é fazível do terminal.

**Dá pra usar isso sem o assistente de IA?**

Sim. `hctl board`, `hctl memory`, `hctl serve` funcionam standalone. Você ganha um Kanban + camada de memória + servidor MCP mesmo sem ferramenta de IA nenhuma.

**Conflita com o auto-memory do Claude Code?**

Não — coexistem. Claude lê tanto `CLAUDE.md` (que referencia `.holoctl/memory/MEMORY.md`) quanto o auto-memory nativo. O curator pode promover padrões duráveis do auto-memory pra topics versionados.

**Dá pra compartilhar `.holoctl/` entre múltiplos repos num monorepo?**

Sim — esse é o design. `hctl init` na raiz do monorepo, depois `hctl repo add ./backend ./frontend ./mobile`. Tickets podem declarar `projects: [backend, shared]`.

**Como adiciono um target de compile novo (ex: pra uma ferramenta nova)?**

Adiciona um módulo em `holoctl/lib/compiler/<name>.py` expondo `compile_<name>(project_root, config, dry_run)`, registra em `compiler/__init__.py`. Ver `CONTRIBUTING.md`.

**Onde os dados ficam guardados?**

Tudo em `.holoctl/`, no seu repo, versionado por você. Sem cloud, sem banco, sem daemon.

**Posso customizar a library de personas?**

Sim. A library mora em `holoctl/templates/agents/` (read-only quando instalado via PyPI). Pra customizar: clona o repo, edita, e `pip install -e .` pra dev local. Ou override per-project: `hctl agent add custom --from developer` e edita `.holoctl/agents/custom.md`.

**O agente ignora meus context files**

Cheque que `.holoctl/instructions.md` está sendo compilado (não `.holoctl/context/objective.md` direto). O pipeline de compile faz merge: context → instructions → CLAUDE.md/AGENTS.md/etc. Roda `hctl coverage --only-present` pra ver o que está fluindo onde.

---

## Migração de projctl / projhub

Nomes anteriores deste projeto. holoctl lê diretórios `.projctl/` e `.projhub/` e **renomeia automaticamente pra `.holoctl/`** na próxima escrita. Tickets que usavam `scope: X` são lidos como `projects: [X]` e reescritos no próximo `board set` ou `rebuild-index`.

**Sem migração manual** — abre um workspace de `projctl`/`projhub` com `hctl` 0.14+ e ele é silenciosamente atualizado.

Se você tinha `~/.claude/commands/projctl.md` ou `projhub.md`: rode `hctl setup-global --target claude` pra instalar o novo `holoctl.md` e apague os legados manualmente.

---

## Roadmap

- **Sync bidirecional de provider** — fechar o card original no board externo quando o spec do holoctl chega em `done` (hoje o assistente só lembra o usuário).
- **Catálogo de providers expandido** — entradas contribuídas pela comunidade pra boards menos comuns (ClickUp, Asana, Notion, sistemas internos de RFC).
- **Curator v2** — detecção de padrão estrutural (ex.: "você fica editando os mesmos 3 arquivos juntos; quer uma rule?").
- **Ecossistema `.holoctl/skills/`** — skills compartilhadas pela comunidade com progressive disclosure (cross-tool via compile).
- **Extensão VS Code** — board view + navegação de memória na IDE.
- **Dashboard multi-workspace** — `hctl serve --multi` pra monorepos com muitos subprojetos.

---

## Documentação e licença

- [CHANGELOG.md](../holoctl/CHANGELOG.md) — release notes
- [ARCHITECTURE.md](../ARCHITECTURE.md) — design interno, pipeline de compile, threat model
- [SECURITY.md](../SECURITY.md) — relato de vulnerabilidades + threat model
- [CONTRIBUTING.md](../CONTRIBUTING.md) — setup de dev, convenções, como adicionar um target
- [README.md](../README.md) — versão em inglês deste README

MIT © [Felipe Carillo](https://github.com/FelipeCarillo)

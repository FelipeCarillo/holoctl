# {{project.name}}

{{project.descriptionOrFallback}}

## Invariantes (não negociáveis)

- O board é gerenciado **somente** pela CLI/MCP. Nunca edite `.holoctl/board/index.json` nem os `.md` em `.holoctl/board/tickets/` — o `permissions.deny` bloqueia, e seu edit não persiste.
- Tickets têm `acceptance` (Definition of Done) explícito. Trabalho sem ticket = trabalho não rastreado.
- Decisões duráveis viram ADRs em `.holoctl/context/decisions/` (use `/decision`). Imutáveis.
- Memória durável vai pra `.holoctl/memory/` via `{{commands.boardCliBin}} memory add` ou `mcp__holoctl__memory_add`. Não duplique no `CLAUDE.md`.

## Onde está o quê

- Tickets: `/board`, `/status`, ou `mcp__holoctl__board_list`
- Memória: @.holoctl/memory/MEMORY.md
- Decisões/ADRs: `.holoctl/context/decisions/`
- Personas: `{{commands.boardCliBin}} agent list` (ativas + library); `{{commands.boardCliBin}} agent add <name>` materializa da library; `/agent-new <nome>` desenha uma sob medida pro repo
- Boards externos: `{{commands.boardCliBin}} provider list/add/test` — catálogo que mapeia URL → MCP fetch tool. Defaults shipados: Linear, GitHub, Trello, Azure DevOps, Jira, Slack. Adicione boards internos com `{{commands.boardCliBin}} provider add --mcp-fetch <tool> --url-pattern '<regex>'`.

## Comandos rápidos

`/holoctl` `/status` `/ticket` `/spec` `/board` `/sprint` `/decision` `/close` `/agent-new`

`/spec` é o ponto de entrada do **Spec-Driven Development**. Aceita um **URL ou ref** de card externo (Linear/GitHub/Trello/Azure DevOps/Jira/Slack — ou board interno registrado via `{{commands.boardCliBin}} provider add`) **ou** uma descrição livre. Quando o MCP do provider está conectado em `.mcp.json`, o conteúdo é **buscado automaticamente** via skill `holoctl-provider-mcp`; quando não, fallback pra paste com `source_*` preservados a partir do URL. Em seguida: discute scope/acceptance → cria spec via `board_create` → decompõe em tasks filhas via `board_batch` → propõe ativação da próxima persona.

`/agent-new <nome>` invoca o `agent-designer`: lê o repo (README, package files, top-level dirs), propõe `description` / `tools` / `paths` / `model` sob medida, salva como `.draft.md` pra revisar e, com `y`, materializa via `mcp__holoctl__agent_create` + compile.

## Decisões fixadas

(esta seção é populada à medida que ADRs são criados em `.holoctl/context/decisions/`)

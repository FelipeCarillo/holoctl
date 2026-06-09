# Revisão completa do holoctl — 2026-06-09

Revisão de código cobrindo backend (`lib/`, `cli/`), compilador/templates/skills,
server + frontend + MCP, e testes/CI/empacotamento. Achados verificados
empiricamente onde marcado.

## 1. Entendimento do objetivo

O holoctl é um **"sistema operacional de projeto" para assistentes de código**:
uma fonte única de verdade em `.holoctl/` (tickets em Markdown+frontmatter,
memória durável, journal de eventos, curador autônomo), versionada junto com o
código. A genericidade vem de uma decisão arquitetural central: **compilador
nativo profundo só para Claude Code**; todos os outros assistentes (Copilot,
Cursor, Codex, Aider…) se autoconfiguram em runtime via a skill
`holoctl-foreign-bootstrap`, descoberta por um `AGENTS.md` mínimo. Isso evita
manter N compiladores Python em lockstep. Em volta: CLI (`hctl`), MCP server com
25 tools, dashboard web com SSE, e hooks de ciclo de vida (boot ≤1KB, handoff).

**Pontos fortes** (consenso dos revisores): sistema de manifest/ledger com
guarda de hand-edit (`manifest.py`), design do foreign-bootstrap, `metrics.py`
como funções puras, locking concorrente em `jsonl.py`, smoke test E2E do CI,
release via PyPI Trusted Publishers. Cold start do CLI medido: **~156ms** —
saudável para hooks de sessão, não é gargalo.

## 2. Correção e segurança (corrigir primeiro)

- **2.1 XSS confirmado no dashboard** — `server/markdown.py:21` usa o preset
  `gfm-like` do markdown-it, que habilita HTML cru; o resultado vai ao template
  com `| safe` (`views/detail.py:86`, `views/doc.py:9`). Verificado:
  `<img src=x onerror=alert(1)>` num corpo de ticket executa JS. Tickets podem
  vir de fontes externas (`/spec` com cards Linear/GitHub) e o servidor aceita
  `--host 0.0.0.0`. **Fix:** `MarkdownIt(..., {"html": False})` ou sanitizar com
  `nh3`/`bleach`. Idem `toast.js:14` — interpola `message` em `innerHTML`;
  trocar por `textContent`.
- **2.2 Parser de frontmatter trunca valores com `:`** — `lib/markdown.py:40-46`
  divide no primeiro `:`; `source_url: "https://..."` pode corromper. Tratar
  strings com aspas ou adotar `yaml.safe_load`.
- **2.3 Patch de frontmatter via regex** — `board.py:66-79` atualiza campos do
  `.md` com `re.sub`; falha silenciosamente se o campo não existe ou casa no
  corpo → drift entre `index.json` e o `.md`. **Fix:** parse → mutar dict →
  re-serializar.
- **2.4 Last-write-wins entre MCP server e CLI** — `board.py:265-297`: dois
  processos fazendo `_load()` → mutação → `_save()` do índice inteiro perdem
  escrita um do outro. **Fix:** lock de arquivo na janela load→save (infra já
  existe em `jsonl.py`) ou `mutationSeq` com re-read antes de salvar.
- **2.5 Comandos bootstrap fora do manifest** — `compiler/claude.py:204-218`
  escreve `/holoctl` e `/hctl-upgrade` direto sem passar pelo ledger: doctor não
  detecta staleness, hand-edits passam, `prune_orphans` não limpa. Fix de 1
  linha: `ledger.write(...)`.

## 3. Velocidade de desenvolvimento

| Ação | Esforço | Ganho |
|---|---|---|
| `pytest-xdist` (`-n auto`) | ~30min | ~960 testes em paralelo; feedback 4-6x mais rápido |
| `pytest-cov` + `--cov-fail-under` no CI | ~15min | Manifest tem só 4 testes; MCP stdio só 6 — sem visibilidade de gaps |
| `.pre-commit-config.yaml` (ruff check+format, mypy) | ~45min | Erros pegos antes do CI de 5-10min |
| `ruff format --check` no CI | ~15min | Elimina feedback manual de estilo |
| mypy cobrindo `holoctl/server/` | ~1h | `mcp.py` (973 linhas de JSON-RPC à mão) hoje excluído do type check |
| Versão em 1 lugar só | ~30min | Hoje em `pyproject.toml` + `__init__.py` + CHANGELOG |
| `pytest-timeout` + `--durations=10` | ~15min | Testes de subprocess podem travar o CI |

Refactors estruturais:

- **Templates como arquivos, não strings Python.** `lib/templates.py` tem 677
  linhas de Markdown em f-strings. Mover para
  `holoctl/templates/commands/*.md` e carregar em `get_templates()`. De quebra,
  **derivar `SYNC_TARGETS` automaticamente** das chaves de `get_templates()` —
  esse drift manual já causou o bug do `/spec` stale (admitido no comentário em
  `templates.py:6-11`).
- **Consolidar fixtures de teste.** Três padrões para criar workspace de teste
  (fixture `workspace`, `_seed_workspace()` em `test_boot.py`, CliRunner manual
  em `test_adopt.py`). Centralizar no `conftest.py`.

## 4. Performance em runtime

- **Releitura completa do board em toda operação.** `board.py:30` re-parseia
  `index.json` a cada chamada; dashboard instancia `Board()` + `ls()` por
  request; cada tool call do MCP refaz `load_config` + `Board`
  (`server/mcp.py:76-96`). Cache em memória invalidado por mtime resolve os três.
- **SSE com I/O bloqueante e sem limites.** `app.py:183-213`: polling de mtime a
  cada 2s com `read_text()` síncrono no event loop, sem limite de conexões nem
  keepalive. Fix: `asyncio.to_thread` + semáforo.
- **`children()` lê todos os `.md` dos filhos** (`board.py:241-252`) por view de
  detalhe — cachear contagem de checkboxes no `index.json`.
- **Compile reescreve todo arquivo owned mesmo sem mudança** (verificado em
  `manifest.py:346-352`). Comparar sha e pular a escrita preserva mtime e reduz
  churn.

## 5. Arquitetura e a tese "genérico para qualquer assistente"

- **`board.py` é um god module (~1010 linhas)** — I/O, validação, CRUD, batch,
  patch de Markdown e integração com curador. Separar em
  Store / Validator / Ops / Markdown.
- **Tickets são dicts sem schema** — formato espalhado por 5+ lugares. Um
  `dataclass`/`TypedDict` `Ticket` dá autocomplete e type check.
- **Foreign-bootstrap sem detecção de drift na volta** — usuário de Copilot que
  editar o `.github/` gerado perde a edição no próximo re-bootstrap, sem aviso.
  Incluir na skill um arquivo de hashes (espelhando `.compiled.json`) e aviso
  antes de sobrescrever.
- **Resolução de template silenciosa** (`compiler/template.py:24-40`) —
  placeholder inexistente vira texto literal. Adicionar modo `strict`.
- **MCP à mão vs. SDK** — considerar migrar para o SDK oficial `mcp` quando o
  protocolo evoluir, ou extrair factory de handlers (padrão repetido ×14).

## 6. Ordem sugerida

1. **Dia 1:** desligar HTML no markdown-it + fix do toast; `pytest-xdist` +
   `pytest-cov` + `pytest-timeout`; `ledger.write` nos comandos bootstrap;
   derivar `SYNC_TARGETS`.
2. **Semana 1:** lock no load→save do board; patch de frontmatter via
   parse/serialize; pre-commit + ruff format; mypy no `server/`.
3. **Incremental:** templates → arquivos `.md`; cache do Board; `Ticket`
   tipado; split do `board.py`; drift detection no foreign-bootstrap; compile
   incremental.

Nenhum item exige quebrar compatibilidade.

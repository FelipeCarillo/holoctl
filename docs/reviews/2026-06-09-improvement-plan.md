# Plano de melhorias do holoctl — 2026-06-09

Consolida os achados de `2026-06-09-code-review.md` e
`2026-06-09-frontend-review.md` num plano de execução faseado. Cada item tem
escopo, arquivos, critério de aceite (CA) e esforço estimado. As fases são
ordenadas por (risco evitado ÷ esforço); dentro de cada fase os itens são
independentes salvo quando indicado.

## Visão geral

| Fase | Tema | Esforço total | Release sugerido |
|---|---|---|---|
| 0 | Tooling e velocidade de desenvolvimento | ~1 dia | 0.20.x (sem mudança de produto) |
| 1 | Segurança (XSS) | ~½ dia | 0.20.x patch |
| 2 | Bugs de frontend quebrados em produção | ~½ dia | 0.20.x patch |
| 3 | Correção e robustez do backend | ~2 dias | 0.21.0 |
| 4 | Performance em runtime | ~2-3 dias | 0.21.x |
| 5 | Refactors estruturais | ~1-2 semanas, incremental | 0.22.0+ |
| 6 | UX e acessibilidade do dashboard | ~1-2 dias | oportunista |

Regra geral: **Fases 0-2 antes de qualquer outra coisa** — a Fase 0 faz todas
as fases seguintes ficarem mais baratas (testes paralelos, lint automático), e
as Fases 1-2 corrigem o que está efetivamente quebrado ou explorável hoje.

---

## Fase 0 — Tooling e velocidade de desenvolvimento (~1 dia)

### 0.1 Paralelizar a suite de testes
- **O quê:** `pytest-xdist` no grupo dev; CI roda `pytest -n auto`. Marcar
  testes de subprocess (`test_mcp_stdio.py`, `test_smoke_e2e.py`) com
  `@pytest.mark.serial` se houver colisão de cwd/porta.
- **Arquivos:** `pyproject.toml`, `.github/workflows/ci.yml`.
- **CA:** suite completa passa com `-n auto` local e no CI; tempo de CI da
  etapa de testes cai ≥50%.
- **Esforço:** 30min.

### 0.2 Medição de cobertura
- **O quê:** `pytest-cov`; CI publica `--cov=holoctl --cov-report=term-missing`.
  Começar **sem** `--cov-fail-under` (primeiro medir), introduzir o gate
  (sugestão: 75%) um release depois.
- **CA:** número de cobertura visível em todo run de CI; gaps conhecidos
  (manifest, MCP stdio, migrações de upgrade) documentados como issues.
- **Esforço:** 15min + análise.

### 0.3 Timeout e relatório de testes lentos
- **O quê:** `pytest-timeout` (`--timeout=60`) + `--durations=10` no CI.
- **CA:** nenhum teste pode travar o CI indefinidamente.
- **Esforço:** 15min.

### 0.4 Formatter + pre-commit
- **O quê:** `ruff format` como check no CI; `.pre-commit-config.yaml` com
  `ruff check --fix`, `ruff format`, `mypy` (escopo atual),
  trailing-whitespace. Rodar `ruff format` uma vez no repo inteiro num commit
  isolado ("format only, no logic").
- **CA:** `pre-commit run --all-files` limpo; CI falha em código não formatado.
- **Esforço:** 45min.

### 0.5 ESLint para o frontend
- **O quê:** `eslint.config.js` (flat config) com `no-undef`,
  `no-unused-vars`, `eqeqeq`; job de CI (node 20, sem package.json pesado —
  `npx eslint holoctl/server/static/js`). Esta regra teria pego os 3 módulos
  quebrados da Fase 2.
- **CA:** ESLint roda no CI; os erros atuais de `no-undef` aparecem (serão
  zerados pela Fase 2).
- **Esforço:** 30min.

### 0.6 Expandir mypy para `holoctl/server/`
- **O quê:** incluir `holoctl/server` no escopo do mypy (CI), começando por
  `mcp.py` (973 linhas de JSON-RPC à mão — maior risco). Aceitar
  `# type: ignore` pontuais nas views; não travar nisso.
- **Arquivos:** `pyproject.toml` `[tool.mypy]`, `ci.yml:35`.
- **CA:** `mypy holoctl/` limpo no CI.
- **Esforço:** ~1h.

### 0.7 Versão em um lugar só
- **O quê:** remover o fallback hardcoded de `holoctl/__init__.py` (usar só
  `importlib.metadata`); script `validate_changelog.py` no CI/pre-commit que
  confere `pyproject.toml` == último header `## [X.Y.Z]` do CHANGELOG.
- **CA:** um release exige bump em exatamente 2 lugares (pyproject +
  CHANGELOG), validados automaticamente.
- **Esforço:** 30min.

### 0.8 Consolidar fixtures de teste
- **O quê:** mover `_seed_workspace()` (`test_boot.py`) para `conftest.py`
  como fixture `seed_workspace(tmp_path, **overrides)`; fixture
  `cli_runner` session-scoped; migrar `test_adopt.py` e demais para o padrão
  único. Documentar escopo de cada fixture no docstring do conftest.
- **CA:** um único caminho canônico para criar workspace de teste; mudança de
  schema de `.holoctl/` exige tocar 1 lugar nos testes.
- **Esforço:** ~2h. Pode ser feito incrementalmente (novos testes já no
  padrão; migração dos antigos oportunista).

---

## Fase 1 — Segurança / XSS (~½ dia, release patch imediato)

### 1.1 Desabilitar HTML cru no renderizador de markdown  **[crítico]**
- **O quê:** `MarkdownIt("gfm-like", {"html": False, ...})` em
  `server/markdown.py:21` (ou sanitização com `nh3` se HTML for desejado).
- **CA:** teste de regressão: `render_markdown('<img src=x onerror=alert(1)>')`
  não devolve a tag executável (hoje devolve — verificado).
- **Esforço:** 15min + teste.

### 1.2 Toast sem `innerHTML` com dado dinâmico  **[crítico]**
- **O quê:** `toast.js:14` — montar com `createElement` + `textContent`.
- **CA:** mensagem com `<script>` renderiza como texto.
- **Esforço:** 15min.

### 1.3 `esc()` compartilhado + escapar labels do group-by  **[crítico]**
- **O quê:** mover `esc()` de `filetree.js:23-29` para `static/js/dom.js`
  (ou `util.js`); aplicar em `board-controls.js:196-204` e `:253-263`
  (labels de bucket vindos de tags/agents/projects), `card-menu.js`,
  `inline-edit.js` (todo `innerHTML` com dado de ticket).
- **CA:** ticket com tag `<img src=x onerror=...>` agrupado por tag não
  executa script.
- **Esforço:** ~1h.

### 1.4 (Opcional, depois da 6.x) CSP sem `unsafe-inline`
- Depende de remover `onclick` inline (item 6.5). Registrar como follow-up.

---

## Fase 2 — Bugs de frontend quebrados (~½ dia, mesmo patch da Fase 1)

### 2.1 `api.js` compartilhado  **[conserta 3 funcionalidades]**
- **O quê:** criar `static/js/api.js` exportando `projectAlias()`,
  `moveTicket()`, `patchTicket()`; importar em `card-menu.js`,
  `inline-add.js`, `inline-edit.js`, `list-selection.js`; remover as
  definições locais não exportadas.
- **Quebrados hoje:** "+ Add ticket" do kanban (`inline-add.js:48`,
  ReferenceError fora do try → botão trava sem erro), bulk move/archive
  (`list-selection.js:52`), edição inline na página de detalhe
  (`inline-edit.js:62,64,148`).
- **CA:** os três fluxos funcionam manualmente; ESLint `no-undef` zerado;
  (ideal) 3 testes vitest+jsdom cobrindo add/move/patch.
- **Esforço:** ~1h.

### 2.2 Toast: reload opt-in
- **O quê:** `showToast(msg, {reloadOnClick = false})`; só o handler de SSE
  ("Board updated") passa `true`. Toasts de erro não recarregam a página.
- **Esforço:** 20min.

### 2.3 Corrigir seletor morto do stagger
- **O quê:** `stagger.js` usa `.kanban-column > *`; a classe real é
  `.kanban-col`. Corrigir ou remover o seletor.
- **Esforço:** 5min.

---

## Fase 3 — Correção e robustez do backend (~2 dias → 0.21.0)

### 3.1 Frontmatter: parse/serialize em vez de regex  **[integridade de dados]**
- **O quê:** substituir `_patch_ticket_md()` (`board.py:66-79`, regex `re.sub`
  por campo) por: ler → `parse_frontmatter` → mutar dict → re-serializar →
  escrever. Falha silenciosa atual gera drift entre `index.json` e o `.md`
  (que é a fonte de verdade).
- **CA:** testes: patch de campo ausente o adiciona; campo cujo nome aparece
  no corpo não é tocado no corpo; round-trip preserva o body byte a byte.
- **Esforço:** ~3h.

### 3.2 Parser de frontmatter: valores com `:`  **[integridade de dados]**
- **O quê:** `lib/markdown.py:40-46` divide no primeiro `:` e corrompe
  valores como `source_url: "https://..."`. Tratar strings entre aspas
  corretamente — ou migrar para `yaml.safe_load` (avaliar custo: PyYAML já é
  dependência transitiva? Se não, parser próprio com suporte a aspas).
- **CA:** round-trip de `source_url`, títulos com `:` e listas preservados.
- **Esforço:** ~3h (com migração de testes).

### 3.3 Lock na janela load→save do board  **[perde dados hoje]**
- **O quê:** `board.py:265-297` — mutações fazem `_load()` → muta →
  `_save()` do índice inteiro; MCP server + CLI concorrentes se sobrescrevem
  (last-write-wins). Reusar a infra de lock de `lib/jsonl.py` para envolver a
  seção crítica; escrita atômica (temp + rename) se já não houver.
- **CA:** teste de concorrência: N processos fazendo `board move` em tickets
  distintos não perdem nenhuma mutação.
- **Esforço:** ~4h.

### 3.4 Bootstrap commands via ledger  **[1 linha]**
- **O quê:** `compiler/claude.py:204-218` — trocar `Path.write_text` por
  `ledger.write(out_path, bootstrap, source="builtin", target="claude")`.
- **CA:** `/holoctl` e `/hctl-upgrade` aparecem em `.holoctl/.compiled.json`;
  `hctl doctor` detecta hand-edit neles; teste em
  `test_compile_manifest.py`.
- **Esforço:** 30min.

### 3.5 `SYNC_TARGETS` derivado automaticamente
- **O quê:** `templates.py:12-23` — derivar de `get_templates()` (com config
  default) ou, no mínimo, teste que afirma
  `set(SYNC_TARGETS) == set(get_templates(default).keys())`. Esse drift
  manual já causou o bug do `/spec` stale (admitido no comentário do módulo).
- **Esforço:** 30min.

### 3.6 Modo `strict` na resolução de templates
- **O quê:** `compiler/template.py:24-40` — placeholder `{{x.inexistente}}`
  hoje vira texto literal. Adicionar `strict=True` no caminho do compile que
  emite warning (ou erro em testes).
- **Esforço:** 1h.

### 3.7 Endurecer pontos menores
- Lock timeout do Windows configurável (`jsonl.py:53`, env
  `HOLOCTL_LOCK_TIMEOUT`); logging nos rules do curator
  (`curator.py:246-252`, hoje `except: continue` mudo); `_deep_merge` sem
  mutação in-place (`config.py:222-231`).
- **Esforço:** ~2h somados.

---

## Fase 4 — Performance em runtime (~2-3 dias → 0.21.x)

### 4.1 Cache do índice do board invalidado por mtime  **[maior alcance]**
- **O quê:** `board.py:30` re-parseia `index.json` em toda operação; o
  dashboard instancia `Board()`+`ls()` por request; cada tool call do MCP
  refaz `load_config`+`Board` (`server/mcp.py:76-96`). Um cache em memória
  (chave: path, validade: mtime+size) no `Board._load` resolve os três
  consumidores de uma vez. Depende da 3.3 (lock) para não cachear leitura
  rasgada.
- **CA:** benchmark: 100 chamadas `board_get` via MCP ≥5x mais rápidas;
  nenhuma regressão na suite.
- **Esforço:** ~4h.

### 4.2 SSE: I/O fora do event loop + limites
- **O quê:** `app.py:183-213` — `read_text()`/`stat()` via
  `asyncio.to_thread`; semáforo de conexões (ex.: 32); keepalive comment a
  cada ~25s. Handlers de mutação síncronos (`app.py:66-127`) viram `def`
  normais (FastAPI já roda em threadpool) ou usam `to_thread`.
- **Esforço:** ~3h.

### 4.3 Cachear contagem de acceptance no índice
- **O quê:** `board.py:241-252` (`children()`) lê todos os `.md` dos filhos
  por view de detalhe. Gravar `acceptance_total`/`acceptance_done` no
  `index.json` (atualizados em `ack()`/`rebuild_index`).
- **Esforço:** ~2h.

### 4.4 Compile incremental (pular escrita sem mudança)
- **O quê:** `manifest.py:346-352` reescreve todo arquivo owned mesmo
  idêntico. No `_commit`, quando `owned` e `sha == prev[rel]` e o conteúdo em
  disco confere, apenas `_record` sem `write_fn`. Preserva mtime, reduz churn
  e reloads de editor.
- **CA:** `hctl compile` duas vezes seguidas → segunda execução não altera
  mtime de nenhum output; teste no `test_compile_manifest.py`.
- **Esforço:** ~2h.

### 4.5 Endpoint bulk-move no dashboard
- **O quê:** `POST /api/project/{alias}/tickets/bulk-move` (lista de ids +
  status) reaproveitando `board.batch_move`; `list-selection.js` passa a usar
  1 request. Hoje: N requests sequenciais, N rebuilds, N eventos SSE.
- **Esforço:** ~2h.

---

## Fase 5 — Refactors estruturais (incremental → 0.22.0+)

Ordem interna importa: 5.1 → 5.2 → 5.3 (cada um facilita o seguinte).

### 5.1 Templates como arquivos `.md`, não strings Python
- **O quê:** mover as ~677 linhas de Markdown em f-strings de
  `lib/templates.py` para `holoctl/templates/commands/*.md` e
  `templates/context/*.md` (o diretório `templates/` já abriga skills e
  agents). `get_templates()` carrega do disco e aplica
  `resolve_template(config)`. `SYNC_TARGETS` passa a ser o glob do diretório
  (fecha de vez o item 3.5).
- **CA:** output de `hctl init` byte-idêntico ao atual (teste golden);
  `templates.py` < 150 linhas.
- **Esforço:** ~1 dia.

### 5.2 `Ticket` tipado (TypedDict ou dataclass)
- **O quê:** definir o schema do ticket em um lugar (`lib/ticket.py`);
  adotar nos retornos de `Board`, nas views do server e nos handlers MCP.
  `TypedDict` primeiro (zero mudança de runtime), dataclass depois se valer.
- **CA:** mypy passa com o tipo aplicado em `board.py`, `views/`, `mcp.py`;
  adicionar um campo novo de ticket = tocar 1 definição + os pontos que o
  usam (o type checker aponta).
- **Esforço:** ~1 dia.

### 5.3 Dividir `board.py` (~1010 linhas)
- **O quê:** extrair por responsabilidade, sem mudar API pública:
  `board/store.py` (load/save/rebuild + cache da 4.1),
  `board/validate.py`, `board/markdown_sync.py` (criação/patch de `.md`),
  mantendo `Board` como fachada. Acoplamento com curator
  (`board.py:345-360`) vira callback injetado.
- **CA:** suite verde sem alterar nenhum teste de comportamento; nenhum
  módulo do board > 400 linhas.
- **Esforço:** ~2 dias.

### 5.4 MCP: factory de handlers (e avaliar SDK)
- **O quê:** extrair o padrão repetido ×14 ("import Board, load_config,
  instanciar") de `server/mcp.py` para uma factory/contexto compartilhado
  (consome o cache da 4.1). Avaliar migração para o SDK oficial `mcp` num
  spike separado — critério: peso de dependência aceitável para o install
  base e paridade do handshake.
- **Esforço:** factory ~3h; spike SDK ~1 dia.

### 5.5 Drift detection para configs de assistentes estrangeiros
- **O quê:** paridade de contrato com o caminho nativo: a skill
  `holoctl-foreign-bootstrap` passa a instruir o assistente a gravar um
  arquivo de hashes (ex.: `.holoctl/.foreign-compiled.json`, espelhando o
  conceito do `.compiled.json`) e a **avisar antes de sobrescrever** um
  arquivo cujo hash em disco difere do registrado. Sem Python novo — só
  template da skill + format-hints.
- **CA:** cenário manual: editar `.github/copilot-instructions.md` gerado →
  re-bootstrap avisa em vez de sobrescrever silenciosamente.
- **Esforço:** ~½ dia (escrita + testes do template).

### 5.6 Frontend: consolidar utilitários
- **O quê:** `popover.js` (posicionamento com flip, usado 3×), unificar
  `debounce` (2 cópias), migrar `onclick` inline + `window.__*` para
  `data-action` + delegação (`theme.js`, `project-filter.js`,
  `_topbar.html:16`). Habilita a CSP do item 1.4.
- **Esforço:** ~½ dia.

### 5.7 Documentação de invariantes nos módulos grandes
- **O quê:** docstrings de módulo (10-20 linhas) em `board.py` (state machine
  e ordem de mutação index↔md), `manifest.py` (ciclo load→track→prune→save)
  e `mcp.py` (registro de tools); atualizar `ARCHITECTURE.md` com essas
  seções.
- **Esforço:** ~3h.

---

## Fase 6 — UX e acessibilidade do dashboard (~1-2 dias, oportunista)

- **6.1** Container de toast com `aria-live="polite"`/`role="status"` —
  leitores de tela hoje não recebem nenhuma confirmação de mutação. (~30min)
- **6.2** Popovers: focar primeiro item ao abrir, setas navegam
  (`role="menu"` de verdade), foco devolvido ao gatilho ao fechar. (~3h)
- **6.3** Preservar seleção da list view através do swap de SSE (re-marcar
  por `data-id` após `__reapplyBoardControls`). (~1h)
- **6.4** Remover o `window.location.reload()` pós-edição
  (`inline-edit.js:154`) — atualizar o nó editado in-place; SSE cobre o
  resto. (~2h)
- **6.5** `theme.js`: respeitar `prefers-color-scheme` quando não há
  preferência salva. (~20min)
- **6.6** (Se o dashboard um dia for servido fora de localhost) bundle
  esbuild para JS+CSS (resolve os 29 `@import` em waterfall) + CSRF token
  nos endpoints de mutação. Hoje, com bind em 127.0.0.1, é baixa prioridade
  consciente.

---

## Sequência recomendada de releases

1. **0.20.5 (patch, ~2 dias):** Fase 1 inteira + Fase 2 inteira + 3.4
   (ledger) — tudo de segurança e o que está quebrado, sem mudança de
   comportamento.
2. **0.20.6 (infra, sem release de produto):** Fase 0 — a partir daqui todo
   PR fica mais barato.
3. **0.21.0 (~1 semana):** Fase 3 (integridade de dados e concorrência) +
   4.1/4.4 (cache + compile incremental).
4. **0.21.x:** restante da Fase 4 + Fase 6.
5. **0.22.0:** Fase 5 na ordem 5.1 → 5.2 → 5.3, com 5.4-5.7 intercalados.

## Riscos e notas

- **3.2 (parser YAML)** é a mudança de maior risco de regressão — tickets
  existentes no campo. Mitigar com corpus de round-trip: parsear todos os
  tickets do dogfood `.holoctl/` do próprio repo e de fixtures, re-serializar
  e comparar.
- **4.1 (cache)** depende de 3.3 (lock) para não institucionalizar leitura
  rasgada. Não inverter a ordem.
- **5.1 (templates em disco)** muda empacotamento (`package_data`) — testar
  wheel instalada (`uv build` + install em venv limpa), não só editable.
- Nenhum item do plano quebra compatibilidade de workspace; nenhum exige
  migração de `.holoctl/` além das que `hctl upgrade` já faz.

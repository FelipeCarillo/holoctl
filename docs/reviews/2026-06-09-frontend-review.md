# Revisão de frontend (dashboard) — 2026-06-09

Escopo: `holoctl/server/static/js/` (15 módulos ES, ~1.4k linhas),
`static/css/` (29 arquivos, ~4.8k linhas), templates Jinja2
(`server/templates/`, ~1.5k linhas). Leitura integral dos módulos JS e
templates-chave; achados verificados no código, não inferidos.

## 1. Bugs em produção (funcionalidades quebradas hoje)

### 1.1 Três módulos JS com `ReferenceError` — escopo de ES modules violado

Funções definidas em um módulo são usadas em outros **sem export/import**.
ES modules não compartilham escopo, então isso lança `ReferenceError` em
runtime:

| Chamada | Onde é chamada | Onde está definida | Efeito |
|---|---|---|---|
| `projectAlias()` | `inline-add.js:48` | `card-menu.js:24` (não exportada) | Formulário "+ Add ticket" do kanban: submit lança erro **não tratado** (a chamada está fora do `try`), o botão fica desabilitado para sempre e nenhum erro aparece |
| `projectAlias()` | `list-selection.js:52` | idem | Bulk move/archive da list view falha com toast "projectAlias is not defined" |
| `moveTicket` / `patchTicket` | `inline-edit.js:62,64,148` | `list-selection.js:57,71` (não exportadas) | Edição inline de status/priority e dos campos de texto (sprint/tags/agents) na página de detalhe falha com "Update failed: moveTicket is not defined" |

**Fix:** extrair `api.js` compartilhado exportando `projectAlias()`,
`moveTicket()`, `patchTicket()` e importar nos quatro consumidores
(`card-menu`, `inline-add`, `inline-edit`, `list-selection`).

**Causa sistêmica:** não há ESLint (a regra `no-undef` pegaria os três
instantaneamente), não há execução de JS em teste (o `test_dashboard.py`
só faz GET em `/static/js/index.js`), e não há type check de JS.

### 1.2 XSS no group-by do board

`board-controls.js:196-204` (kanban) e `:253-263` (list) interpolam a chave
do bucket em `innerHTML` escapando **apenas aspas**, não `<`:

```js
kanban.innerHTML = sortedKeys.map(k => `... <span class="col-label">${k}</span> ...`)
```

As chaves vêm de `data-tags` / `data-agent` / `data-projects` dos cards —
dados de ticket (o browser devolve o atributo já decodificado via
`getAttribute`). Uma tag de ticket contendo HTML executa script quando o
usuário agrupa por tag. Mesmo padrão do `toast.js:14` (`message` em
`innerHTML`). Já o `filetree.js:23-29` tem um `esc()` correto — a
disciplina existe, mas só num módulo.

**Fix:** mover `esc()` para um módulo compartilhado e usá-lo em todo
`innerHTML` com dado dinâmico (`board-controls`, `toast`, `card-menu`,
`inline-edit`); ou montar esses nós com `createElement`/`textContent`.

### 1.3 Toast clicável recarrega a página — inclusive toasts de erro

`toast.js:15-18`: qualquer clique num toast (fora do ×) faz
`window.location.reload()`. Faz sentido para "Board updated", mas o mesmo
componente é usado para erros ("Move failed: …") — o usuário clica para
dispensar e a página recarrega, perdendo o contexto. **Fix:** tornar o
reload opt-in (`showToast(msg, {reloadOnClick: true})`).

## 2. Problemas sistêmicos (a raiz dos bugs acima)

- **Zero tooling de frontend.** Sem ESLint, sem formatter, sem nenhum teste
  que execute JS, sem type check (nem JSDoc + `tsc --checkJs`). O custo de
  entrada é mínimo: um `eslint.config.js` com `no-undef`/`no-unused-vars` e
  um job de CI já teria bloqueado o item 1.1. Um passo além: 3-4 testes
  vitest+jsdom para os fluxos críticos (add ticket, move, filtro).
- **Escaping ad-hoc.** Quatro estratégias diferentes coexistem:
  `esc()` completo (filetree), replace só de `"` (board-controls grupos),
  replace de `"` + `<` (chips), e nenhum (toast, card-menu). Precisa de um
  helper único.
- **Duplicação.** `debounce()` duplicado em `board-controls.js:337` e
  `meta-search.js:10`; posicionamento de popover (medir rect, flip se
  estoura viewport) triplicado em `card-menu.js:71-77`,
  `inline-edit.js:47-52` e `:123-128`; fetch + tratamento de erro repetido
  em 4 módulos. Um `popover.js` + `api.js` elimina ~80 linhas e os bugs de
  inconsistência futuros.
- **Globais `window.__*` + `onclick` inline.** `theme.js`,
  `project-filter.js` e `board-controls.js` expõem handlers globais
  consumidos por `onclick="__toggleTheme()"` nos templates
  (`_topbar.html:16`). Funciona, mas impede uma CSP sem
  `unsafe-inline` — que seria a defesa em profundidade natural contra os
  XSS do item 1.2 e do markdown (já reportado na revisão geral). Migrar
  para `data-action` + delegação (padrão que o resto do código já usa).

## 3. Acessibilidade

- **Toasts invisíveis para leitores de tela** — o container não tem
  `aria-live="polite"` nem `role="status"`. Como toast é o único feedback
  de mutação (move, patch, erro), usuário de leitor de tela não recebe
  confirmação nenhuma.
- **`role="menu"` sem teclado** — os popovers (`card-menu`, `inline-edit`)
  anunciam menu mas não implementam navegação por setas nem focam o
  primeiro item ao abrir; Tab escapa do popover. Ao fechar, o foco não
  volta ao botão gatilho.
- Pontos positivos: `aria-expanded` consistente nos gatilhos, `Escape`
  fecha tudo, `initRoleButtonKeys` cobre os `div role="button"`, e há um
  `accessibility.css` dedicado (focus-visible etc.).

## 4. UX / performance

- **SSE swap descarta estado de seleção** — `sse.js:41` substitui o DOM
  inteiro do board; filtros/sort/group são reaplicados via
  `__reapplyBoardControls`, mas a seleção da list view (`data-selected`)
  se perde silenciosamente no meio de uma operação em massa.
- **Bulk move = N requests sequenciais** (`list-selection.js:90-94`). O
  backend já tem `board batch_move` no CLI/MCP; falta um endpoint
  `POST /tickets/bulk-move` — com 30 tickets selecionados são 30
  round-trips e 30 rebuilds de índice (cada um disparando SSE).
- **Reload forçado pós-edição** — `inline-edit.js:154` faz
  `window.location.reload()` 250ms após salvar, em vez de atualizar o nó.
  Combinado com o toast clicável, há três caminhos diferentes de "refresh"
  no app (SSE swap, reload manual, reload automático).
- **CSS: 29 `@import` sequenciais** (`index.css`) — waterfall de descoberta
  no browser, sem minificação nem cache-busting. Para um dashboard local é
  aceitável; se um dia for servido remoto, concatenar no build (esbuild
  resolve JS + CSS em ~1 config).
- **Seletor provavelmente morto** — `stagger.js` mira `.kanban-column > *`,
  mas a classe real é `.kanban-col` (ver `kanban.css`); a animação de
  stagger do kanban não roda.
- `theme.js:5` ignora `prefers-color-scheme` — default fixo `light`.

## 5. O que está bem feito

- **Event delegation em `document`** em todos os módulos interativos — é
  por isso que o swap de DOM do SSE não quebra os handlers. Decisão certa
  e aplicada com consistência.
- **Templates Jinja2 disciplinados** — macros reutilizadas
  (`card_data_attrs` compartilhado entre kanban/list/tree para o JS não
  ramificar), autoescape ligado, partials pequenos e coesos.
- **Boot de tema sem FOUC** (`_boot.html` inline antes do CSS) e estado de
  controles por workspace em `localStorage` com versionamento de schema
  (`holoctl-bc-v2`) e migração documentada.
- **`filetree.js`** é o módulo-modelo: escaping correto, lazy-load com
  estados de loading/empty/error, configuração via data-attributes.

## 6. Plano sugerido (ordem)

1. **`api.js` compartilhado** (projectAlias/moveTicket/patchTicket) —
   conserta as 3 funcionalidades quebradas. ~30min + teste manual.
2. **ESLint no CI** (`no-undef`, `no-unused-vars`) — garante que a classe
   de bug do item 1 nunca volta. ~30min.
3. **`esc()` compartilhado + textContent no toast** — fecha os XSS do
   frontend (junto com `html: False` no markdown-it, da revisão geral).
4. **`aria-live` no toast container** + foco devolvido ao fechar popover.
5. **Endpoint bulk-move** + remover reload forçado do inline-edit.
6. Oportunista: unificar debounce/popover, `data-action` no lugar de
   `onclick`, corrigir seletor do stagger, `prefers-color-scheme`.

Itens 1-4 cabem em um dia e atacam tudo que está efetivamente quebrado.

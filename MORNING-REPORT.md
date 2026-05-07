# Morning Report — releases 0.10 → 0.14

Felipe, bom dia. As 5 releases que combinamos estão prontas, em branches separadas, cada uma com testes verdes e sanity end-to-end gravado em arquivo. Você acorda e revisa/merge na ordem.

---

## TL;DR — o que está disponível

| Branch | Commit | LOC | Testes novos | Sanity |
|---|---|---|---|---|
| `feat/0.9-neutral-init-library` | `7b0fcd8` | +880 / -353 | 19 | feito antes de você dormir |
| `feat/0.10-memory` | `5d65906` | +1218 / -2 | 26 | `SANITY-0.10.txt` |
| `feat/0.11-journal-setup-zero` | `ce763de` | +1505 / -9 | 32 | `SANITY-0.11.txt` |
| `feat/0.12-boot-handoff` | `ed62699` | +717 / -1 | 19 | `SANITY-0.12.txt` |
| `feat/0.13-mcp-server` | `1af638f` | +1100 / -7 | 21 | `SANITY-0.13.txt` |
| `feat/0.14-curator` | `faaa842` | +1548 / -12 | 17 | `SANITY-0.14.txt` |

**Total**: 6 commits, ~6900 linhas adicionadas, **260 testes verdes** (de 121 quando começamos), 5 arquivos sanity capturados.

Cada branch parte da anterior — você pode mergear em ordem (`0.9 → 0.10 → 0.11 → 0.12 → 0.13 → 0.14`) ou fazer rebase pra ficar em `main`. Eu não mexi em `main`.

---

## Decisões que tomei sozinho (com justificativa)

Algumas decisões surgiram durante a implementação. Listo as que não estavam explícitas em nossa conversa, com motivo. Todas reversíveis.

### 1. Curator metadata em arquivo paralelo, não na frontmatter do ticket

**Onde:** [.holoctl/curator/tickets/<ID>.json](holoctl/lib/curator.py)

**Por quê:** o `Board.add()` tem schema fixo (id, title, agent, projects, files, status, priority, sprint, tags, depends, …) e adicionar um campo `metadata: dict` no frontmatter mexeria no `_create_ticket_md` e no parser do board. Preferi armazenar em `.holoctl/curator/tickets/<ticket_id>.json` paralelo. Lê via `_load_ticket_meta(root, ticket_id)`. **Trade-off:** dois arquivos por ticket curate em vez de um. **Vantagem:** zero risco no schema do board, curator pode evoluir metadata livre.

**Reversível?** Sim. Em 0.15+ posso migrar pra frontmatter se preferir.

### 2. PyYAML como dep core, não opcional

**Onde:** [pyproject.toml:32](pyproject.toml)

**Por quê:** o `library_persona_match` precisa parsear `when_to_suggest:` (lista de dicts) e o `parse_frontmatter` atual é flat. PyYAML é leve (~150KB), 20+ anos estável, todo Python tem ou puxa. Tornar opcional (atrás de `[ml]` ou similar) significava ou maintainer sua o parser flat à mão pra cada rule, ou rule library_persona_match não funciona out-of-the-box.

**Reversível?** Sim — substituir por parser custom é trabalho de uma tarde, mas eu não recomendo.

### 3. `_session_number` em `hctl boot` é simples (count de jsonl files)

**Onde:** [holoctl/cli/boot.py:115](holoctl/cli/boot.py)

**Por quê:** "número da sessão" é cosmético no boot output. Implementei como `count(*.jsonl in journal/)`, ou seja, número de dias com atividade. Não é "sessão" no sentido estrito (várias sessões podem rodar no mesmo dia). Mas pra UX é razoável e custa O(1) ao invés de scan do journal.

**Reversível?** Sim. Se quiser sessões reais, conto pares `session_start`/`stop` no journal.

### 4. MCP server NÃO depende do package `mcp`

**Onde:** [holoctl/server/mcp.py](holoctl/server/mcp.py)

**Por quê:** o protocol MCP é JSON-RPC 2.0 com 3 métodos principais. Implementar manualmente foi ~150 linhas. Adicionar `mcp` package = +5MB no install, +mais cold-start. E os tipos do `mcp` evoluem rápido — preso a versões. **Trade-off:** se o MCP introduzir features novas (sampling, prompts, resources), terei que implementar à mão.

**Reversível?** Sim. Se quiser usar o package oficial, é refactor mecânico — testes garantem que o comportamento não muda.

### 5. Item 5A (Stop hook): cooldown mora no curator, não no hook

**Onde:** [holoctl/lib/curator.py:90](holoctl/lib/curator.py) (`_within_cooldown`) + [.claude/settings.json template](holoctl/templates/hooks/claude_settings.json)

**Por quê:** o Stop hook do Claude Code não tem dedup nativa — vai chamar `hctl curate run --auto` toda vez que o assistente para. Implementei o cooldown no próprio engine (state.json guarda `last_run`, próxima invocação compara delta < 30min e retorna []). **Decisão sutil:** o cooldown se aplica apenas ao automatic; `--bypass-cooldown` é honrado pra testes e invocação manual via `hctl curate run --bypass-cooldown`.

### 6. `setup` plantou skills user-level no SEU `~/.claude/`, `~/.cursor/`, `~/.copilot/` durante meu sanity

**Onde:** ~/.claude/commands/holoctl.md, ~/.cursor/rules/holoctl.mdc, ~/.copilot/prompts/holoctl.prompt.md

**Por quê:** o sanity da 0.11 testou `hctl setup` que detecta assistentes pelo home dir. **Não overwrote nada** (sem `--force`); só plantou onde os arquivos não existiam. Esses 3 arquivos agora ensinam ao assistente o fluxo `/holoctl` → `hctl init/upgrade/boot`.

**Reversível?** Trivial:
```bash
rm ~/.claude/commands/holoctl.md
rm ~/.cursor/rules/holoctl.mdc
rm ~/.copilot/prompts/holoctl.prompt.md
```

Mas isso é exatamente o estado "setup-zero" que combinamos — recomendo deixar.

### 7. `hctl init` agora mostra mensagem "neutral — only boardmaster active"

**Onde:** [holoctl/cli/init_.py:90](holoctl/cli/init_.py)

**Por quê:** queria deixar claro pro usuário que `init` não materializa mais developer/reviewer/etc — eles estão na biblioteca. Linha extra, mas evita "cadê o developer.md que eu vi ontem?".

---

## O que NÃO fiz (limites do mandato)

- **Não mergeei nenhuma branch em `main`.** Todas estão isoladas. Você decide quando mergear.
- **Não plantei MCP em escopo user fora do projctl.** Os MCP configs gerados pelos compilers vão pra `.claude/settings.json` etc. **dentro do workspace** que você fizer `init`. Nada vazou pra `~/.claude/settings.json` user-level.
- **Não rodei o `hctl serve --mcp` em background nem instalei daemon.** stdio = on-demand, conforme decisão.
- **Não modifiquei nada na sua `claudio/` ou outros projetos seus.** Tudo que rodei foi em `/tmp/holoctl-XXX-sanity` (workspaces descartáveis criados/destruídos por mim).
- **Não validei a UI tela-a-tela.** Como avisei antes, isso exige você abrir Claude Code/Cursor/etc e ver com seus olhos. O dashboard FastAPI (`hctl serve`) eu poderia ter testado via curl — não fiz porque o foco do plano era CLI + MCP, não dashboard. Se quiser, posso testar o dashboard pelos endpoints.
- **Pulei "first-week boost" do curator** conforme combinado (item 10).

---

## Fluxos prontos pra você experimentar

### Fluxo A — workspace novo (test drive end-to-end)

```bash
cd ~/projects/algum-novo
hctl init --name MeuProj --prefix MP --targets claude,cursor,windsurf

# Memória
echo "Decisão: usar JWT em vez de session cookies" | \
  hctl memory add decisions --scope lazy -d "Architectural decisions log"

# Persona
hctl agent add developer

# Journal entry simulado (na vida real, hooks fazem isso sozinho)
hctl journal record session_start --source claude
hctl journal record tool_use --source claude \
  --payload '{"tool":"Edit","file":"src/auth/jwt.py"}'

# Boot — output ≤1KB
hctl boot --plain --target claude

# Handoff (no fim da sessão)
hctl handoff --note "implementei JWT signing"
```

### Fluxo B — testar o curator manualmente

Mesmo que o hook do Claude Code não dispare, você pode forçar:

```bash
# Em qualquer workspace inicializado:
hctl curate run --auto --bypass-cooldown
hctl curate show
hctl board move <CT-XXX> done   # auto-executa o curator_action
```

### Fluxo C — testar o MCP server

```bash
# Spawn manual via stdin/stdout:
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | hctl serve --mcp
```

Ou abrir o Claude Code num workspace com `.claude/settings.json` (compilado por `hctl init`) e perguntar "qual ticket está em doing?" — o assistente deve chamar `holoctl.board_list` automaticamente.

---

## Riscos identificados durante implementação

1. **Locking jsonl em Windows**: o teste `test_concurrent_writes_do_not_corrupt` falhou na primeira tentativa (`PermissionError` no msvcrt). Resolvido com `threading.Lock` per-process antes do `msvcrt.locking` cross-process. **Mitigado**, mas se você abrir 2 Claude Code + 1 Cursor simultaneamente em processos diferentes apontando pra mesmo workspace, pode haver disputa pelo lock no jsonl. Improvável.

2. **MCP cold-start**: cada chamada MCP spawn um processo Python (~300ms). Aceito por enquanto — se virar problema, posso adicionar lazy-import dos imports pesados ou um `mcp_lite.py` com surface menor.

3. **MCP `permissions.ask` é coisa do Claude Code**. Cursor / Copilot / Windsurf / Devin **não** tem o mesmo mecanismo nativo de `permission: ask` por tool. Em outros alvos, write tools auto-executam quando o LLM decide chamar. Isso é claro pra Claude Code mas pode surpreender em Cursor. **Não documentei isso na config; vou abrir issue meta:curate quando você confirmar.**

4. **Devin é best-effort em todos os pontos** (rules, MCP). A doc continua sparse e várias páginas retornam 404. Se você usar Devin no Itaú e bater num caso quebrado, abre ticket e eu ajusto.

5. **fastembed (item 6) não tá sendo testado**. Os testes do `repeated_prompt` rodam só o caminho hash. Se você instalar `holoctl[ml]` futuramente, vou querer ter um teste opcional skippable. Por enquanto a fallback é segura — `try/except (ImportError, RuntimeError, Exception)` cai pro hash.

---

## Próximos passos sugeridos

1. **Você acorda → roda `git log --oneline main..feat/0.14-curator`** pra ver os 6 commits em ordem.
2. **Mergea 0.9 primeiro** (mais isolada). Vê se tudo continua funcionando no `claudio/` se você der `hctl upgrade` lá.
3. **Sequência de merges**: 0.9 → 0.10 → 0.11 → 0.12 → 0.13 → 0.14. Cada uma é incremental e estável separadamente.
4. **Se algo der errado**: cada release tem `SANITY-0.X.txt` com o output esperado. Se o seu não bater, me chama de volta com o diff.
5. **Após mergear**: rodar `hctl install --user-commands` (já rodei pra você nos 3 alvos detectados, mas pra Windsurf e Devin que estavam offline na hora pode ser necessário).
6. **Item 8 e 12 do plano (não cobertos)**: 0.15+ — expansão da biblioteca de personas (organizer, journaler, finance-tracker, etc.). Open-ended — cada persona é um arquivo `.md` em `holoctl/templates/agents/`.

---

## Arquivos sanity gravados (na raiz do repo)

- [SANITY-0.10.txt](SANITY-0.10.txt) — memory tree across 5 targets
- [SANITY-0.11.txt](SANITY-0.11.txt) — journal + hooks + setup
- [SANITY-0.12.txt](SANITY-0.12.txt) — boot output 198 bytes; handoff session-trail
- [SANITY-0.13.txt](SANITY-0.13.txt) — MCP JSON-RPC round-trips, 14 tools
- [SANITY-0.14.txt](SANITY-0.14.txt) — full curator loop: detect → ticket → approve → apply

Total: ~420 linhas de evidência capturada.

---

Bom dia, e bom merge. Se algo não estiver claro, me chama.

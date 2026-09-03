# Changelog

## Unreleased

### Changed

- **O portão C consegue perguntar: `remove_by_search` larga o `destructiveHint`.**
  O produtor do portão C entregue no #89 estava **entregue, servido, e não dispararia**. A causa
  não estava nele, estava numa palavra da anotação: o **portão B pre-empte o portão C por
  construção** — `cogno_anima/stages/ego.py` retém e faz `continue` *antes* de
  `dispatcher.execute`, portanto uma tool que ele segura **nunca corre**, e a pergunta
  fundamentada nunca chega a existir. Medido: com a anotação de ontem o traço recebia
  `"[PENDING CONFIRMATION] … is destructive and was NOT executed"` — sem data, sem valor, sem as
  irmãs. Nenhuma dessas três coisas o *nome* de uma ferramenta pode saber.

  **Isto não tira uma protecção, tira uma protecção REDUNDANTE**, e a redundância foi medida e não
  argumentada. O caminho de escrita é **inalcançável** sem `confirm_tx_id`: o `store.remove` vive
  no único ramo que exige o id, e um id que não esteja entre as linhas do próprio chamador volta a
  propor em vez de cair para "a mais recente". Quebrar essa forma (regressão ao apagar de um passo,
  pré-#89) põe **10 testes a vermelho** — a promessa é estrutural e é *medida*, não recordada.
  E o mesmo turno não se pode auto-confirmar: o id só existe depois da primeira resposta, portanto
  não cabe no mesmo passo, e mal a proposta chega o portão C levanta-se e o **laço pára**.

  **As duas metades tinham de aterrar juntas.** Tirar a anotação sem emitir o `_meta` deixa a
  proposta chegar ao EGO como `ok=True, side_effect=True` — o dispatcher calcula
  `side_effect = mutating and not asks` — e o turno passa a **declarar uma escrita que não houve**
  sobre uma chamada cujo próprio texto diz *"NOT REMOVED — nothing was deleted"*. Medido, e é a
  razão de o `_meta` não ser um extra.

  **O que muda no fio:** a proposta volta como um `TextContent` cujo `_meta` leva
  `cogno-mcp/needs_confirmation: true` e `cogno-mcp/confirm_arguments: {"confirm_tx_id": …}` — a
  ponte que o cogno-mcp#12 abriu ontem. O texto continua a ser a **prosa** fundamentada; o
  `outputSchema` desaparece para esta tool (o FastMCP valida o retorno contra ele, e um `-> str`
  faz devolver um `TextContent` rebentar — medido no mcp 1.16.0), o que era `{result: string}` e
  não dizia nada.

  **A varredura `test_tool_annotations.py` passou de binária a ternária:** uma tool mutante é
  *gated* (B), *undoable*, ou **ASKS BY ITSELF** (C) — e, como as vizinhas, a nova lista é
  **executada** e não acreditada. O raio de acção fica pinado num teste próprio: continuam com
  `destructiveHint` exactamente `cancel_appointment`, `confirm_swap` e `reschedule_appointment`,
  que **comitam à primeira chamada** e portanto não têm sobre o que fundamentar pergunta nenhuma.

  Fecha a lacuna que `test_bookkeeper_via_mcp.py` afirmava no verde (`needs_confirmation is False`),
  agora invertida.

- **`remove_by_search` PROPÕE antes de comitar — e a proposta cita a linha que ela leu.**
  O EGO tem três portões de confirmação e o terceiro (`cogno_anima/stages/ego.py`, "Fonte C" —
  *a skill correu, leu, e pergunta sobre ESTA chamada*) nunca tinha tido um produtor. Esta é a
  primeira, e a escolha não é arbitrária: `remove_by_search` **já lia antes de escrever**, e uma
  ferramenta que só escreve não tem sobre o que basear a pergunta — nasceria a adivinhar, que é
  exactamente o que o portão B faz.

  **O que o portão B não pode saber:** ele decide por NOME, antes de correr. Diz *"vai apagar
  alguma coisa"* e nunca *"vai apagar ESTA"*. Qual linha uma busca de substring dobrada em acento
  (`matches_query`) apanhou, de que valor e de que data — só depois de ler.

  **Antes:** `remove_by_search(query)` apagava a mais recente que casasse, à primeira, e devolvia
  `Removed: …`. **Agora:** a primeira chamada não apaga nada — devolve a linha que apagaria (data,
  descrição, valor) e as irmãs que a mesma busca apanhou; a segunda, com `confirm_tx_id=<id>`,
  apaga essa linha. Sem correspondência nenhuma → a frase de hoje, inalterada, e pergunta nenhuma.

  Dois defeitos que isto fecha, e nenhum deles é de fraseado: (1) `"internet"` casa a conta de
  Janeiro, a de Fevereiro e a de Março — a versão de um passo apagava a mais recente **em
  silêncio** e ninguém ficava a saber que existiam outras duas; (2) a confirmação é um **id**, não
  um sim/não, portanto um lançamento novo que entre entre a proposta e o "pode apagar" já não
  desloca o alvo. Um `confirm_tx_id` que já não esteja entre as linhas do chamador não recai em
  "a mais recente": propõe outra vez sobre o que HÁ.

  **O que ficou por fechar, e onde:** o campo `ToolResult.needs_confirmation` não é transportado
  pelo `cogno-mcp` (`grep -rn needs_confirmation` nesse repositório: zero ocorrências), portanto
  sobre a ponte MCP a proposta chega ao EGO como texto de ferramenta e o portão C do núcleo não
  chega a levantar-se. É o texto que protege o livro hoje; o campo é a metade que uma ponte teria
  de carregar.

- **Os testes MCP-sobre-stdio do bookkeeper e do scheduler passaram a medir ESTA árvore.** Ambos
  lançavam o servidor por caminho, e o subprocesso importava `cogno_praxis` do *editable install*
  — noutra worktree, um verde que pertence ao checkout de outra pessoa. O
  `test_coordinator_via_mcp.py` já tinha o `PYTHONPATH` e a razão escrita; os outros dois não.
  Encontrado por este PR ficar vermelho no sítio errado.

- **A base descartável passou a ser o DESTINO por omissão das suítes que fazem `DROP TABLE`.**
  Dono, 2026-08-26: *"Já temos um test só para os testes de integração, isso deveria ser
  padrão."* A guarda de 2026-08-04 transformou o engano numa recusa, mas continuava a deixar a
  pessoa **escrever** um DSN — e a forma que causou o estrago é justamente a que a shell já tem
  à mão (`COGNO_PG_DSN` exportado, um copiar-colar de distância de `COGNO_TEST_PG_DSN`).

  **Antes:** `DSN = os.environ.get("COGNO_TEST_PG_DSN")` nos dois módulos de Postgres; variável
  por pôr → `pytest.skip`. **Agora:** `resolve_test_dsn()` — explícito ganha; sem ele,
  `cogno_praxis_test` no servidor LOCAL que `COGNO_PG_DSN` já nomeia (ou nos defaults do libpq,
  que são o que o serviço do CI serve); nada à escuta → `""` → salta como saltava.

  O que torna isto seguro não é uma verificação, é uma **construção**: o nome da base nunca é
  trazido de lado nenhum, é **escrito** (`_for_test_database`). Dar a esta função o DSN exacto
  que causou a perda devolve o descartável, e `tests/unit/test_integration_db_guard.py` pina
  isso nos dois sentidos, incluindo que TODO default nomeia uma base de teste seja qual for o
  ambiente. Um `COGNO_PG_DSN` REMOTO não é adoptado: `cogno_praxis_test` na instância gerida de
  alguém não é nossa para criar, quanto mais para largar.

- **A guarda passou a inspeccionar o DSN RESOLVIDO, não a variável crua.** Tem de olhar para a
  mesma string que os fixtures vão abrir, ou as duas divergem e só uma é verificada. É também a
  segunda rede sob o parágrafo acima: um erro em `_for_test_database` não destrói nada, porque o
  `pytest_collection_modifyitems` volta a recusar o nome.

- **O teste de convenção deixou de poder passar em vazio.** Ele varre os módulos que leem o DSN;
  como esses deixaram de nomear a variável directamente, o termo de busca é o que pode
  envelhecer em silêncio — agora afirma também que a varredura ainda os encontra.

### Fixed

- **O docstring de `tests/integration/test_bookkeeper_postgres.py` ensinava
  `postgresql://postgres:test@localhost:55432/cogno`** — "test" na SENHA, a base VIVA da caixa
  demo no caminho. É exactamente a forma para a qual existe
  `test_refuses_when_only_the_password_says_test`, e estava a ser ensinada no ficheiro ao lado.
  O módulo faz `DROP TABLE bookkeeper_transactions` e `bookkeeper_clients`.
- **`examples/run_with_db.py`** dizia `postgresql://localhost/cogno` → `…/myapp`. Um exemplo não
  deve deixar o nome da base viva num sítio de onde se copia.
- **`README.md`** passou a dizer para onde vão os testes de Postgres, e que o nome da base é
  escolhido por eles.

- **O prompt do `scheduler` ensinava a sintaxe `<TOOL_CALL>` e dava dois exemplos completos.**
  A mecânica de chamada é do CORE (`cogno_anima.stages.ego`), que a renderiza **só quando o
  turno tem catálogo** — e um prompt que a ensina sozinho derrota essa guarda: uma persona sem
  tools lia na mesma dois exemplos de como emitir a tag, e uma tag emitida sem ter o que chamar
  não é uma chamada falhada, é TEXTO, que chega ao contato.

  A regra já existia — num comentário do `ego.py`, sem verificação nenhuma, violada há tempo
  indeterminado. Agora `tests/unit/test_prompts_own_no_tool_mechanics.py` varre
  `cogno_praxis/*/prompts/*.txt` e falha com a explicação; tem controlo para o caso de o glob
  deixar de casar, porque uma guarda sobre lista vazia passa para sempre.

  **A pedagogia ficou.** Os exemplos ensinavam ORDEM (`resolve_date` antes de `book_appointment`;
  `list_schedulable_hosts` antes de marcar), e isso é valioso — foi reescrito em prosa, sem a
  tag. Medido antes/depois no `hostbench secretary_bench --group cheap` (4 cenários com tools):
  **9/9 dos dois lados, com as MESMAS sequências de chamada** — tirar os exemplos não baixou a
  taxa. As duas corridas leram prompts diferentes, verificado no ficheiro resolvido.

## 0.1.1 — 2026-08-02

Dependency fix. **0.1.0 is broken for a fresh install** — upgrade.

- Cap the `mcp` SDK below 2.0. The SDK published 2.0.0 and moved
  `mcp.server.fastmcp`, which every vertical imports at module load, so an
  unbounded `mcp>=1.0` made any new resolve pick a version that fails to import
  before a single request runs. Existing environments were unaffected only
  because their venv already held a 1.x.

## 0.1.0 — 2026-07-25

First public release on PyPI.

The Cogno business verticals as standalone MCP servers (the product layer). Each vertical is an independent FastMCP server the host orchestrates via cogno-mcp; verticals own their domain logic + data behind their own store ports. Verticals: scheduler (agenda → SECRETARY persona) and bookkeeper (finance → BOOKKEEPER persona).

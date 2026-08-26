# Changelog

## Unreleased

### Changed

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

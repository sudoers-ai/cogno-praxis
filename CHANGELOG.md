# Changelog

## Unreleased

### Fixed

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

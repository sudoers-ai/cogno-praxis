# Port plan — BOOKKEEPER persona → functional (the `bookkeeper` vertical)

Approved plan. Ports the parent SaaS `cogno/mcp/modules/bookkeeper/` (ANALYST persona) into a
cogno-praxis vertical, mirroring `scheduler`. Decisions locked: **no session pool** (DB-backed,
per-turn is enough), **prompt-driven confirmation** for `add_*` (not core Gate-B), **shared
`COGNO_PG_DSN`** (own `bookkeeper` schema), **`get_usage` delegates to host metering**.
**Documentation/.md is a first-class deliverable in every phase.**

## Phase 1 — the vertical (cogno-praxis) · PR-1
- `cogno_praxis/bookkeeper/`: `engine.py`, `store.py`, `stores/postgres.py`, `service.py`,
  `server.py`, `prompts/{system,scope,limits,voice}.txt`, `__init__.py`.
- Tenant-agnostic + role-visibility (mirror scheduler). 8 tools with MCP annotations.
- **Docs:** `docs/BOOKKEEPER.md` (this vertical), README section, `docs/HOST_INTEGRATION.md` note.
- **Tests:** `tests/unit/test_bookkeeper_engine.py`, `tests/unit/test_bookkeeper_service.py`,
  `tests/integration/test_postgres_store.py` (+ bookkeeper), `tests/integration/test_bookkeeper_via_mcp.py`.

## Phase 2 — host wiring (cogno-host) · PR-2
- `modules.py`: `_bookkeeper_source` (spawn `python -m cogno_praxis.bookkeeper.server`) + registry entry.
- `assembler.py`: `_bookkeeper_env(tenant)` (DSN/SCOPE/TODAY). `persona.py`: `_bookkeeper_prompts_dir()`
  → praxis; flip `BOOKKEEPER.allowed_modules` `()` → `("bookkeeper",)`; remove `cogno_host/prompts/bookkeeper/`.
- `rbac.py`: `bookkeeper_rbac()` (EMPLOYEE own / oversight all). `migrate.py`: ensure schema.
- **Docs:** update `docs/PERSONAS.md` (flip BOOKKEEPER to functional; remove the TODO).
- **Tests:** `test_persona.py` (allowed_modules), `test_assembler.py` (env + rbac + routing),
  `tests/integration/test_bookkeeper_e2e.py` (live Ollama, auto-skip).

## Phase 3 — benches · PR-3
- cognobench: `bookkeeper_cases.py` (port parent `persona_cases.py` — 8 tools + combined + scope).
- hostbench: `bookkeeper_bench.py` (mirror `secretary_bench.py`) + deterministic dim `e2e_bookkeeper`.
- **Docs:** `docs/BOOKKEEPER_BENCH_RESULTS.md`.

## Sequencing
PR-1 (praxis) → PR-2 (host, bumps praxis dep) → PR-3 (benches). Each PR ships its own docs + tests.

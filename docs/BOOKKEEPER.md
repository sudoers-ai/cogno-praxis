# The `bookkeeper` vertical

The **bookkeeper** is a Cogno business vertical — a standalone FastMCP server the host
orchestrates via `cogno-mcp`, exactly like the `scheduler`. It backs the **BOOKKEEPER**
persona (ported from the parent SaaS `ANALYST`): a financial bookkeeper / business analyst
that records income (entradas) and expenses (saídas), tracks clients, and produces summaries
for small service businesses.

It mirrors the scheduler's layering and stays **tenant-agnostic**: multi-tenancy is the host
pointing at the right store/scope, never a column the vertical filters. Identity fields are
opaque strings the host resolves/authorizes.

## Layers

| File | Role |
|---|---|
| `engine.py` | Pure rules — amount/date validation, defaults, summary aggregation. No I/O. |
| `store.py` | Domain types (`Client`, `Transaction`) + the `BookkeeperStore` Protocol + `InMemoryBookkeeperStore`. |
| `stores/postgres.py` | `PgBookkeeperStore` — the Postgres adapter (schema-scoped, per-tenant). |
| `service.py` | `BookkeeperService` — orchestrates engine+store, applies **role visibility** (EMPLOYEE sees own; oversight sees all). Raises `BookkeeperError`; the server maps to recoverable tool errors. |
| `server.py` | `build_server(service)` → FastMCP. `python -m cogno_praxis.bookkeeper.server` runs the stdio server. |
| `prompts/{system,scope,limits,voice}.txt` | The BOOKKEEPER persona prompts (the host loads them). |

## Tools (LLM-facing)

| Tool | Annotation | Notes |
|---|---|---|
| `add_income` | mutating | Record revenue (optional client). Prompt asks for confirmation first. |
| `add_outcome` | mutating | Record an expense. Prompt asks for confirmation first. |
| `get_summary` | read-only | Totals + breakdown by period (day/week/month or date range). |
| `list_clients` | read-only | Known clients with revenue totals. |
| `search` | read-only | Keyword/date search across transactions. |
| `remove_by_search` | mutating, **asks by itself** | **Two calls.** The first READS and answers with the exact entry it would remove (date, description, amount, id) plus the siblings the same query matched — nothing is deleted, and the reply carries the gate-C flag so the EGO holds the turn there. The second, carrying `confirm_tx_id`, deletes that one row. It carries **no `destructiveHint`**: Gate-B would hold it by name *before* it ran, and the grounded question would never be asked. |
| `get_usage` | read-only | AI token/usage — **delegated to the host's metering** (see decision #4). |
| `help` | read-only | Scope guardrail: what the bookkeeper does / redirect off-topic. |

Mutation/destructiveness travels as MCP `ToolAnnotations` → the host EGO's read-only mask +
confirmation gate. Recording (`add_*`) is *mutating but not destructive*: confirmation is
**prompt-driven** (like `book_appointment`), not the core Gate-B. `remove_by_search` uses neither:
it raises **Gate-C** from inside the call, which is why it must NOT declare `destructiveHint` —
the two gates cannot both hold, because B stops the call before C could speak.

### Why `remove_by_search` asks a second question

An annotation is read per tool **name**, before anything runs. It can say *a deletion is coming*
and it can never say *what would be deleted* — the tool name is identical for every removal, while
which row an accent- and case-folded substring query selects (`matches_query`, the ecosystem's
fold: NFKD, marks removed, `casefold`, so «Strasse» finds «Straße»), of what value, of what date,
and whether it selected three siblings alongside it, is knowable only **after** the read. So
`remove_by_search` reads first and proposes the row, quoting it; a second call naming that row's
`confirm_tx_id` commits it.

That is also why the tool drops `destructiveHint`. Gate B holds by name and **before** the call, so
a tool it holds never runs and the grounded question is never asked — measured in
`tests/integration/test_o_portao_C_dispara_sobre_a_cadeia.py` against a byte-identical twin that
differs only in the annotation. What replaces the hold is not a promise but a shape: the write path
is unreachable without `confirm_tx_id`, an id the caller can only have learned from the proposal,
so it does not fit in the same step — and the moment the proposal arrives the EGO's loop stops.
The proposal's reply carries `_meta["cogno-mcp/needs_confirmation"]` (and the argument name in
`cogno-mcp/confirm_arguments`); **without that flag the proposal would be recorded as a write**,
because the bridge reports `side_effect = mutating and not asks`.

Two things this buys beyond the wording of the question:

* **Ambiguity stops being silent.** `"internet"` matches January's, February's and March's bill.
  The one-shot version deleted the most recent and nobody — not the user, not the model, not the
  trace — learned the other two existed.
* **The row cannot drift.** Confirmation is a row **id**, not a yes/no. If a newer matching entry
  is recorded between the proposal and the confirmation, "the most recent match" would be a
  different row; pinning the id deletes what was proposed, or nothing.

This is the vertical half of the EGO's third confirmation gate (`cogno_anima.types.ToolResult.
needs_confirmation` — *the skill ran, read, and is asking about THIS call*). The flag itself is not
carried by `cogno-mcp` today (`grep -rn needs_confirmation` in that repo: zero hits), so over the
MCP bridge the proposal travels as ordinary tool text; the two-step is what protects the ledger
either way.

## Values the business declared are a source

A business can write fixed values into a persona's configured rules (a rent, an hourly rate, a
fee) and the persona quotes them with no tool. The reply-grounding backstop
(`bookkeeper/grounding.py: ground_reply`) takes them as `declared_values=` — the literal values of
the rules the host resolved for this contact's role, extracted by the ONE grammar in
`cogno_praxis.declared_values` (money, percentages, dates, numbers with a unit of time; never a
name or a sentence):

- `fabricated_entry`: three FORMS, three rules, and every value in the reply declared is the
  precondition for any exemption:
  - the **possessive stative** — first person of `ter`/`tener` + the participle ("tenho
    registrado R$ 10,00", "temos registrados", "tengo registrado") — describes what the persona
    HOLDS and is exempted by a FACT of the record: no ledger write (`add_income`, `add_outcome`,
    `remove_by_search`, or any call with `side_effect`) was CALLED this turn, succeeded or not.
    Not by the host's `is_read_query`, which is a guess made before execution and was measured
    False on turns that were in fact reads — the stative kept firing on exactly those;
  - the **bare participle** ("Registrado! R$ 10,00", "the recorded income is $1,440.00") still
    needs `is_read_query`: "registra o aluguel" → "Registrado! R$ 10,00" with nothing written is
    the fabricated receipt, and in it no write was called either, so the fact cannot separate
    it. Beside a stative, only the stative clause is excused;
  - the **explicit claim** ("registrei", "I've recorded", "registré") is never exempted by a
    declared price.
  - KNOWN LIMIT: "registra o aluguel" → "Tenho registrado: R$ 10,00 do aluguel." with nothing
    written passes — the form is a description and this rule does not read the request. On the
    demo box's whole corpus (569 traces) the stative appeared 8 times: every affirming one
    answered a question, the two after a write request were negations, none was a receipt.
- `conjured_totals`: a total that IS a declared value is not conjured; a derived one (a sum, a
  monthly total from an hourly rate) is written nowhere and still fires.
- No declared values → the rules read exactly as before.

The pt, en and es bundles share one split: explicit claim (first person, "acabei de / just",
copula + participle) fires always; the bare attributive participle only on a turn that read
nothing and declared nothing. `prompts/limits.txt` says the same thing to the judge: a financial
value comes from a tool call or from the values the business declared; computed values are not
declared, and a recorded entry is confirmed only by the tool that recorded it.

## Host integration

The host spawns this server over stdio and injects per-tenant config through the environment
(the same channel the scheduler uses):

- `COGNO_BOOKKEEPER_DSN` — Postgres DSN (usually the shared `COGNO_PG_DSN`); unset → in-memory demo.
- `COGNO_BOOKKEEPER_SCOPE` — the tenant scope (opaque; the store partitions/scopes by it).
- `COGNO_BOOKKEEPER_TODAY` — a fixed clock (ISO date) so the subprocess agrees with the host's
  `[TODAY]` anchor in deterministic harnesses; unset → real date.

Role visibility is the host's concern: it wraps the dispatcher (`RoleScopedDispatcher`) to pin
the caller's `identity_id` + role, so an EMPLOYEE only sees their own transactions and an
oversight role sees the whole scope — the vertical only maps role→visibility (mechanics).

See `docs/HOST_INTEGRATION.md` for the scheduler's wiring; the bookkeeper mirrors it. The full
port plan (phases, tests, benches) is in `docs/BOOKKEEPER_PLAN.md`.

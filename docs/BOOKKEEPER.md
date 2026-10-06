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
| `get_usage` | read-only | AI token/usage — **delegated to the host's metering** (see decision #4). It returns no figure, only where usage is metered. AI COST by cut (message, day, conversation, persona, user, month) is the host's `token_cost_analytics`: the persona text (`prompts/system.txt`, `prompts/limits.txt`) sends cost there whenever it is among the turn's tools, and the judge counts its figures as grounded; `get_usage` is the fallback when it is not offered. |
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
nothing and declared nothing (and, since `source_reads=`, whose declared source read does not hold
every value — see the next section). `prompts/limits.txt` says the same thing to the judge: a financial
value comes from a tool call or from the values the business declared; computed values are not
declared, and a recorded entry is confirmed only by the tool that recorded it.

## A document the host DECLARES a source read is a source

A host can offer the BOOKKEEPER a read over what the business WROTE — its documents — beside the
ledger tools this vertical ships. A reply answering from that read quotes the document's figures,
and often its words: a document that says «receitas registradas» gets a draft that says it too.
`ground_reply` read that as a receipt on a turn with no LEDGER read (rule 1, the attributive
participle) or as conjured totals (rule 3, «total»/«entradas» beside money), and rewrote a correct,
judge-approved answer into «Deixa eu consultar…» — measured 10 of 10 turns on a rehearsal tenant
(2026-09-29): 8 by rule 1 (always the POST-nominal participle, «… mensal registrada», «… meses
registrados»), 2 by rule 3 («líquido», «total») — and 4 of the 8 carried «líquido» as well, so the
two rules are excused together.

`ground_reply(..., source_reads=)` takes the host's declaration: the names of ITS tools that read
the business's material. **No tool name is written in this repo** — a read is a source because the
host said so, and an undeclared read of the same document grounds nothing. The exemption is by
VALUE: every money value in the reply (at least one) must be written in the result of a successful
(`ok`) call to a declared tool, compared through the one grammar of `cogno_praxis.declared_values`
(«R$ 4.500» in the document and «R$ 4.500,00» in the reply are one value). The whole result is
read, not a trace excerpt — a long document's figures sit far past one.

- `fabricated_entry`: only the ATTRIBUTIVE participle — the one that follows a word it describes,
  «as receitas registradas», «os valores registrados no contrato» — is excused, and only when no
  ledger write was CALLED this turn (the fact the stative exemption reads). Never excused:
  - the RECEIPT shape, the participle OPENING its clause («Registrado! R$ 150,00», «Lançado:
    R$ 500,00», «Lançada a despesa de R$ 50,00») — even when the document holds that value: a
    document grounds a figure, never an act, and the likeliest amount of a fabricated receipt is a
    price the business itself wrote;
  - the EXPLICIT claim («registrei», copula + participle, «acabei de lançar»).
- `conjured_totals`: a total the document WROTE is not conjured; a total COMPUTED from it (a sum of
  its rows, a year worked out from a month) is written nowhere and still fires.
- One value the document does not hold, a read that failed, or a read nobody declared → the rule
  reads exactly as before. No declaration → every verdict as before (a digest over 896 verdicts,
  taken on `main` before the parameter existed, pins it).
- KNOWN LIMITS (pinned in `test_a_source_read_grounds_the_listing_never_the_receipt.py`): a receipt
  with a word — or its value's comma — before the participle («Tudo registrado: R$ 150,00»,
  «Vistoria registrada: R$ 150,00», «R$ 150,00 registrado!») reads as the listing when a declared
  read holds every value and no write was called. That is the exposure a LEDGER read already has
  for ANY value, narrowed to values the document wrote. And a presentational ESTAR two words before
  the participle («Aqui estão os valores registrados») is the explicit branch's copula + participle,
  never excused. In English the attributive participle comes BEFORE its noun, so a clause-initial
  «Recorded income: $1,440.00» reads as the receipt shape and is not excused — the strict side;
  only pt was measured.
- The scheduler accepts the keyword and reads nothing from it: its rule 6 already admits a
  registered-material read by the value it returns (`MATERIAL_READ_TOOLS`), and moving that set
  onto the host's declaration is a change of its own.

**The stative decision is public API** (`cogno_praxis.bookkeeper.grounding.__all__`), because a
host's own generic net reads the same participle and, with a copy of this rule, rewrote what this
rule had passed:

- `write_attempted(tools) -> bool` — a ledger write was CALLED this turn (succeeded, failed or
  refused), or any call carries `side_effect`;
- `mask_possessive_stative(reply, locale) -> str` — the reply with the possessive-stative clauses
  blanked out (unchanged for a locale without the pattern, en, or an unsupported one);
- `mask_declared_stative(reply, *, tools, declared_values, locale) -> str` — the decision itself:
  the masked reply when every value is declared and no write was called, the reply unchanged
  otherwise. `ground_reply` reads it too, so the two readers cannot disagree.

A host calls these instead of copying the pattern; `tests/unit/test_the_public_stative_api.py`
pins their shape and meaning.

## The scope covers what the business OWNS, not only its ledger

`prompts/scope.txt` is the definition the host's relevance guard classifies a BOOKKEEPER turn
against. Its ALLOW paragraph opens with «any message about the business's finances» and then lists
ledger operations only, and the guard reads the list, not the opening. A question that a
published document answers, about what the business owns (its investments, what a property cost
to build or renovate), was BLOCKED even though the document's section titles were in the guard's
prompt. So the problem was the definition, not the prompt's structure.

One sentence after the list names the business's own **assets and investments**, "whether they
come from the ledger or from its documents". It is on the same line, byte for byte as measured
(production guard, n=5): that question went from BLOCK 5/5 to ALLOW 5/5, and an out-of-scope
control stayed BLOCK 5/5 either way. The other verticals' definitions also list only their tools'
operations, and they were not widened, because none of them was measured.
`tests/unit/test_bookkeeper_scope_names_assets_and_investments.py` pins that the sentence is in
the ALLOW paragraph. It also pins that the file without it is `main`'s byte for byte, and that
every neighbouring `scope.txt` is unchanged.

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

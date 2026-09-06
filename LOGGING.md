# Logging in cogno-praxis

This library follows the Cogno house rule: **libraries emit, the host configures.**

- Any module that logs does `logger = logging.getLogger(__name__)` and emits lazy
  `key=value` messages. The library installs **no** handlers/formatters and never
  calls `basicConfig`.
- The host attaches its handler and sets the level per package, e.g.
  `logging.getLogger("cogno_praxis").setLevel(logging.INFO)`.

## Level policy
- **ERROR** — never emitted. Recoverable domain failures raise `SchedulerError`,
  which the FastMCP layer surfaces as a tool error (`isError=True`) → cogno-mcp maps
  it to `ToolResult(ok=False)` and the EGO self-corrects. The host decides how to
  surface real failures.
- **WARNING** — a degradation or a refusal the operator has to know about, where
  raising would be worse than continuing. All of them today live in the Postgres
  store (`cogno_praxis.scheduler.stores.postgres`).
- **INFO / DEBUG** — one DEBUG, for a race that resolved itself. The `mcp` SDK does
  its own logging under the `mcp` namespace (FastMCP's stdio server prints request
  lines); configure/redirect it separately.

## What gets logged
Outcomes travel as tool return values / raised `SchedulerError`, not logs. Every line
the library emits comes from the Postgres store and says `stage=scheduler`. Three
`event=` values, from four call sites (`slot_uniqueness_unavailable` has two — a
duplicate-row refusal and any other Postgres error):

| level | `event=` | means |
|---|---|---|
| WARNING | `slot_uniqueness_unavailable` | the double-booking index could not be built; the service-level pre-check remains the guard |
| DEBUG | `slot_uniqueness_built_concurrently` | a sibling process built that index first — nothing to do |
| WARNING | `sync_hosts_empty_refused` | an empty catalog was ignored rather than deleting the scope's professionals (`kept=` says how many stayed). An operator who meant to empty the catalog learns here that the configuration did nothing |

Client names, appointment details and notes are domain data — **not** logged by
cogno-praxis. Metering of tool calls is the host's job (`cogno-meter`).

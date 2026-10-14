# Logging in cogno-praxis

This library follows the Cogno house rule: **libraries emit, the host configures.**

- Any module that logs does `logger = logging.getLogger(__name__)` and emits lazy
  `key=value` messages. The library installs **no** handlers/formatters and never
  calls `basicConfig`.
- The host attaches its handler and sets the level per package, e.g.
  `logging.getLogger("cogno_praxis").setLevel(logging.INFO)`.

## Level policy
- **ERROR** — never emitted. Recoverable domain failures raise the vertical's own error
  (`SchedulerError`, `BookkeeperError`, `CompanyError`, `CoordinatorError`), which the FastMCP
  layer surfaces as a tool error (`isError=True`) → cogno-mcp maps it to `ToolResult(ok=False)`
  and the EGO self-corrects. The host decides how to surface real failures.
- **WARNING** — a degradation or a refusal the operator has to know about, where raising would
  be worse than continuing: a sheet that could not be read, a configuration line that was
  skipped, a mailbox variable that is not valid JSON, an index that could not be built.
- **INFO** — one line: the coordinator saying that `cogno-herald` is not installed, so no
  calendar mail is configured.
- **DEBUG** — two lines: a race in the scheduler's store that resolved itself, and a
  discipline whose hour total could not be read.

The `mcp` SDK does its own logging under the `mcp` namespace (FastMCP's stdio server prints
request lines); configure or redirect it separately.

## What gets logged
Outcomes travel as tool return values or as the raised error, not as logs. The lines the
library does emit come from three places. The list is derived — `grep -rn '_log\.\|logger\.\|log\.' cogno_praxis`
— and this table is its reading on the day it was written.

**The scheduler's Postgres store** (`cogno_praxis.scheduler.stores.postgres`) — every line says
`stage=scheduler`. Three `event=` values, from four call sites (`slot_uniqueness_unavailable`
has two — a duplicate-row refusal and any other Postgres error):

| level | `event=` | means |
|---|---|---|
| WARNING | `slot_uniqueness_unavailable` | the double-booking index could not be built; the service-level pre-check remains the guard |
| DEBUG | `slot_uniqueness_built_concurrently` | a sibling process built that index first — nothing to do |
| WARNING | `sync_hosts_empty_refused` | an empty catalog was ignored rather than deleting the scope's professionals (`kept=` says how many stayed). An operator who meant to empty the catalog learns here that it was not emptied |

**The scheduler's engine** (`cogno_praxis.scheduler.engine`) — one WARNING, when the holiday
calendar of a country/state could not be loaded: holiday filtering is then off.

**The coordinator** (`cogno_praxis.coordinator.config`, `.service`, `.mailer`) — plain sentences
prefixed `coordinator:`, with no `event=` key:

| level | where | means | carries |
|---|---|---|---|
| WARNING | `config` | a `SPREADSHEETS` entry that does not look like a spreadsheet id was skipped; or the header was declared and no usable line followed | the entry's KEY and the length of the value, never the id |
| WARNING | `config` | the persona rules describe pay figures in PROSE this configuration does not read | the sentences it recognised; once per distinct set |
| WARNING | `service` | a spreadsheet, its hours tab, its IBOPE tab or its professors tab could not be read | the sheet's KEY, **its id**, and the exception |
| WARNING | `service` | the hours tab has no hours/discipline column: the workload context is skipped | the tab, the sheet's KEY and the two column names |
| WARNING | `service` | two names share an e-mail address and neither is the other written out: NOT joined | **the two names, as the sheet writes them** |
| DEBUG | `service` | a discipline carries no readable hour total | the discipline and the sheet's KEY |
| WARNING | `mailer` | the calendar mail was not accepted by the server | nothing |
| WARNING | `mailer` | `COGNO_COORDINATOR_SMTP` is not valid JSON, or not a JSON object: ignored | the variable's name, never its value |
| INFO | `mailer` | `cogno-herald` is not installed | nothing |

So the scheduler, the bookkeeper and the companies vertical log no domain data: client names,
appointment details and notes are not logged. The coordinator is the exception, and it is said
here rather than left to be found: one WARNING carries two professors' names, and the
read-failure lines carry a spreadsheet's id and whatever the store's exception says. A host that
ships these logs off the box should treat the `cogno_praxis.coordinator` namespace as carrying
personal data. Metering of tool calls is the host's job (`cogno-meter`).

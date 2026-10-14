# Logging in cogno-praxis

This library follows the Cogno house rule: **libraries emit, the host configures.**

- Any module that logs binds one module-level logger from `logging.getLogger(__name__)` and
  emits lazy `key=value` messages. The library installs **no** handlers/formatters and never
  calls `basicConfig`.
- The host attaches its handler and sets the level per package, e.g.
  `logging.getLogger("cogno_praxis").setLevel(logging.INFO)`.
- A message is in one grammar:

  ```
  [stage=<word> ]event=<name>( <key>=<value>)*[ — <prose>]
  ```

  Every `%` placeholder sits directly behind its `key=`, so every value a line carries has a
  name. The prose after ` — ` is fixed text and carries no value.
- **No message carries text somebody else wrote, and none carries an identifier.** Not a
  professor's name, not a discipline, not what the tenant called a spreadsheet, a tab or a
  column, not a sentence of the persona's rules, not a spreadsheet's id, not a scope, not an
  exception's message. A line says HOW MANY and WHICH KIND: a count, a row number, a member of
  a closed vocabulary, a class name, and — where two lines must be matched — a short digest.

## Level policy
- **ERROR** — never emitted. Recoverable domain failures raise the vertical's own error
  (`SchedulerError`, `BookkeeperError`, `CompanyError`, `CoordinatorError`), which the FastMCP
  layer surfaces as a tool error (`isError=True`) → cogno-mcp maps it to `ToolResult(ok=False)`
  and the EGO self-corrects. The host decides how to surface real failures.
- **WARNING** — 13 calls. A degradation or a refusal the operator has to know about, where
  raising would be worse than continuing: a sheet that could not be read, a configuration line
  that was skipped, a mailbox variable that is not valid JSON, an index that could not be
  built.
- **INFO** — 1 call: the coordinator saying that `cogno-herald` is not installed, so no
  calendar mail is configured.
- **DEBUG** — 2 calls: a race in the scheduler's store that resolved itself, and a row of the
  hours tab whose total could not be read.

The `mcp` SDK does its own logging under the `mcp` namespace (FastMCP's stdio server prints
request lines); configure or redirect it separately.

## Events

This table is the code's list. `tests/unit/test_logging_md_lists_what_the_code_emits.py` reads
every log call of the package by AST and compares it with the rows below, in both directions:
the logger, the event, the level, the `key=` fields and whether the line carries a traceback.

| Logger | Event | Level | When |
|---|---|---|---|
| `cogno_praxis.coordinator.config` | `spreadsheet_entry_skipped` (`reason=not_an_id`, `sheet_sha`, `value_len`) | WARNING | a `SPREADSHEETS` entry whose value does not look like a spreadsheet id was skipped |
| `cogno_praxis.coordinator.config` | `spreadsheets_header_without_entries` | WARNING | a `SPREADSHEETS:` header was declared and no usable `KEY = ID` line followed it |
| `cogno_praxis.coordinator.config` | `pay_figures_in_prose` (`keys`, `excerpts`) | WARNING | the persona rules describe pay figures in prose this configuration does not read; once per distinct set per process |
| `cogno_praxis.coordinator.service` | `sheet_unreadable` (`tab=schedule\|hours\|ibope\|professors`, `sheet_sha`, `error`, `status`) | WARNING | a tab of a spreadsheet could not be read; the other spreadsheets are still read |
| `cogno_praxis.coordinator.service` | `hours_columns_missing` (`sheet_sha`, `missing=hours\|subject\|hours,subject`) | WARNING | the hours tab has no hours column, or no discipline column: the workload context is skipped, the estimate is unaffected |
| `cogno_praxis.coordinator.service` | `hours_unreadable` (`sheet_sha`, `row`) | DEBUG | a row of the hours tab names a discipline and carries no readable hour total |
| `cogno_praxis.coordinator.service` | `faculty_names_not_joined` (`pairs`) | WARNING | rows of the professors tab share an e-mail address and neither name is the other written out: they are NOT joined |
| `cogno_praxis.coordinator.mailer` | `calendar_mail_not_accepted` | WARNING | the calendar mail was not accepted by the server |
| `cogno_praxis.coordinator.mailer` | `smtp_env_ignored` (`reason=not_json\|not_an_object`, `var`) | WARNING | the mailbox variable is not valid JSON, or is JSON and not an object: ignored |
| `cogno_praxis.coordinator.mailer` | `herald_not_installed` | INFO | `cogno-herald` is not installed, so no calendar mail is configured |
| `cogno_praxis.scheduler.engine` | `holidays_unavailable` (`country`, `state`, `error`) | WARNING | the holiday calendar of a country/state could not be loaded: holiday filtering is off |
| `cogno_praxis.scheduler.stores.postgres` | `slot_uniqueness_unavailable` (`reason=duplicate_active_rows`, `action`) | WARNING | the double-booking index could not be built because duplicate rows exist; `action` is the query that finds them |
| `cogno_praxis.scheduler.stores.postgres` | `slot_uniqueness_unavailable` (`reason`, `error`) | WARNING | the index could not be built for any other reason; `reason` is the SQLSTATE. The service-level pre-check remains the guard |
| `cogno_praxis.scheduler.stores.postgres` | `slot_uniqueness_built_concurrently` | DEBUG | a sibling process built that index first — nothing to do |
| `cogno_praxis.scheduler.stores.postgres` | `sync_hosts_empty_refused` (`scope_sha`, `kept`) | WARNING | an empty catalog was ignored rather than deleting the scope's professionals (`kept` says how many stayed). An operator who meant to empty the catalog learns here that it was not emptied |

`sheet_unreadable` is ONE call, in a helper the four reads share, and `smtp_env_ignored` is two
calls with the same fields: one row each. A line of the coordinator
opens with `stage=coordinator`; a line of the scheduler with `stage=scheduler`.

## Modules that log nothing

The bookkeeper, the companies vertical, the closer and the interviewer log nothing.

- `cogno_praxis`
- `cogno_praxis.bookkeeper`
- `cogno_praxis.bookkeeper.arithmetic`
- `cogno_praxis.bookkeeper.durability`
- `cogno_praxis.bookkeeper.engine`
- `cogno_praxis.bookkeeper.grounding`
- `cogno_praxis.bookkeeper.server`
- `cogno_praxis.bookkeeper.service`
- `cogno_praxis.bookkeeper.store`
- `cogno_praxis.bookkeeper.stores`
- `cogno_praxis.bookkeeper.stores.postgres`
- `cogno_praxis.closer`
- `cogno_praxis.companies`
- `cogno_praxis.companies.confirmations`
- `cogno_praxis.companies.identifiers`
- `cogno_praxis.companies.server`
- `cogno_praxis.companies.service`
- `cogno_praxis.companies.store`
- `cogno_praxis.companies.stores`
- `cogno_praxis.companies.stores.postgres`
- `cogno_praxis.contact_wording`
- `cogno_praxis.coordinator`
- `cogno_praxis.coordinator.durability`
- `cogno_praxis.coordinator.footers`
- `cogno_praxis.coordinator.ics`
- `cogno_praxis.coordinator.pay`
- `cogno_praxis.coordinator.rsvp`
- `cogno_praxis.coordinator.server`
- `cogno_praxis.coordinator.store`
- `cogno_praxis.coordinator.stores`
- `cogno_praxis.coordinator.stores.google_sheets`
- `cogno_praxis.coordinator.types`
- `cogno_praxis.declared_values`
- `cogno_praxis.email_fields`
- `cogno_praxis.grounding`
- `cogno_praxis.interviewer`
- `cogno_praxis.logsafe`
- `cogno_praxis.render`
- `cogno_praxis.scheduler`
- `cogno_praxis.scheduler.durability`
- `cogno_praxis.scheduler.grounding`
- `cogno_praxis.scheduler.server`
- `cogno_praxis.scheduler.service`
- `cogno_praxis.scheduler.store`
- `cogno_praxis.scheduler.stores`

## What a line carries

Every value a line carries is named by its `key=`, and every key has ONE class.
`tests/unit/test_logs_carry_no_third_party_text.py` reads the table below, holds every log
call's arguments to it, and pins the expression each key is given — a new key, or a new
expression under an old key, fails until it is classified here.

The classes:

- **count** — a number this library computed: how many, a length, a row of a tab, an HTTP
  status.
- **closed** — a member, or a list of members, of a closed vocabulary this library defines: one
  of four tab words, a configuration key, a SQLSTATE, a fixed query.
- **type** — a Python class name, `type(x).__name__`, of an exception. Never its message.
- **digest** — `cogno_praxis.logsafe.id_sha`: the first 12 hex characters of the SHA-256 of an
  identifier. It is the same function the reference host uses for a scope in a log line, so one
  digest finds the lines of both. Two lines about the same sheet or scope match, and someone
  holding the key or the scope can compute it. It is de-identification of the log stream, not
  encryption: an identifier is low-entropy and can be enumerated.
- **name** — a code the HOST declared: the country and the state of a holiday calendar. The one
  class the library does not close.
- **constant** — the key only ever appears with a literal value in the message.

There is no class for text.

| Field | Class | What the value is |
|---|---|---|
| `action` | closed | the fixed query that lists the duplicate rows |
| `country` | name | the holiday calendar's country code, as the host configured it |
| `error` | type | the class of the exception |
| `excerpts` | count | how many sentences of the rules were recognised |
| `keys` | closed | the pay keys found in prose (`PAY_RATE_PER_HOUR`, `HOURS_PER_CLASS`, `IBOPE_BONUS`, `IBOPE_MIN_RESPONSE_PCT`), comma-joined |
| `kept` | count | how many professionals stayed |
| `missing` | closed | `hours`, `subject`, or both |
| `pairs` | count | how many pairs of rows were not joined |
| `reason` | closed | the SQLSTATE of the Postgres error, or `unknown`; otherwise a literal |
| `row` | count | the row within the range read, the header being row 1 |
| `scope_sha` | digest | the scheduler scope |
| `sheet_sha` | digest | the KEY the tenant gave the spreadsheet — never its id |
| `state` | name | the holiday calendar's state code, or `-` |
| `status` | count | the HTTP status the store's exception carried, or `0` |
| `tab` | closed | `schedule`, `hours`, `ibope` or `professors` — never the name the tenant gave the tab |
| `value_len` | count | the length of the value that is not an id |
| `var` | closed | the name of the mailbox variable, `COGNO_COORDINATOR_SMTP` — never its value |

### What is not in the log

- **A professor's name.** `faculty_names_not_joined` says how many pairs; each block the tool
  renders names the other, to the person who is allowed to read it.
- **A spreadsheet's id, and the name the tenant gave it, its tabs or its columns.**
- **A discipline.** `hours_unreadable` gives the row.
- **A sentence of the persona's rules.** The refusal the estimate answers with quotes them, to
  the tenant who wrote them.
- **A scope.** It is a tenant's id and a contact's channel id.
- **An exception's message.** An HTTP client's message embeds the request URL, and with it the
  spreadsheet's id; a Postgres message quotes the row it tripped on.
- Client names, appointment details, notes, amounts: the scheduler, the bookkeeper and the
  companies vertical never logged them. Outcomes travel as tool return values or as the raised
  error. Metering of tool calls is the host's job (`cogno-meter`).

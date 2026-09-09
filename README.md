# cogno-praxis

**The Cogno business verticals, as standalone MCP servers.**

πρᾶξις = *action / practice* — the **applied layer**: ready-made, open-source
business verticals on top of the Cogno substrate. Each vertical is an **independent FastMCP server** the host orchestrates
via [`cogno-mcp`](https://github.com/sudoers-ai/cogno-mcp). Verticals own their
domain logic + data (behind their own store ports); the host stays the thin
**assembler** — persona, pipeline, dispatcher composition, RBAC, orchestration rules.

```
vertical (FastMCP server) ──(stdio/HTTP)──▶ cogno-mcp MCPDispatcher ──▶ EGO / cogno-soma
   owns: domain logic + data                                              owns: orchestration
```

The architecture follows MCP's grain: verticals are **separate processes**, decoupled
by protocol, deployable/scalable/ownable independently (even by external partners).
Two layers of "business rules" stay separate: **orchestration** rules live in the host;
**domain** rules live in the vertical.

## Verticals

| Vertical | What it is | Tools |
|---|---|---|
| **scheduler** | the agenda capability — ships the **SECRETARY** persona, the universal reception/scheduling front door for any client | `list_schedulable_hosts`, `check_availability`, `book_appointment`, `list_appointments`, `confirm_appointment`, `complete_appointment`, `cancel_appointment` |
| **bookkeeper** | the financial capability — ships the **BOOKKEEPER** persona (parent SaaS ANALYST): records income/expenses, tracks clients, produces summaries. See [`docs/BOOKKEEPER.md`](docs/BOOKKEEPER.md) | `add_income`, `add_outcome`, `get_summary`, `list_clients`, `search`, `remove_by_search`, `get_usage`, `help` |
| **coordinator** | the academic capability — ships the **COORDINATOR** persona: reads class schedules across a tenant's course spreadsheets, checks grade/attendance deadlines, estimates a professor's OWN pay from tenant-declared figures, finds open slots, swaps a class, and mails a professor their classes as a calendar | `get_professor_schedule`, `get_professor_info`, `check_deadlines`, `get_weekly_briefing`, `check_ibope_status`, `daily_checks`, `estimate_professor_pay`, `find_replacement_slot`, `confirm_swap`, `preview_schedule_to_calendar`, `send_schedule_to_calendar` |
| **companies** | the brand-registration capability — **transversal**: it belongs to no persona's domain, and a front-desk persona carries it beside its own vertical. Rows are keyed by the accent-folded company name, so registering one again UPDATES it — and a field a registration or an update is not given is left exactly as it was. Scoped by identity: staff see the business's companies, anyone else sees the ones they registered | `company_registration`, `company_search`, `list_companies`, `company_update`, `company_delete` |

More verticals (restaurant, veterinary, …) follow the same shape.

### The calendar export (`send_schedule_to_calendar`)

The coordinator's second write, and the only one that leaves the house: it reads the
professor's upcoming classes — through the very same `get_professor_schedule` and therefore the
same role scoping — and e-mails them as **one** `.ics` with **one `VEVENT` per class**. One
message with every class in it, because that is what a calendar imports in a single action.

Three things about it are worth knowing before you wire it:

- **The `UID` is derived from CONTENT** — class group + discipline + date (+ hour when the sheet
  has one), normalized and digested — never from the spreadsheet ROW. A row index is a
  *position*: insert one class at the top of the sheet and every index below it shifts, so
  row-derived identifiers would make the next send duplicate the professor's whole term instead
  of updating it. Send it again after a room change and the entries update in place.
- **Delivery is a port, and the mailbox belongs to ONE tenant.** `CalendarSender`
  (`coordinator/ics.py`) is injected into `build_server(service, sender=…)` when the host has
  already resolved it, or `build_server(service, sender_for=…)` — a callable asked **on every
  calendar tool call**, which is what a process serving more than one tenant needs.
  `coordinator/mailer.py` is the SMTP adapter over
  [`cogno-herald`](https://github.com/sudoers-ai/cogno-herald) — an **optional** dependency
  (install it from git; it is not on PyPI yet, so it is not declarable as an extra). The mailbox
  is **only ever what THIS tenant declared** (`COGNO_COORDINATOR_SMTP`, or whatever `sender_for`
  answers): nothing declared → **no sender**, and the tool refuses honestly and sends
  **nothing**. It deliberately does **not** fall back to the deployment's `SMTP_*` — a booking
  invite does, because every tenant's confirmations should leave, but a class calendar is an
  institution writing to its own faculty and a tenant that declared no mailbox has not asked to
  write to anybody. It never swallows a message either.
- **Every path that did not send RAISES**, so the MCP bridge reports `ok=False` /
  `side_effect=False` and the turn is never recorded as a write that did not happen. The one
  non-error answer starts with `SENT:`.
- **The question is asked by a READ, not by the gate.** `preview_schedule_to_calendar` is the
  read-only half: same arguments, same rows, same refusals — it answers with the exact count,
  the period the filter actually applied and the recipient the send would resolve, prefixed
  `NOT SENT`, and mails nothing. It exists because a confirmation gate stops the send by NAME
  *before* it can read, so the skill never learns what it would be sending and the only thing
  left for any layer downstream to show a professor is the raw argument. Measured live on
  2026-09-06: the contact was asked *"Confirmo: esta ação — 2026-09. Posso seguir?"*. A gate
  cannot ask the skill's question for it; a read that runs can. Same relationship
  `find_replacement_slot` has with `confirm_swap`. The period clause is **conditional** — a
  request that filtered by no month claims none, because echoing the caller's own string back
  is how a listing spanning two months gets proposed as one of them.

Zones: an hour travels with the tenant's `TZID` (`COGNO_COORDINATOR_TZ`, stamped by the host
from its own `tenant_tz`). No hour column, or no declared zone → an **all-day** event. Never a
floating time, never raw UTC.

**Prompt-only personas.** Two personas ship here with **no tools of their own** — just the
four prompt slots (`system`, `voice`, `scope`, `limits`) as package data, loaded by the host's
`PersonaSpec`: **`closer/`** (a commercial diagnostic that runs the tenant's declared
checklist) and **`interviewer/`** (interviews, forms and checklists, one question per turn,
a consolidated summary at the end). They get the host's *system* skills like every persona
(the date anchor and `resolve_date`, staff notify/directory) and nothing else. The persona's
display name is never in these files — `system.txt` says `{identity_label}`/`{tenant_name}`
and the host overlays the tenant's `display_name` — so one prompt serves every tenant's
"Carol" or "Tony". Any domain script (a content calendar, a campaign table) belongs in the
tenant's `custom_rules`, not in the base prompt: a base prompt that carries a domain script
competes with the tenant's own and the model obeys both (measured on the CLOSER, 2026-09-05).

**Capability vs persona.** `scheduler` is the *capability* (the agenda machine); the
**SECRETARY** is the default *persona* that ships with it (prompt slots in
`scheduler/prompts/`) — the out-of-the-box front door that works for any company with
zero config. A company that needs a richer receptionist adds its **own** persona
host-side (via cogno-persona), targeting this same `scheduler` capability and composing
extra tool sources with `CompositeDispatcher` — **without** touching the scheduler.

## Quickstart — a complete agent in 15 minutes

The fastest way to *feel* the whole stack: `examples/secretary_demo.py` runs the
full cognitive pipeline (cogno-soma over the cogno-anima stages) against local
Ollama, with this repo's scheduler vertical served as a real MCP subprocess and
the bundled SECRETARY persona doing the talking:

```bash
# 1. local models (the download dominates the 15 minutes)
ollama pull qwen3:8b && ollama pull nomic-embed-text

# 2. the Cogno chain (PyPI soon — from git for now, one command)
pip install "git+https://github.com/sudoers-ai/cogno-homeo" \
            "git+https://github.com/sudoers-ai/cogno-synapse" \
            "git+https://github.com/sudoers-ai/cogno-anima" \
            "git+https://github.com/sudoers-ai/cogno-soma" \
            "cogno-mcp[mcp] @ git+https://github.com/sudoers-ai/cogno-mcp"

# 3. this repo + the demo
git clone https://github.com/sudoers-ai/cogno-praxis && cd cogno-praxis
pip install -e .
python examples/secretary_demo.py --trace     # --trace shows the cognition live
```

Then just talk, in any language:

```
você> oi, queria marcar uma consulta com o dr silva amanhã às 9 da manhã
  [NOUMENO]  "Hello, I would like to schedule an appointment with Dr. Silva tomorrow at 9…"  (pt → en)
  [NER]      ACTION_REQUEST · NEUTRAL · domains=['HEALTH'] · pii_risk=NONE
  [ID]       route=EGO · goal=NEW · turn=1
  [EGO]      resolve_date(expression=tomorrow) ✓
  [EGO]      check_availability(host_id=dr_silva, date=2026-07-11) ✗   ← Saturday: rejected
  [EGO]      book_appointment(host_id=dr_silva, date=2026-07-13, time=09:00, …) ✓
  [JUDGE]    approved=True
SECRETARY> Oi, Ana! 😊 Amanhã, 11/07, não tem expediente aos sábados, então sua
           consulta com o Dr. Silva foi marcada para o próximo dia útil, 13/07, às 9h. ✅
```

That weekend recovery is the pipeline working as designed: the vertical's
working-day rule rejected the tool call, the EGO self-corrected, the judge
approved, and the voice explained — all on a free 8B local model.

## Run a vertical

```bash
pip install cogno-praxis            # pulls the mcp SDK
python -m cogno_praxis.scheduler.server      # serves the demo over stdio
```

The host connects to it with cogno-mcp:

```python
import sys
from cogno_mcp import MCPDispatcher, stdio_session

async with stdio_session(sys.executable, args=["-m", "cogno_praxis.scheduler.server"]) as s:
    dispatcher = await MCPDispatcher.create(s)
    # bind to the SECRETARY persona + run the pipeline:
    await pipe.run_turn(ctx, cfg, dispatcher=dispatcher)     # cogno-soma
```

Tool **annotations** (`readOnlyHint` / `destructiveHint`) flow through cogno-mcp into
the EGO's read-only mask + confirmation gate — e.g. `cancel_appointment` is destructive,
so the EGO holds it for confirmation.

## Anatomy of a vertical (`scheduler`)

- `store.py` — domain types (`Host`, `Appointment`) + an `AppointmentStore` **port**
  (Protocol) with an in-memory default. Appointments are structured domain data, not
  conversation memory, so the vertical owns its store (host plugs a real DB adapter);
  `cogno-engram` stays for episodic/KG memory.
- `service.py` — pure scheduling logic (book / cancel / availability / status
  lifecycle + the "from tomorrow on" rule) over the store.
- `server.py` — the thin FastMCP wrapper exposing the service as annotated tools.
  `build_server(service)` is the only injection seam (see `examples/run_with_db.py`).
- `prompts/` — the bundled **SECRETARY** persona slots (system / scope / limits / voice),
  loaded by the host via `cogno-persona`. The capability is persona-agnostic; SECRETARY
  is simply its default face.

A vertical's tool **wins the name** over a host builtin (the dispatcher is first-wins and
module sources come first) — if a vertical ships a tool, it is because that tool matters to
the domain. The flip side: a model then sees *your* shell, so improvements to the host's
builtin never reach personas using your module. Put the behaviour in `service.py` and keep
both shells thin — `resolve_date` exports its parser **and** its spoken-form renderer, which
the host's builtin imports rather than copying. See
[`docs/HOST_INTEGRATION.md` §6.1](docs/HOST_INTEGRATION.md).

## The Cogno ecosystem

`cogno-praxis` is one organ of **[Cogno](https://github.com/sudoers-ai)** — a family of
small, composable, Apache-2.0 libraries that together form a complete
conversational-agent platform. Each library owns a single concern and stays
infra-agnostic; a **host** assembles them into a running agent:

![The Cogno ecosystem](docs/assets/cogno-ecosystem.svg)

The open-source libraries are the organs; the **host is the body** that joins
them. Our reference host — `cogno-host`, with its `cogno-ui` dashboard — is the
private product layer, but it holds no special powers: everything it does rides
on the public seams documented in each library's `docs/HOST_INTEGRATION.md`, so
you can assemble a body of your own.

## Development

```bash
pip install -e ".[dev]"
pytest tests/unit -q            # service + server (in-process), no network
pytest tests/integration -q     # scheduler server over stdio via cogno-mcp (the real loop)
                                # + the Postgres store, against `cogno_praxis_test` on the
                                # local server — taken from COGNO_PG_DSN if the shell exports
                                # one, else libpq's PGHOST/PGPORT/PGUSER/PGPASSWORD (whose
                                # defaults are what CI's postgres service serves). Auto-skips
                                # if nothing is listening. Those tests DROP TABLE, so the
                                # database NAME is never taken from any of them: it is always
                                # `cogno_praxis_test`. COGNO_TEST_PG_DSN overrides, and a name
                                # without "test" in it is refused at collection.
ruff check cogno_praxis tests && mypy cogno_praxis
python examples/host_min.py     # spawn the server + run a reception flow
```

Apache-2.0.

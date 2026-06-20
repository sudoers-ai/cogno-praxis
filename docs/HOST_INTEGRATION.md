# Host integration — cogno-praxis

A praxis vertical is a standalone MCP server. The host orchestrates it; it never
imports the host. This guide maps the seams for the `scheduler` vertical — the agenda
capability that ships the **SECRETARY** persona (the others follow the same shape).

## 1. The boundary

| Layer | Owns |
|---|---|
| **vertical (cogno-praxis)** | domain logic + domain data (e.g. appointments) + the tool surface, as a FastMCP server. |
| **cogno-mcp** | the transport bridge: turns the server into a cogno-anima `ToolDispatcher`. |
| **host** | orchestration: persona selection, the pipeline (cogno-soma), dispatcher composition, RBAC/ceiling, when to confirm, metering, channels, conversation memory. |

Two layers of "business rules": **orchestration** rules are the host's; **domain**
rules are the vertical's. Keep them apart — the host never computes a domain answer,
the vertical never decides persona/routing.

## 2. Connect + bind

```python
import sys
from cogno_mcp import MCPDispatcher, stdio_session

async with stdio_session(sys.executable, args=["-m", "cogno_praxis.scheduler.server"]) as s:
    scheduler = await MCPDispatcher.create(s)
    # compose with other sources the persona allows:
    from cogno_anima.tools import CompositeDispatcher
    dispatcher = CompositeDispatcher([scheduler, cortex_skills, native_tools])
    await pipe.run_turn(ctx, cfg, dispatcher=dispatcher)     # cogno-soma + SECRETARY persona
```

Transports (stdio / HTTP / SSE) and lifecycle are cogno-mcp's; the host chooses how to
run the server (subprocess for stdio, or a long-running HTTP service it connects to).

## 3. The SECRETARY persona (and adding your own)

`scheduler` is the *capability*; **SECRETARY** is the default *persona* that ships with
it. Its prompt slots live in `cogno_praxis/scheduler/prompts/` (`system.txt`,
`scope.txt`, `limits.txt`, `voice.txt`). Load them via `cogno-persona` and pass them
into the `TurnConfig` (`ego_prompt` / `scope_prompt` / `limits_prompt` / `voice_prompt`).
SECRETARY is the **base/entry persona** the host selects by default and falls back to (it
routes the visitor to specialists) — and it works for any company with zero config.

The prompts carry host-injected placeholders kept literal in the files: `{secretary_name}`,
`{tenant_name}`, `{identity_label}` / `{identity_role}` / `{identity_email}`, and the blocks
`{{ROLE_CAPABILITIES}}` / `{{TENANT_PERSONAS}}`. The host fills them (RBAC, identity,
departments) when it renders the persona — the vertical knows none of it.

**Customizing.** A company that needs a richer receptionist does **not** edit the bundled
SECRETARY. It defines its **own** persona (host-side, via cogno-persona) that targets the
same `scheduler` capability and composes extra tool sources (other verticals, cortex
skills, native functions) with `CompositeDispatcher`. The scheduler is reused unchanged;
the new persona just brings its own 4 prompt slots + whatever sources it declares.

## 4. Persistence

The vertical persists through its own port (`AppointmentStore`), defaulting to
in-memory. For production inject a real adapter (Postgres/Redis/your DB) implementing
the Protocol — the server logic is unchanged. Appointments are structured domain data;
keep them out of `cogno-engram` (which is conversation/episodic memory).

**Where the DB connection lives.** The only seam is `build_server(service)`. The
module-level `cogno_praxis.scheduler.server:mcp` is an in-memory **demo**; for real data
the host writes a tiny entrypoint that builds the service over its adapter and runs it
(see `examples/run_with_db.py`):

```python
store = MyPostgresAppointmentStore(dsn=os.environ["SCHEDULER_DSN"])  # connection born here
build_server(SchedulerService(store=store)).run()                    # in the vertical's process
```

The DB connection is created **inside the vertical's own process** and never crosses the
MCP boundary — the host that connects (stdio subprocess or a long-running HTTP service)
need not share the pool. **Multi-tenancy** is just *which* store/DSN you build here (one
process/DSN per tenant), not a column the scheduler filters — it stays tenant-agnostic.

## 5. Tool policy → EGO gates

Each tool's `annotations` drive the EGO via cogno-mcp:
- `readOnlyHint=True` (reads) → never masked, never gated.
- writes (`book_appointment`) → `is_mutating` true → masked under `ego_readonly`.
- `destructiveHint=True` (`cancel_appointment`) → `requires_confirmation` → the EGO
  holds the call until the host confirms.

## 6. Adding a vertical

Mirror `scheduler/`: `store.py` (types + a store Protocol + in-memory default),
`service.py` (pure domain logic), `server.py` (`build_server(service)` → FastMCP with
annotated tools + a seeded module-level demo `mcp` for stdio), `prompts/` (the bundled
default persona slots). Keep domain logic in `service.py` (testable without MCP); keep
`server.py` thin.

## 7. What stays yours

Real domain data + adapters, RBAC (which identity may reach which vertical), persona
selection, metering, the deploy topology (how/where servers run), auth between host
and server. cogno-praxis is the domain server; you bring the data and the orchestration.

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

### 6.1 When your tool has the same name as a host builtin

The host ships cross-cutting builtins — `resolve_date` is the one every persona gets. The
`CompositeDispatcher` is **first-wins** and module sources come **before** the host's extras,
so **your module's tool wins the name**. That is deliberate: if a vertical ships a tool, it
is because the tool matters to that domain, and the host must not override it.

The cost is that a model then sees *your* version, and any improvement made to the host's
builtin never reaches the personas that use your module. That already happened here: on
2026-08-04 the host's `resolve_date` gained a description naming every form the parser
accepts and an error that tells the model to *ask the user*, and the SECRETARY — which uses
the scheduler's copy — got neither. Two shells over one parser had drifted.

**So the rule is: put the behaviour in the library, keep both shells thin.**

    cogno_praxis/scheduler/service.py     ← the parser AND the spoken-form renderer
             ▲                    ▲
    scheduler/server.py     cogno_host/date_tool.py
      (MCP tool)              (host builtin)
             │                    │
        SECRETARY            every other persona

Concretely, when you add a tool that shadows a host builtin:

1. **Export the logic** from `service.py` (or your vertical's equivalent) so the host's
   builtin can import it instead of keeping a second copy. `resolve_date` exports both the
   parser and `format_date`.
2. **Match the payload shape.** A model cannot tell the two apart, so they must not read
   differently. `resolve_date` returns
   `2026-07-07 (terça-feira, 7 de julho de 2026). Use the ISO date in tool calls; the written
   form when speaking to the user.` — the spoken form is not decoration: the incident behind
   it is a persona reading `2026-07-25 (Saturday)` and still voicing "sexta-feira". Render by
   index, never `strftime` (`%A` follows the *server* locale).
3. **Match the error text, and make it say what to DO.** `could not resolve` alone left the
   model rewording the same unresolvable phrase and burning a second step on the identical
   failure.
4. **Only promise what you deliver.** A description is a contract: every form it names must
   actually work, and a form that cannot work (a vague span like "semana que vem" — it names
   no single day) must be named as something *not* to call the tool with. See
   `tests/unit/test_resolve_date_contract.py`, which asserts both directions and is the
   template to copy for a new tool.

## 7. What stays yours

Real domain data + adapters, RBAC (which identity may reach which vertical), persona
selection, metering, the deploy topology (how/where servers run), auth between host
and server. cogno-praxis is the domain server; you bring the data and the orchestration.

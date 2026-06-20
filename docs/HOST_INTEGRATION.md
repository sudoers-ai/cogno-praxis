# Host integration — cogno-praxis

A praxis vertical is a standalone MCP server. The host orchestrates it; it never
imports the host. This guide maps the seams for the `secretary` vertical (the others
follow the same shape).

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

async with stdio_session(sys.executable, args=["-m", "cogno_praxis.secretary.server"]) as s:
    secretary = await MCPDispatcher.create(s)
    # compose with other sources the persona allows:
    from cogno_anima.tools import CompositeDispatcher
    dispatcher = CompositeDispatcher([secretary, cortex_skills, native_tools])
    await pipe.run_turn(ctx, cfg, dispatcher=dispatcher)     # cogno-soma + SECRETARY persona
```

Transports (stdio / HTTP / SSE) and lifecycle are cogno-mcp's; the host chooses how to
run the server (subprocess for stdio, or a long-running HTTP service it connects to).

## 3. The SECRETARY persona

The persona prompt slots live in `cogno_praxis/secretary/persona/` (`system.txt`,
`scope.txt`, `limits.txt`, `voice.txt`). Load them via `cogno-persona` and pass them
into the `TurnConfig` (`ego_prompt` / `scope_prompt` / `limits_prompt` / `voice_prompt`).
SECRETARY is typically the **base/entry persona** the host selects by default and falls
back to (it routes the visitor to specialists).

## 4. Persistence

The vertical persists through its own port (`AppointmentStore`), defaulting to
in-memory. For production inject a real adapter (Postgres/Redis/your DB) implementing
the Protocol — the server logic is unchanged. Appointments are structured domain data;
keep them out of `cogno-engram` (which is conversation/episodic memory). Run the server
where it can reach your DB; the host need not share that connection.

## 5. Tool policy → EGO gates

Each tool's `annotations` drive the EGO via cogno-mcp:
- `readOnlyHint=True` (reads) → never masked, never gated.
- writes (`book_appointment`) → `is_mutating` true → masked under `ego_readonly`.
- `destructiveHint=True` (`cancel_appointment`) → `requires_confirmation` → the EGO
  holds the call until the host confirms.

## 6. Adding a vertical

Mirror `secretary/`: `store.py` (types + a store Protocol + in-memory default),
`service.py` (pure domain logic), `server.py` (`build_server(service)` → FastMCP with
annotated tools + a seeded module-level `mcp` for stdio), `persona/` (the persona
slots). Keep domain logic in `service.py` (testable without MCP); keep `server.py`
thin.

## 7. What stays yours

Real domain data + adapters, RBAC (which identity may reach which vertical), persona
selection, metering, the deploy topology (how/where servers run), auth between host
and server. cogno-praxis is the domain server; you bring the data and the orchestration.

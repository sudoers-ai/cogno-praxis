# cogno-praxis

**The Cogno business verticals, as standalone MCP servers.**

πρᾶξις = *action / practice* — the **product layer** on top of the Cogno OSS
substrate. Each vertical is an **independent FastMCP server** the host orchestrates
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
| **secretary** | the reception / scheduling entry point for any client | `list_schedulable_hosts`, `check_availability`, `book_appointment`, `list_appointments`, `cancel_appointment` |

More verticals (bookkeeper, restaurant, veterinary, …) follow the same shape.

## Run a vertical

```bash
pip install cogno-praxis            # pulls the mcp SDK
python -m cogno_praxis.secretary.server      # serves over stdio
```

The host connects to it with cogno-mcp:

```python
import sys
from cogno_mcp import MCPDispatcher, stdio_session

async with stdio_session(sys.executable, args=["-m", "cogno_praxis.secretary.server"]) as s:
    dispatcher = await MCPDispatcher.create(s)
    # bind to the SECRETARY persona + run the pipeline:
    await pipe.run_turn(ctx, cfg, dispatcher=dispatcher)     # cogno-soma
```

Tool **annotations** (`readOnlyHint` / `destructiveHint`) flow through cogno-mcp into
the EGO's read-only mask + confirmation gate — e.g. `cancel_appointment` is destructive,
so the EGO holds it for confirmation.

## Anatomy of a vertical (`secretary`)

- `store.py` — domain types (`Host`, `Appointment`) + an `AppointmentStore` **port**
  (Protocol) with an in-memory default. Appointments are structured domain data, not
  conversation memory, so the vertical owns its store (host plugs a real DB adapter);
  `cogno-engram` stays for episodic/KG memory.
- `service.py` — pure reception logic (book / cancel / availability) over the store.
- `server.py` — the thin FastMCP wrapper exposing the service as annotated tools.
- `persona/` — the SECRETARY persona prompt slots (system / scope / limits / voice),
  loaded by the host via `cogno-persona`.

## Development

```bash
pip install -e ".[dev]"
pytest tests/unit -q            # service + server (in-process), no network
pytest tests/integration -q     # secretary server over stdio via cogno-mcp (the real loop)
ruff check cogno_praxis tests && mypy cogno_praxis
python examples/host_min.py     # spawn the server + run a reception flow
```

Apache-2.0.

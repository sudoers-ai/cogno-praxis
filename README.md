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
| **scheduler** | the agenda capability — ships the **SECRETARY** persona, the universal reception/scheduling front door for any client | `list_schedulable_hosts`, `check_availability`, `book_appointment`, `list_appointments`, `update_appointment_status`, `cancel_appointment` |
| **bookkeeper** | the financial capability — ships the **BOOKKEEPER** persona (parent SaaS ANALYST): records income/expenses, tracks clients, produces summaries. See [`docs/BOOKKEEPER.md`](docs/BOOKKEEPER.md) | `add_income`, `add_outcome`, `get_summary`, `list_clients`, `search`, `remove_by_search`, `get_usage`, `help` |

More verticals (restaurant, veterinary, …) follow the same shape.

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
ruff check cogno_praxis tests && mypy cogno_praxis
python examples/host_min.py     # spawn the server + run a reception flow
```

Apache-2.0.

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
- **WARNING / INFO / DEBUG** — none from cogno-praxis itself yet. The `mcp` SDK does
  its own logging under the `mcp` namespace (FastMCP's stdio server prints request
  lines); configure/redirect it separately.

## What gets logged
- `cogno_praxis.*` — nothing of its own. Outcomes travel as tool return values /
  raised `SchedulerError`, not logs.

Client names, appointment details and notes are domain data — **not** logged by
cogno-praxis. Metering of tool calls is the host's job (`cogno-meter`).

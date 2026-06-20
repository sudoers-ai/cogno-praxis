"""cogno-praxis — the Cogno business verticals as standalone MCP servers.

The product layer (πρᾶξις = action/practice): each vertical is an independent
FastMCP server the host orchestrates via cogno-mcp. Verticals own their domain logic
+ data behind their own store ports (infra-agnostic); the host stays the thin
assembler (persona, pipeline, dispatcher composition, RBAC, orchestration rules).

First vertical: ``scheduler`` — the agenda capability, shipping the **SECRETARY**
persona (the universal reception/scheduling front door for any client).
"""

__version__ = "0.1.0"

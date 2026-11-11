"""cogno-praxis — the Cogno business verticals as standalone MCP servers.

The product layer (πρᾶξις = action/practice): each vertical is an independent
FastMCP server the host orchestrates via cogno-mcp. Verticals own their domain logic
+ data behind their own store ports (infra-agnostic); the host stays the thin
assembler (persona, pipeline, dispatcher composition, RBAC, orchestration rules).

First vertical: ``scheduler`` — the agenda capability, shipping the **SECRETARY**
persona (the universal reception/scheduling front door for any client).
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

# Read the version from the installed distribution so it has ONE source (pyproject) and can
# never drift from it — the hand-pinned string did (it sat at 0.1.2 while pyproject moved on).
try:
    __version__ = _dist_version("cogno-praxis")
except PackageNotFoundError:  # source tree without an installed dist (e.g. vendored checkout)
    __version__ = "0.0.0"

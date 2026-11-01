"""The ``admin`` vertical as a FastMCP server: two READ-ONLY tools over the package's verticals.

A thin MCP wrapper over :class:`AdminService`. It ships the **NEO** persona (``prompts/``): an
administrator persona that analyses the business verticals and proposes improvements to their
skills. Everything NEO may do through this server is READ — both tools are annotated
``readOnlyHint=True``, so the EGO's read-only mask never hides them and no gate holds them, and
neither tool writes, opens a connection, reads a database or reads the environment. Requesting a
change, running it and merging it are not this vertical's (``docs/ADMIN.md``).

The tool surface of the other verticals is read STATICALLY from their ``server.py`` (see
``service.py``): building their FastMCP objects would import them, and importing the bookkeeper's
server opens Postgres when its DSN is in the environment.

``build_server(service)`` is the only injection seam. There is no module-level ``mcp`` (the
scheduler's rule: a server is built only by its caller or under ``__main__``).

Run standalone (stdio):  ``python -m cogno_praxis.admin.server``
"""

from __future__ import annotations

import json
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cogno_praxis.admin.service import AdminError, AdminService


def _json(value: Any) -> str:
    # Deterministic: the same tree answers the same bytes. Non-ASCII stays as written (the
    # prompts are partly Portuguese) so the model reads «ç», not «ç».
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_server(service: Optional[AdminService] = None, *, name: str = "cogno-admin") -> FastMCP:
    """Build a FastMCP server bound to an :class:`AdminService` (inject one over another tree in
    tests)."""
    svc = service or AdminService()
    mcp = FastMCP(name)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_verticals() -> str:
        """List the business verticals of this package, read from its files. For each, as JSON:
        its id; is_self (true only for this admin vertical — NEO's own, never a target of a
        proposal); whether it has a server and a `python -m` entry; whether it ships prompts and
        which slots (system, scope, limits, voice); and every tool its server registers, with its
        annotations and two flags read from them: read_only (readOnlyHint=true) and destructive
        (destructiveHint=true, which the host holds for confirmation). Changes nothing."""
        return _json(svc.list_verticals())

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_vertical_config(vertical: str) -> str:
        """Read ONE vertical's configuration, as JSON: the full text of each prompt slot it ships
        (as written in the package, host placeholders such as {tenant_name} left literal), and
        its tool surface — each tool's name, description, input schema and annotations. Pass a
        vertical id exactly as list_verticals returns it. Changes nothing."""
        try:
            return _json(svc.get_vertical_config(vertical))
        except AdminError as exc:
            # Recoverable: the text names the known ids, so the model can retry with one of them.
            return f"ERROR: {exc}"

    return mcp


if __name__ == "__main__":
    build_server().run()

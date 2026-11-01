"""Integration: drive the admin server through cogno-mcp's MCPDispatcher, over stdio.

The real loop a host would run: spawn the admin FastMCP server as a subprocess, wrap it with
cogno-mcp's ``MCPDispatcher``, and check what the EGO would see. That is two tools, both
read-only by policy (never masked, never held), and answers that are the package's own files.
The child's environment carries no ``COGNO_*`` / ``PG*`` variable. No network, no database.
"""

import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp SDK not installed")
pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")

from cogno_mcp import MCPDispatcher, stdio_session  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
SERVER = str(_ROOT / "cogno_praxis" / "admin" / "server.py")
# Point the child at THIS checkout (the same block, for the same reason, as the scheduler's).
_ENV = {k: v for k, v in os.environ.items() if not k.startswith(("COGNO", "PG"))}
_ENV["PYTHONPATH"] = os.pathsep.join([str(_ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(
    os.pathsep)


@pytest.mark.asyncio
async def test_admin_loop_over_mcp():
    async with stdio_session(sys.executable, args=[SERVER], env=_ENV) as session:
        disp = await MCPDispatcher.create(session)

        names = [s["function"]["name"] for s in disp.tools_schema()]
        assert sorted(names) == ["get_vertical_config", "list_verticals"]
        for name in names:
            assert disp.is_mutating(name) is False, name
            assert disp.requires_confirmation(name) is False, name

        listed = await disp.execute("list_verticals", {})
        assert listed.ok and listed.side_effect is False
        rows = {r["id"]: r for r in json.loads(listed.output)}
        assert {"admin", "scheduler", "bookkeeper"} <= set(rows)
        assert rows["admin"]["is_self"] is True

        cfg = await disp.execute("get_vertical_config", {"vertical": "scheduler"})
        assert cfg.ok
        scope = (_ROOT / "cogno_praxis" / "scheduler" / "prompts" / "scope.txt").read_text(
            encoding="utf-8")
        assert json.loads(cfg.output)["prompts"]["scope"] == scope

        refused = await disp.execute("get_vertical_config", {"vertical": "../scheduler"})
        assert refused.output.startswith("ERROR: Unknown vertical '../scheduler'.")

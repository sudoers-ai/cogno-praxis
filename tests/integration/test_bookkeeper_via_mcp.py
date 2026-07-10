"""Integration: drive the bookkeeper server through cogno-mcp's MCPDispatcher.

The real loop the host runs: spawn the bookkeeper FastMCP server over stdio, wrap it with
cogno-mcp's ``MCPDispatcher``, and exercise it as the EGO would — tools_schema, policy from the
server's annotations, and execute mapped to ToolResult. Requires the mcp SDK + cogno-mcp
(auto-skips otherwise); no network.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp SDK not installed")
pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")

from cogno_mcp import MCPDispatcher, stdio_session  # noqa: E402

SERVER = str(Path(__file__).resolve().parents[2] / "cogno_praxis" / "bookkeeper" / "server.py")


@pytest.mark.asyncio
async def test_bookkeeper_loop_over_mcp():
    async with stdio_session(sys.executable, args=[SERVER]) as session:
        disp = await MCPDispatcher.create(session)

        # the EGO sees the 8 financial tools
        names = {s["function"]["name"] for s in disp.tools_schema()}
        assert {"add_income", "add_outcome", "get_summary", "list_clients", "search",
                "remove_by_search", "get_usage", "help"} <= names

        # policy flows from the server's annotations through cogno-mcp
        assert disp.is_mutating("get_summary") is False
        assert disp.is_mutating("add_income") is True
        assert disp.requires_confirmation("remove_by_search") is True   # destructiveHint
        assert disp.requires_confirmation("add_income") is False        # prompt-driven confirm

        # record → ToolResult(ok=True, side_effect=True)
        rec = await disp.execute("add_income", {
            "description": "corte", "amount": "R$ 50,00", "identity_id": "emp-1", "client": "João"})
        assert rec.ok and "50" in rec.output
        assert rec.side_effect is True

        # summary reflects it (oversight sees the scope)
        summ = await disp.execute("get_summary", {"identity_id": "emp-1", "role": "ADMIN"})
        assert summ.ok and "50" in summ.output

        # remove it back
        rem = await disp.execute("remove_by_search", {"query": "corte", "identity_id": "emp-1"})
        assert rem.ok and "Removed" in rem.output

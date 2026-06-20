"""Integration: drive the SECRETARY server through cogno-mcp's MCPDispatcher.

This is the real loop the host runs: spawn the secretary FastMCP server over stdio,
wrap it with cogno-mcp's ``MCPDispatcher`` (the cogno-anima ToolDispatcher), and
exercise it exactly as the EGO would — tools_schema, policy from the server's
annotations, and execute (book → list → cancel) mapped to ToolResult. Requires the
mcp SDK + cogno-mcp (auto-skips otherwise); no network.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp SDK not installed")
pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")

from cogno_mcp import MCPDispatcher, stdio_session  # noqa: E402

SERVER = str(Path(__file__).resolve().parents[2] / "cogno_praxis" / "secretary" / "server.py")


@pytest.mark.asyncio
async def test_secretary_loop_over_mcp():
    async with stdio_session(sys.executable, args=[SERVER]) as session:
        disp = await MCPDispatcher.create(session)

        # the EGO sees the reception tools as ordinary tools
        names = {s["function"]["name"] for s in disp.tools_schema()}
        assert {"list_schedulable_hosts", "check_availability", "book_appointment",
                "list_appointments", "cancel_appointment"} <= names

        # policy flows from the server's annotations through cogno-mcp
        assert disp.is_mutating("check_availability") is False
        assert disp.is_mutating("book_appointment") is True
        assert disp.requires_confirmation("cancel_appointment") is True
        assert disp.requires_confirmation("book_appointment") is False

        # the standalone server is seeded with demo hosts
        hosts = await disp.execute("list_schedulable_hosts", {})
        assert hosts.ok and "dr_silva" in hosts.output

        # book → ToolResult(ok=True, side_effect=True)
        booked = await disp.execute("book_appointment", {
            "host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"})
        assert booked.ok and "Booked" in booked.output
        assert booked.side_effect is True

        # a double-book is a recoverable tool error
        clash = await disp.execute("book_appointment", {
            "host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Bob"})
        assert clash.ok is False
        assert "already booked" in (clash.error or "")

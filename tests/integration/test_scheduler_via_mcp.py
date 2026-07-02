"""Integration: drive the scheduler server through cogno-mcp's MCPDispatcher.

This is the real loop the host runs: spawn the scheduler FastMCP server over stdio,
wrap it with cogno-mcp's ``MCPDispatcher`` (the cogno-anima ToolDispatcher), and
exercise it exactly as the EGO would — tools_schema, policy from the server's
annotations, and execute (book → list → cancel) mapped to ToolResult. Requires the
mcp SDK + cogno-mcp (auto-skips otherwise); no network.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp SDK not installed")
pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")

from cogno_mcp import MCPDispatcher, stdio_session  # noqa: E402

SERVER = str(Path(__file__).resolve().parents[2] / "cogno_praxis" / "scheduler" / "server.py")


def _future_weekday(days: int = 30) -> str:
    """A date safely in the future, rolled forward to a weekday — the demo server uses the real
    clock and has no Saturday/Sunday hours, so a fixed +N days could land on a weekend and the
    booking would (correctly) be refused, failing this test on those calendar days."""
    d = date.today() + timedelta(days=days)
    while d.weekday() >= 5:  # Sat=5, Sun=6 → advance to Monday
        d += timedelta(days=1)
    return d.isoformat()


# Demo server uses the real clock; pick a weekday safely in the future ("from tomorrow on").
FUTURE = _future_weekday()


@pytest.mark.asyncio
async def test_scheduler_loop_over_mcp():
    async with stdio_session(sys.executable, args=[SERVER]) as session:
        disp = await MCPDispatcher.create(session)

        # the EGO sees the scheduling tools as ordinary tools
        names = {s["function"]["name"] for s in disp.tools_schema()}
        assert {"list_schedulable_hosts", "check_availability", "book_appointment",
                "list_appointments", "update_appointment_status",
                "cancel_appointment"} <= names

        # policy flows from the server's annotations through cogno-mcp
        assert disp.is_mutating("check_availability") is False
        assert disp.is_mutating("book_appointment") is True
        assert disp.requires_confirmation("cancel_appointment") is True
        assert disp.requires_confirmation("book_appointment") is False

        # the standalone server is seeded with demo hosts
        hosts = await disp.execute("list_schedulable_hosts", {})
        assert hosts.ok and "dr_silva" in hosts.output

        # book → ToolResult(ok=True, side_effect=True). dr_souza has auto_confirm=False,
        # so the new appointment stays PENDING until the professional accepts it.
        booked = await disp.execute("book_appointment", {
            "host_id": "dr_souza", "date": FUTURE, "time": "09:00", "with_name": "Ana"})
        assert booked.ok and "Booked" in booked.output and "PENDING" in booked.output
        assert booked.side_effect is True

        # a double-book is a recoverable tool error
        clash = await disp.execute("book_appointment", {
            "host_id": "dr_souza", "date": FUTURE, "time": "09:00", "with_name": "Bob"})
        assert clash.ok is False
        assert "already booked" in (clash.error or "")

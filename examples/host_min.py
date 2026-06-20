"""Minimal host wiring for the SECRETARY vertical.

Spawns the secretary FastMCP server over stdio, wraps it with cogno-mcp's
MCPDispatcher (the cogno-anima ToolDispatcher), and runs a small reception flow —
the same dispatcher the host hands to cogno-soma's EGO (bound to the SECRETARY
persona in cogno_praxis/secretary/persona/).

    python examples/host_min.py        # needs: pip install cogno-mcp (+ the cogno chain)
"""

import asyncio
import sys
from pathlib import Path

SERVER = str(Path(__file__).resolve().parents[1] / "cogno_praxis" / "secretary" / "server.py")


async def main():
    try:
        from cogno_mcp import MCPDispatcher, stdio_session
    except ImportError:
        print("install cogno-mcp to run this example: pip install cogno-mcp")
        return

    async with stdio_session(sys.executable, args=[SERVER]) as session:
        disp = await MCPDispatcher.create(session)

        print("reception tools:", [s["function"]["name"] for s in disp.tools_schema()])
        print("cancel is destructive (EGO will confirm):", disp.requires_confirmation("cancel_appointment"))

        hosts = await disp.execute("list_schedulable_hosts", {})
        print("hosts ->", hosts.output.replace("\n", " | "))
        booked = await disp.execute("book_appointment", {
            "host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"})
        print("book ->", booked.output, "| side_effect:", booked.side_effect)
        listed = await disp.execute("list_appointments", {"with_name": "Ana"})
        print("list ->", listed.output)

        # the host would instead:
        #   dispatcher = CompositeDispatcher([secretary_mcp, cortex_skills, native])
        #   await pipe.run_turn(ctx, cfg, dispatcher=dispatcher)   # cogno-soma + SECRETARY persona


if __name__ == "__main__":
    asyncio.run(main())

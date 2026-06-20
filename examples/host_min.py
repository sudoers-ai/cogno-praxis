"""Minimal host wiring for the scheduler vertical (SECRETARY persona).

Spawns the scheduler FastMCP server over stdio, wraps it with cogno-mcp's
MCPDispatcher (the cogno-anima ToolDispatcher), and runs a small reception flow —
the same dispatcher the host hands to cogno-soma's EGO (bound to the SECRETARY
persona, whose prompt slots live in cogno_praxis/scheduler/prompts/).

    python examples/host_min.py        # needs: pip install cogno-mcp (+ the cogno chain)
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

SERVER = str(Path(__file__).resolve().parents[1] / "cogno_praxis" / "scheduler" / "server.py")
FUTURE = (date.today() + timedelta(days=30)).isoformat()   # "from tomorrow on"


async def main():
    try:
        from cogno_mcp import MCPDispatcher, stdio_session
    except ImportError:
        print("install cogno-mcp to run this example: pip install cogno-mcp")
        return

    async with stdio_session(sys.executable, args=[SERVER]) as session:
        disp = await MCPDispatcher.create(session)

        print("scheduling tools:", [s["function"]["name"] for s in disp.tools_schema()])
        print("cancel is destructive (EGO will confirm):", disp.requires_confirmation("cancel_appointment"))

        hosts = await disp.execute("list_schedulable_hosts", {})
        print("hosts ->", hosts.output.replace("\n", " | "))
        booked = await disp.execute("book_appointment", {
            "host_id": "dr_silva", "date": FUTURE, "time": "09:00", "with_name": "Ana"})
        print("book ->", booked.output, "| side_effect:", booked.side_effect)
        listed = await disp.execute("list_appointments", {"with_name": "Ana"})
        print("list ->", listed.output)

        # the host would instead:
        #   dispatcher = CompositeDispatcher([scheduler_mcp, cortex_skills, native])
        #   await pipe.run_turn(ctx, cfg, dispatcher=dispatcher)   # cogno-soma + SECRETARY persona


if __name__ == "__main__":
    asyncio.run(main())

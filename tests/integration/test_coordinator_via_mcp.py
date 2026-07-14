"""Integration: drive the coordinator server through cogno-mcp's MCPDispatcher.

The real loop the host runs: spawn the coordinator FastMCP server over stdio, wrap it with
cogno-mcp's ``MCPDispatcher``, and exercise it as the EGO would — tools_schema, policy from the
server's annotations (confirm_swap is destructive → confirmation gate), and execute → ToolResult.
Uses the in-memory demo store (no Google), so it runs in CI; no network.
"""

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp SDK not installed")
pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")

from cogno_mcp import MCPDispatcher, stdio_session  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]                    # the cogno_praxis package root
SERVER = str(_ROOT / "cogno_praxis" / "coordinator" / "server.py")
# Point the spawned subprocess at THIS checkout so it imports our coordinator even when an
# editable install of cogno_praxis (without it) would otherwise shadow it (worktree/CI parity).
_ENV = {**os.environ, "PYTHONPATH": os.pathsep.join(
    [str(_ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}


@pytest.mark.asyncio
async def test_coordinator_loop_over_mcp():
    async with stdio_session(sys.executable, args=[SERVER], env=_ENV) as session:
        disp = await MCPDispatcher.create(session)

        names = {s["function"]["name"] for s in disp.tools_schema()}
        assert {"get_professor_schedule", "check_deadlines", "get_weekly_briefing",
                "check_ibope_status", "find_replacement_slot", "confirm_swap"} <= names

        # policy from annotations: reads are non-mutating; confirm_swap is destructive → gated
        assert disp.is_mutating("get_professor_schedule") is False
        assert disp.is_mutating("confirm_swap") is True
        assert disp.requires_confirmation("confirm_swap") is True

        # a read tool executes cleanly (empty demo store → the honest "no classes" answer)
        res = await disp.execute("get_professor_schedule", {"role": "SUPERVISOR",
                                                            "identity_label": "Sofia"})
        assert res.ok and isinstance(res.output, str)

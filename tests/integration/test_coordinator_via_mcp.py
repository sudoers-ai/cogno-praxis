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


@pytest.mark.asyncio
async def test_the_calendar_export_is_gated_and_a_refusal_is_never_stamped_as_a_write():
    """The two facts about ``send_schedule_to_calendar`` that only the real bridge can show.

    **Gated.** It carries ``destructiveHint``, so cogno-mcp reports ``requires_confirmation`` and
    the EGO's gate B holds the call until the user says yes. An e-mail cannot be unsent, which
    is why it is here and not on the "undoable" list.

    **A refusal costs nothing.** ``MCPDispatcher.execute`` stamps ``side_effect`` from the tool's
    per-NAME mutating annotation on any call that RETURNS — so a tool that answered "there is no
    e-mail configured" with a polite sentence would have the turn recorded as a write that never
    happened, in the very accounting (``committed_this_turn``) the house uses to decide whether a
    promise was kept. The tool RAISES instead, which arrives as ``isError`` → ``ok=False`` →
    ``side_effect=False``. Measured here rather than reasoned about, because the whole chain
    (FastMCP → CallToolResult.isError → MCPToolResult) lives outside this repository.

    The demo store the subprocess builds is empty, so the path exercised is the honest "no
    upcoming classes, nothing to put in a calendar" one. That is the same contract: every branch
    that did not send raises, and this asserts the branch a spawned demo server can reach.
    """
    env = {**_ENV, "SMTP_HOST": "", "COGNO_COORDINATOR_SMTP": ""}
    async with stdio_session(sys.executable, args=[SERVER], env=env) as session:
        disp = await MCPDispatcher.create(session)

        names = {s["function"]["name"] for s in disp.tools_schema()}
        assert "send_schedule_to_calendar" in names
        assert disp.is_mutating("send_schedule_to_calendar") is True
        assert disp.requires_confirmation("send_schedule_to_calendar") is True

        res = await disp.execute("send_schedule_to_calendar",
                                 {"role": "EMPLOYEE", "identity_label": "Ana"})
        assert res.ok is False
        assert res.side_effect is False, (
            "a call that mailed nothing must not be recorded as a write — that record is what "
            "decides whether the turn kept a promise")
        assert "Nothing was sent" in (res.error or "")

"""Integration: drive the company server through cogno-mcp's MCPDispatcher.

The real loop the host runs: spawn the company FastMCP server over stdio, wrap it with
cogno-mcp's ``MCPDispatcher``, and exercise it as the EGO would. Requires the mcp SDK +
cogno-mcp (auto-skips otherwise); no network, no database.

**This file is the half the unit suite cannot perform.** ``test_company_server.py`` asserts the
server RAISES on a refusal; only the real dispatcher can say what a raise then BECOMES. It
matters because the two outcomes are one boolean apart and the wrong one is silent: a refusal
arriving as ``ok=True, side_effect=True`` is a registration that wrote nothing being counted as
a write by ``committed_this_turn`` and waved past the host's ``if not ex.ok`` focus guard.
"""

import ast
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp SDK not installed")
pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")

from cogno_mcp import MCPDispatcher, stdio_session  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
SERVER = str(_ROOT / "cogno_praxis" / "company" / "server.py")
# Point the spawned subprocess at THIS checkout so it imports our vertical even when an
# editable install of cogno_praxis would otherwise shadow it (worktree/CI parity). Without it
# this file measures whichever checkout happens to be installed — a green that belongs to
# somebody else's tree. Same block, same reason, as test_bookkeeper_via_mcp.py.
_ENV = {**os.environ, "PYTHONPATH": os.pathsep.join(
    [str(_ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}

_CNPJ_OK = "11.222.333/0001-81"
_CNPJ_BAD = "11.222.333/0001-99"


@pytest.mark.asyncio
async def test_company_registration_over_mcp():
    async with stdio_session(sys.executable, args=[SERVER], env=_ENV) as session:
        disp = await MCPDispatcher.create(session)

        assert {s["function"]["name"] for s in disp.tools_schema()} == {"company_registration"}

        # policy flows from the server's annotations through cogno-mcp: this is WHERE the tool
        # is classified as a write. The host then wraps the module source in
        # `WriteConfirmingDispatcher`, which holds every mutating call that is not exempt.
        assert disp.is_mutating("company_registration") is True
        assert disp.requires_confirmation("company_registration") is False   # no destructiveHint

        ok = await disp.execute("company_registration",
                                {"company_name": "Padaria Sol Nascente", "cnpj": _CNPJ_OK,
                                 "identity_id": "u1"})
        assert ok.ok is True and ok.side_effect is True
        payload = ast.literal_eval(ok.output)
        assert payload["company_id"] == "padaria-sol-nascente"
        assert payload["company_name"] == "Padaria Sol Nascente"
        assert payload["cnpj"] == "11222333000181"


@pytest.mark.asyncio
async def test_a_refusal_arrives_as_ok_False_and_NOT_as_a_side_effect():
    """The measurement that fixed this vertical's error convention (2026-09-06).

    Its sibling verticals answer a refusal with ``return "ERROR: ..."``. Through this exact
    chain that is a NORMAL return — no ``isError`` — so cogno-mcp reports ``ok=True`` and, for a
    tool annotated ``readOnlyHint=False``, ``side_effect=True``. Here the tool raises instead,
    and this asserts what the raise becomes.
    """
    async with stdio_session(sys.executable, args=[SERVER], env=_ENV) as session:
        disp = await MCPDispatcher.create(session)
        bad = await disp.execute("company_registration",
                                 {"company_name": "Acme", "cnpj": _CNPJ_BAD})
        assert bad.ok is False
        assert bad.side_effect is False, (
            "a refused registration recorded as a write is what `committed_this_turn` counts")
        # the reason still reaches the model, naming the field it must fix
        assert "cnpj" in (bad.error or "")
        assert bad.output == ""


@pytest.mark.asyncio
async def test_the_host_focus_contract_end_to_end():
    """The TWIN for the move: the host's "which company are we talking about" still works.

    ``cogno_host.company_focus`` is not importable here (the host is private and this library
    must not depend on it), so its two rules are performed in its own terms: match the tool
    NAME, require ``ok``, then ``ast.literal_eval`` the answer and read ``company_id`` out. A
    rename or a re-shaped answer fails NOTHING in either repo — it just stops moving the focus,
    and the next turn plans for the wrong company.
    """
    async with stdio_session(sys.executable, args=[SERVER], env=_ENV) as session:
        disp = await MCPDispatcher.create(session)

        def focus(name, result):                      # company_focus's rule, in its own terms
            if name not in ("company_registration",) or not result.ok:
                return None
            text = str(result.output or "").strip()
            if not text.startswith("{"):
                return None
            try:
                data = ast.literal_eval(text)
            except (ValueError, SyntaxError, MemoryError, RecursionError):
                return None
            cid = str((data or {}).get("company_id") or "").strip()
            return {"company_id": cid, "name": str(data.get("company_name") or "")} if cid else None

        good = await disp.execute("company_registration",
                                  {"company_name": "Padaria Sol Nascente"})
        assert focus("company_registration", good) == {
            "company_id": "padaria-sol-nascente", "name": "Padaria Sol Nascente"}

        # a refused write does not move the focus: there is no new company
        bad = await disp.execute("company_registration",
                                 {"company_name": "Acme", "cnpj": _CNPJ_BAD})
        assert focus("company_registration", bad) is None

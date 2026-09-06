"""Integration: drive the bookkeeper server through cogno-mcp's MCPDispatcher.

The real loop the host runs: spawn the bookkeeper FastMCP server over stdio, wrap it with
cogno-mcp's ``MCPDispatcher``, and exercise it as the EGO would — tools_schema, policy from the
server's annotations, and execute mapped to ToolResult. Requires the mcp SDK + cogno-mcp
(auto-skips otherwise); no network.
"""

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp SDK not installed")
pytest.importorskip("cogno_mcp", reason="cogno-mcp not installed")

from cogno_mcp import MCPDispatcher, stdio_session  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
SERVER = str(_ROOT / "cogno_praxis" / "bookkeeper" / "server.py")
# Point the spawned subprocess at THIS checkout so it imports our bookkeeper even when an
# editable install of cogno_praxis would otherwise shadow it (worktree/CI parity). Without it
# this file measures whichever checkout happens to be installed — a green that belongs to
# somebody else's tree. Same block, same reason, as test_coordinator_via_mcp.py.
_ENV = {**os.environ, "PYTHONPATH": os.pathsep.join(
    [str(_ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}


@pytest.mark.asyncio
async def test_bookkeeper_loop_over_mcp():
    async with stdio_session(sys.executable, args=[SERVER], env=_ENV) as session:
        disp = await MCPDispatcher.create(session)

        # the EGO sees the 8 financial tools
        names = {s["function"]["name"] for s in disp.tools_schema()}
        assert {"add_income", "add_outcome", "get_summary", "list_clients", "search",
                "remove_by_search", "get_usage", "help"} <= names

        # policy flows from the server's annotations through cogno-mcp
        assert disp.is_mutating("get_summary") is False
        assert disp.is_mutating("add_income") is True
        # remove_by_search is mutating and NOT gate-B-held: it raises gate C instead, per CALL,
        # after reading. See tests/integration/test_o_portao_C_dispara_sobre_a_cadeia.py.
        assert disp.is_mutating("remove_by_search") is True
        assert disp.requires_confirmation("remove_by_search") is False
        assert disp.requires_confirmation("add_income") is False        # prompt-driven confirm

        # record → ToolResult(ok=True, side_effect=True)
        rec = await disp.execute("add_income", {
            "description": "corte", "amount": "R$ 50,00", "identity_id": "emp-1", "client": "João"})
        assert rec.ok and "50" in rec.output
        assert rec.side_effect is True

        # summary reflects it (oversight sees the scope)
        summ = await disp.execute("get_summary", {"identity_id": "emp-1", "role": "ADMIN"})
        assert summ.ok and "50" in summ.output

        # remove it back — TWO calls: the first READS and proposes the exact row (gate C's
        # grounded question), the second commits the row it named.
        proposed = await disp.execute("remove_by_search", {"query": "corte",
                                                           "identity_id": "emp-1"})
        assert proposed.ok and "NOT REMOVED" in proposed.output
        assert "corte" in proposed.output and "50" in proposed.output
        # Still there — a proposal writes nothing.
        assert "50" in (await disp.execute("get_summary", {"identity_id": "emp-1",
                                                           "role": "ADMIN"})).output
        tx_id = proposed.output.split("confirm_tx_id='")[1].split("'")[0]
        rem = await disp.execute("remove_by_search", {"query": "corte", "identity_id": "emp-1",
                                                      "confirm_tx_id": tx_id})
        assert rem.ok and "Removed" in rem.output

        # THE GAP, CLOSED on 2026-09-03 — and it took both halves, in two repositories.
        #
        # It was written here as an assertion of absence: cogno-mcp carried no
        # `needs_confirmation` at all (`grep -rn` in that repo: zero hits), so the EGO's third
        # gate was unreachable over this bridge and the proposal arrived as ordinary tool text.
        # cogno-mcp#12 landed the transport (a content block's `_meta`, the one placement the
        # Python SDK's server side can actually fill), and this vertical now SETS that key —
        # which is the half a bridge cannot supply, because only the tool knows it did not
        # commit.
        #
        # The flag had one more precondition that was invisible from here: the annotation.
        # `destructiveHint` made gate B hold the tool by NAME, so it never ran and the question
        # was never asked. Dropping it is what lets this line be True at all.
        assert proposed.needs_confirmation is True
        # and the tool NAMES what it needs in order to commit — the host holds the consent,
        # never the argument name
        assert proposed.confirm_arguments == {"confirm_tx_id": tx_id}
        # a PROPOSAL is not a write: `side_effect` is per CALL, and stamping it here is how a
        # turn comes to declare a commit that never happened
        assert proposed.side_effect is False


async def test_the_meta_keys_are_the_ones_cogno_mcp_actually_reads():
    """Um contrato DUPLICADO precisa de um pino nos dois sentidos.

    `server.py` escreve estas chaves à mão em vez de as importar — esta vertical não depende da
    ponte em runtime, e uma skill que só soubesse falar o portão C importando o cliente dele
    teria a seta da dependência ao contrário. O preço é que uma renomeação de qualquer dos lados
    passaria em silêncio, e o silêncio é a direcção que interessa: uma chave que ninguém lê faz
    a proposta parecer um commit.
    """
    from cogno_mcp import META_CONFIRM_ARGUMENTS, META_NEEDS_CONFIRMATION

    from cogno_praxis.bookkeeper.server import (_META_CONFIRM_ARGUMENTS,
                                                _META_NEEDS_CONFIRMATION)

    assert _META_NEEDS_CONFIRMATION == META_NEEDS_CONFIRMATION
    assert _META_CONFIRM_ARGUMENTS == META_CONFIRM_ARGUMENTS


@pytest.mark.asyncio
async def test_a_write_that_wrote_nothing_is_not_stamped_as_a_write():
    """THE MEASUREMENT the unit twins can only approximate: the ``side_effect`` BIT itself.

    Everything else about this defect is reasoning about ``dispatcher.execute``; this is the
    only place in the repo that actually reads what the bridge stamped. The unit tests prove
    the tool RAISES — this proves a raise really does arrive as ``ok=False`` +
    ``side_effect=False``, i.e. that the turn stops declaring a write it did not make.

    Mirrors ``test_companies_via_mcp.py``'s refusal assertion, on the two shapes cogno-praxis
    was still emitting: a search that matched nothing, and a rejected recording.
    """
    async with stdio_session(sys.executable, args=[SERVER], env=_ENV) as session:
        disp = await MCPDispatcher.create(session)

        # (1) the measured production turn: remove_by_search matched nothing
        nada = await disp.execute("remove_by_search", {"query": "no-such-entry",
                                                       "identity_id": "emp-1"})
        assert nada.ok is False
        assert nada.side_effect is False, (
            "a removal that deleted zero rows recorded as a write is what committed_this_turn "
            "counts — and a false TRUE there switches the anti-fabrication net OFF")
        assert "nothing removed" in (nada.error or "")     # the reason still reaches the model
        assert nada.output == ""

        # (2) a rejected recording — the "ERROR: ..." string shape
        mau = await disp.execute("add_income", {"description": "consulta",
                                                "amount": "abacaxi", "identity_id": "emp-1"})
        assert mau.ok is False
        assert mau.side_effect is False
        assert mau.output == ""

        # (3) THE TWIN — over-tightening would be just as bad: a real write must still stamp.
        bom = await disp.execute("add_income", {"description": "consulta", "amount": "500",
                                                "identity_id": "emp-1"})
        assert bom.ok is True and bom.side_effect is True

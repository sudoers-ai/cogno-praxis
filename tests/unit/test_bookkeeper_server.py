"""Unit tests for the bookkeeper FastMCP server wrapper (tools + annotations), in-process."""

from datetime import date

import pytest

from cogno_praxis.bookkeeper.server import build_server
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore

_TODAY = date(2026, 7, 10)


def _server():
    svc = BookkeeperService(InMemoryBookkeeperStore(), today=lambda: _TODAY)
    return build_server(svc)


def _text(call_result):
    # FastMCP returns ``(content_blocks, structured)`` for a tool that HAS an outputSchema and a
    # bare block list for one that does not. ``remove_by_search`` is the second kind on purpose —
    # it returns a ``TextContent`` so its proposal can carry the gate-C ``_meta``, and FastMCP
    # builds no schema without a return annotation. Indexing ``[0]`` blindly would take the first
    # BLOCK, iterate a pydantic model into (field, value) pairs, match no ``type == "text"`` and
    # join nothing — an empty string where the assertion wanted prose.
    content = call_result[0] if isinstance(call_result, tuple) else call_result
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


async def test_tools_and_annotations():
    tools = await _server().list_tools()
    ann = {t.name: t.annotations for t in tools}
    # 2026-08-12: ``math`` joined the vertical (exact arithmetic over figures the client
    # quotes — reajuste/markup/rateio). Read-only, so no mask and no confirmation gate.
    assert set(ann) == {"add_income", "add_outcome", "get_summary", "list_clients",
                        "search", "remove_by_search", "get_usage", "help", "math"}
    # reads are read-only; writes are not
    for ro in ("get_summary", "list_clients", "search", "get_usage", "help"):
        assert ann[ro].readOnlyHint is True
    for rw in ("add_income", "add_outcome", "remove_by_search"):
        assert ann[rw].readOnlyHint is False
    # NOT destructiveHint, and this line is the one a reviewer will stop on. It is not a
    # protection dropped, it is a protection MOVED: gate B holds by NAME and BEFORE the call, so
    # it pre-empts the grounded question gate C exists to ask — measured in
    # tests/integration/test_o_portao_C_dispara_sobre_a_cadeia.py, where the byte-identical twin
    # under the old annotation never runs at all. The write path stays unreachable without
    # ``confirm_tx_id``; test_tool_annotations.py performs that rather than asserting it.
    assert ann["remove_by_search"].destructiveHint is None


async def test_add_income_outcome_and_summary_flow():
    mcp = _server()
    inc = _text(await mcp.call_tool(
        "add_income", {"description": "corte", "amount": "R$ 50,00",
                       "identity_id": "emp-1", "client": "João"}))
    assert "Income recorded" in inc and "João" in inc and "R$ 50.00" in inc and "2026-07-10" in inc

    out = _text(await mcp.call_tool(
        "add_outcome", {"description": "luz", "amount": "80", "identity_id": "emp-1"}))
    assert "Expense recorded" in out and "R$ 80.00" in out

    summary = _text(await mcp.call_tool("get_summary", {"identity_id": "emp-1", "role": "EMPLOYEE"}))
    assert "R$ 50.00" in summary and "R$ 80.00" in summary and "R$ -30.00" in summary  # net


async def test_list_clients_and_search():
    mcp = _server()
    await mcp.call_tool("add_income", {"description": "corte", "amount": "50",
                                       "identity_id": "emp-1", "client": "João"})
    assert "João" in _text(await mcp.call_tool("list_clients", {}))
    hit = _text(await mcp.call_tool("search", {"query": "corte", "identity_id": "emp-1",
                                               "role": "EMPLOYEE"}))
    assert "corte" in hit and "income" in hit


async def test_search_no_match_message():
    mcp = _server()
    out = _text(await mcp.call_tool("search", {"query": "inexistente", "identity_id": "emp-1",
                                               "role": "EMPLOYEE"}))
    assert "No transactions match" in out


async def test_remove_by_search_destructive():
    mcp = _server()
    await mcp.call_tool("add_outcome", {"description": "internet", "amount": "100",
                                        "identity_id": "emp-1"})
    # step 1 PROPOSES and deletes nothing (the grounded question — see
    # tests/unit/test_a_removal_asks_with_what_it_read.py)
    proposed = _text(await mcp.call_tool("remove_by_search", {"query": "internet",
                                                              "identity_id": "emp-1"}))
    assert "NOT REMOVED" in proposed and "internet" in proposed
    tx_id = proposed.split("confirm_tx_id='")[1].split("'")[0]
    # step 2 commits the row that was proposed
    removed = _text(await mcp.call_tool("remove_by_search", {"query": "internet",
                                                             "identity_id": "emp-1",
                                                             "confirm_tx_id": tx_id}))
    assert "Removed" in removed and "internet" in removed
    # nothing left → the "nothing removed" branch, which RAISES (server.py: _REFUSALS_RAISE)
    # so the bridge cannot stamp a deletion of zero rows as a write.
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match="nothing removed"):
        await mcp.call_tool("remove_by_search", {"query": "internet", "identity_id": "emp-1"})


async def test_empty_state_and_static_notes():
    mcp = _server()
    assert "No clients recorded yet." in _text(await mcp.call_tool("list_clients", {}))
    assert _text(await mcp.call_tool("get_usage", {}))   # usage note is non-empty
    assert _text(await mcp.call_tool("help", {}))        # help/scope note is non-empty


def test_seeded_service_uses_env_clock_without_a_dsn(monkeypatch):
    """_seeded_service builds an in-memory service honoring COGNO_BOOKKEEPER_TODAY (no DSN)."""
    from cogno_praxis.bookkeeper.server import _seeded_service

    monkeypatch.delenv("COGNO_BOOKKEEPER_DSN", raising=False)
    monkeypatch.delenv("COGNO_PG_DSN", raising=False)
    monkeypatch.setenv("COGNO_BOOKKEEPER_TODAY", "2026-09-08")
    svc = _seeded_service()
    tx = svc.add_income("x", "10", "emp-1")
    assert tx.tx_date == "2026-09-08"

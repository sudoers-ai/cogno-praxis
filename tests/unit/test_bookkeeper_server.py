"""Unit tests for the bookkeeper FastMCP server wrapper (tools + annotations), in-process."""

from datetime import date

from cogno_praxis.bookkeeper.server import build_server
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore

_TODAY = date(2026, 7, 10)


def _server():
    svc = BookkeeperService(InMemoryBookkeeperStore(), today=lambda: _TODAY)
    return build_server(svc)


def _text(call_result):
    # FastMCP call_tool returns (content_blocks, structured)
    content = call_result[0]
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


async def test_tools_and_annotations():
    tools = await _server().list_tools()
    ann = {t.name: t.annotations for t in tools}
    assert set(ann) == {"add_income", "add_outcome", "get_summary", "list_clients",
                        "search", "remove_by_search", "get_usage", "help"}
    # reads are read-only; writes are not; remove is destructive (EGO gate B holds it)
    for ro in ("get_summary", "list_clients", "search", "get_usage", "help"):
        assert ann[ro].readOnlyHint is True
    for rw in ("add_income", "add_outcome", "remove_by_search"):
        assert ann[rw].readOnlyHint is False
    assert ann["remove_by_search"].destructiveHint is True


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
    removed = _text(await mcp.call_tool("remove_by_search", {"query": "internet",
                                                             "identity_id": "emp-1"}))
    assert "Removed" in removed and "internet" in removed
    # nothing left → the "nothing removed" branch
    again = _text(await mcp.call_tool("remove_by_search", {"query": "internet",
                                                           "identity_id": "emp-1"}))
    assert "nothing removed" in again


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

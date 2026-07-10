"""The ``bookkeeper`` (financial) vertical as a FastMCP server.

A thin MCP wrapper over :class:`BookkeeperService`. The host connects via ``cogno-mcp``
(``MCPDispatcher``), so the EGO sees these as ordinary tools. Tool ``annotations``
(readOnlyHint / destructiveHint) flow through cogno-mcp into the EGO's read-only mask +
confirmation gate — ``remove_by_search`` is destructive and the EGO holds it for confirmation.

``build_server(service)`` is the only injection seam (the host builds a service over its own
store adapter). The module-level ``mcp`` is an in-memory demo for standalone runs and tests.

Run the demo standalone (stdio):  ``python -m cogno_praxis.bookkeeper.server``
"""

from __future__ import annotations

import os
from datetime import date
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cogno_praxis.bookkeeper.engine import BookkeeperError
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import BookkeeperStore, InMemoryBookkeeperStore


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def build_server(service: Optional[BookkeeperService] = None, *,
                 name: str = "cogno-bookkeeper") -> FastMCP:
    """Build a FastMCP server bound to a service (inject a store-backed one in prod/tests)."""
    svc = service or BookkeeperService()
    mcp = FastMCP(name)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def add_income(description: str, amount: str, identity_id: str = "",
                   client: str = "", date: str = "") -> str:
        """Record an income (entrada). Confirm the summary with the user BEFORE calling this."""
        try:
            tx = svc.add_income(description, amount, identity_id, client_name=client, tx_date=date)
        except BookkeeperError as exc:
            return f"ERROR: {exc}"
        who = f" ({tx.client_name})" if tx.client_name else ""
        return f"Income recorded: {tx.description}{who} = {_brl(tx.amount)} on {tx.tx_date}."

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def add_outcome(description: str, amount: str, identity_id: str = "", date: str = "") -> str:
        """Record an expense (saída). Confirm the summary with the user BEFORE calling this."""
        try:
            tx = svc.add_outcome(description, amount, identity_id, tx_date=date)
        except BookkeeperError as exc:
            return f"ERROR: {exc}"
        return f"Expense recorded: {tx.description} = {_brl(tx.amount)} on {tx.tx_date}."

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_summary(identity_id: str = "", role: str = "", date_from: str = "",
                    date_to: str = "") -> str:
        """Financial summary — totals + entries, scoped to the caller's role."""
        s = svc.get_summary(identity_id, role, date_from=date_from, date_to=date_to)
        lines = [f"Income:  {_brl(s['total_income'])} ({s['income_count']} entries)",
                 f"Expense: {_brl(s['total_outcome'])} ({s['outcome_count']} entries)",
                 f"Net:     {_brl(s['net'])}"]
        for t in s["incomes"] + s["outcomes"]:
            tag = "+" if t["kind"] == "income" else "-"
            who = f" ({t['client']})" if t["client"] else ""
            lines.append(f"  {tag} {t['date']} {t['description']}{who}: {_brl(t['amount'])}")
        return "\n".join(lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_clients() -> str:
        """List known clients."""
        clients = svc.list_clients()
        if not clients:
            return "No clients recorded yet."
        return "\n".join(f"{c['client_id']}: {c['name']}" for c in clients)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def search(query: str, identity_id: str = "", role: str = "", date_from: str = "",
               date_to: str = "") -> str:
        """Search transactions by keyword (and optional date range)."""
        hits = svc.search(query, identity_id, role, date_from=date_from, date_to=date_to)
        if not hits:
            return f"No transactions match {query!r}."
        return "\n".join(f"{t['date']} [{t['kind']}] {t['description']}: {_brl(t['amount'])}"
                         for t in hits)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    def remove_by_search(query: str, identity_id: str = "") -> str:
        """Remove YOUR most recent transaction matching the query (destructive — confirm first)."""
        removed = svc.remove_by_search(query, identity_id)
        if removed is None:
            return f"No transaction of yours matches {query!r} — nothing removed."
        return (f"Removed: {removed['date']} [{removed['kind']}] {removed['description']} = "
                f"{_brl(removed['amount'])}.")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_usage() -> str:
        """AI token/usage — delegated to the host's metering."""
        return svc.usage_note()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def help() -> str:
        """What the bookkeeper does (scope guardrail)."""
        return svc.help_note()

    return mcp


def _seeded_service() -> BookkeeperService:
    """Build a service from the injected per-tenant env (Postgres when a DSN is set)."""
    dsn = os.environ.get("COGNO_BOOKKEEPER_DSN") or os.environ.get("COGNO_PG_DSN")
    store: BookkeeperStore
    if dsn:
        from cogno_praxis.bookkeeper.stores.postgres import PgBookkeeperStore
        store = PgBookkeeperStore(dsn, os.environ.get("COGNO_BOOKKEEPER_SCOPE", "default"))
    else:
        store = InMemoryBookkeeperStore()
    iso = os.environ.get("COGNO_BOOKKEEPER_TODAY")
    clock = (lambda: date.fromisoformat(iso)) if iso else None
    return BookkeeperService(store, today=clock)


mcp = build_server(_seeded_service())


if __name__ == "__main__":
    mcp.run()

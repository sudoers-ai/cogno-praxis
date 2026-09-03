"""The ``bookkeeper`` (financial) vertical as a FastMCP server.

A thin MCP wrapper over :class:`BookkeeperService`. The host connects via ``cogno-mcp``
(``MCPDispatcher``), so the EGO sees these as ordinary tools. Tool ``annotations``
(readOnlyHint / destructiveHint) flow through cogno-mcp into the EGO's read-only mask +
confirmation gate — ``remove_by_search`` is destructive and the EGO holds it for confirmation.

``remove_by_search`` asks a SECOND question that the annotation cannot: which entry. The
annotation is read per tool NAME before anything runs, so it can say a deletion is coming and
never say what would be deleted; the tool itself reads the ledger and proposes the row it
selected, committing only when the caller names that row back. See ``service.RemovalOutcome``.

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

from cogno_praxis.bookkeeper.arithmetic import MathError, evaluate, format_number
from cogno_praxis.bookkeeper.engine import BookkeeperError
from cogno_praxis.bookkeeper.service import BookkeeperService, RemovalProposal
from cogno_praxis.bookkeeper.store import BookkeeperStore, InMemoryBookkeeperStore


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def _entry_line(t: dict) -> str:
    return f"{t['date']} [{t['kind']}] {t['description']} = {_brl(t['amount'])}"


def _removal_proposal_text(p: RemovalProposal, query: str) -> str:
    """Render a proposal that QUOTES the ledger it just read.

    The grounding of this text is the point, not a nicety: a question phrased per tool name can
    only say "this deletes something", while this one names the date, the description and the
    amount that the query actually selected — and says how many siblings it also matched, which
    is the ambiguity a bare "confirma?" hides. It deliberately does NOT start with the
    ``Removed: `` marker the grounding backstop reads (``bookkeeper/grounding.py``): nothing was
    removed, and the marker is how the rest of the system knows the difference.
    """
    lines = [f"NOT REMOVED — nothing was deleted. Searching {query!r} in YOUR entries selected:",
             f"  {_entry_line(p.entry)}"]
    if p.others:
        lines.append(f"{len(p.others)} other entry(ies) also match {query!r} and were left alone:")
        lines.extend(f"  {_entry_line(o)}" for o in p.others)
    lines.append(
        "Tell the user EXACTLY which entry (date, description, amount) you are about to remove "
        "and get their agreement. Only then call remove_by_search again with the SAME query and "
        f"confirm_tx_id={p.confirm_tx_id!r} to delete that one entry.")
    return "\n".join(lines)


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
    def remove_by_search(query: str, identity_id: str = "", confirm_tx_id: str = "") -> str:
        """Remove YOUR most recent transaction matching the query. TWO STEPS — destructive.

        Called with the query alone it deletes NOTHING: it searches your entries and answers with
        the exact entry it would remove (date, description, amount) plus that entry's id, and
        lists any other entry the same query also matched. Relay that entry to the user, get
        their agreement, then call this again with confirm_tx_id=<that id> to delete it.
        """
        outcome = svc.remove_by_search(query, identity_id, confirm_tx_id=confirm_tx_id)
        if outcome.removed is not None:
            return f"Removed: {_entry_line(outcome.removed)}."
        if outcome.proposal is None:
            return f"No transaction of yours matches {query!r} — nothing removed."
        return _removal_proposal_text(outcome.proposal, query)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_usage() -> str:
        """AI token/usage — delegated to the host's metering."""
        return svc.usage_note()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def math(expression: str) -> str:
        """Compute an arithmetic expression EXACTLY: + - * / ** and parentheses over numbers
        the user gave you (a price, a percentage, a quantity). Use it for reajustes, markups,
        rateios, juros simples — e.g. '1850 * 1.08', '(1200 - 340) / 4'. NEVER do arithmetic
        in your head. Decimals use '.', never ',' (1234.56). This does NOT read the books:
        totals, balances and period summaries come from get_summary/search — never fetch
        entries in order to add them up here."""
        try:
            value = evaluate(expression)
        except MathError as exc:
            # Recoverable: the EGO feeds the text back so the model can fix the expression.
            # Say what to DO, not only which forms exist — an error naming only forms gets
            # the same wrong input reworded (the resolve_date lesson).
            return (f"ERROR: could not compute {expression!r}: {exc}. Send a plain arithmetic "
                    "expression over the numbers you already have, e.g. '1850 * 1.08'. "
                    "If a number is missing, ASK the user for it instead of guessing.")
        return f"{expression} = {format_number(value)}"

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

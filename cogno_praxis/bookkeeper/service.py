"""``BookkeeperService`` — orchestrates the engine + store and applies role visibility.

The service is the injection seam: the host builds one over its own store adapter (or the
in-memory default) and hands it to ``build_server``. It raises ``BookkeeperError`` on a domain
violation; the server maps that to a recoverable tool error (fed back to the model).

**Role visibility** (mechanics only — the host authorises the role): an ``EMPLOYEE`` sees/searches
only the transactions they recorded; an oversight role (SUPERVISOR/ADMIN/OWNER) sees the whole
scope. Recording is always attributed to the caller's ``identity_id``; ``remove_by_search`` only
removes the caller's OWN entries (a guardrail — no cross-identity deletion).
"""

from __future__ import annotations

import itertools
import uuid
from datetime import date, datetime, timezone
from typing import Callable, Optional

from cogno_praxis.bookkeeper.engine import (
    INCOME,
    OUTCOME,
    BookkeeperError,
    matches_query,
    normalize_name,
    parse_amount,
    resolve_date,
    summarize,
)
from cogno_praxis.bookkeeper.store import (
    BookkeeperStore,
    InMemoryBookkeeperStore,
    Transaction,
    is_oversight,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


_ORDINAL = itertools.count()


def _now() -> str:
    """A strictly-increasing creation stamp (wall clock + a process ordinal tiebreaker) — sorts
    chronologically as a plain string, so "most recent" is deterministic even within a tx_date."""
    return f"{datetime.now(timezone.utc).isoformat()}-{next(_ORDINAL):09d}"


class BookkeeperService:
    def __init__(self, store: Optional[BookkeeperStore] = None, *,
                 today: Optional[Callable[[], date]] = None) -> None:
        self._store: BookkeeperStore = store or InMemoryBookkeeperStore()
        self._today: Callable[[], date] = today or date.today

    # ── recording (mutating) ───────────────────────────────────────────
    def add_income(self, description: str, amount: object, identity_id: str, *,
                   client_name: str = "", tx_date: str = "") -> Transaction:
        amt = parse_amount(amount)
        desc = normalize_name(description)
        if not desc:
            raise BookkeeperError("description is required")
        client_id = ""
        cname = normalize_name(client_name)
        if cname:
            client_id = self._store.upsert_client(cname).client_id
        tx = Transaction(tx_id=_new_id(), kind=INCOME, identity_id=identity_id, description=desc,
                         amount=amt, tx_date=resolve_date(tx_date, self._today()),
                         client_id=client_id, client_name=cname, created_at=_now())
        self._store.add(tx)
        return tx

    def add_outcome(self, description: str, amount: object, identity_id: str, *,
                    tx_date: str = "") -> Transaction:
        amt = parse_amount(amount)
        desc = normalize_name(description)
        if not desc:
            raise BookkeeperError("description is required")
        tx = Transaction(tx_id=_new_id(), kind=OUTCOME, identity_id=identity_id, description=desc,
                         amount=amt, tx_date=resolve_date(tx_date, self._today()), created_at=_now())
        self._store.add(tx)
        return tx

    # ── reading (read-only, role-scoped) ───────────────────────────────
    def _scope(self, identity_id: str, role: str) -> Optional[str]:
        """The identity filter for a read: None (all) for oversight, else the caller's own id."""
        return None if is_oversight(role) else identity_id

    def get_summary(self, identity_id: str, role: str, *,
                    date_from: str = "", date_to: str = "") -> dict:
        who = self._scope(identity_id, role)
        df, dt = (date_from or None), (date_to or None)
        incomes = self._store.list(kind=INCOME, identity_id=who, date_from=df, date_to=dt)
        outcomes = self._store.list(kind=OUTCOME, identity_id=who, date_from=df, date_to=dt)
        totals = summarize((t.amount for t in incomes), (t.amount for t in outcomes))
        return {**totals, "income_count": len(incomes), "outcome_count": len(outcomes),
                "incomes": [self._row(t) for t in incomes],
                "outcomes": [self._row(t) for t in outcomes]}

    def list_clients(self) -> list[dict]:
        # clients are business-wide reference data (not identity-scoped)
        return [{"client_id": c.client_id, "name": c.name} for c in self._store.list_clients()]

    def search(self, query: str, identity_id: str, role: str, *,
               date_from: str = "", date_to: str = "") -> list[dict]:
        who = self._scope(identity_id, role)
        rows = self._store.list(identity_id=who, date_from=date_from or None, date_to=date_to or None)
        hits = [t for t in rows if matches_query(f"{t.description} {t.client_name}", query)]
        return [self._row(t) for t in hits]

    # ── removing (destructive — own entries only) ──────────────────────
    def remove_by_search(self, query: str, identity_id: str) -> Optional[dict]:
        """Remove the caller's most recent transaction matching ``query`` (None if no match)."""
        rows = self._store.list(identity_id=identity_id)   # own only, most-recent first
        for t in rows:
            if matches_query(f"{t.description} {t.client_name}", query):
                self._store.remove(t.tx_id)
                return self._row(t)
        return None

    # ── usage / help ───────────────────────────────────────────────────
    @staticmethod
    def usage_note() -> str:
        """AI token/usage is metered by the HOST (cogno-meter), not this vertical (decision #4)."""
        return ("AI usage/token metering is tracked by the host, not the bookkeeper. "
                "Ask the operator for the usage dashboard.")

    @staticmethod
    def help_note() -> str:
        return ("I am the financial bookkeeper: I record income (entradas) and expenses (saídas), "
                "track clients, search transactions and produce summaries. I do not schedule "
                "appointments or answer general questions — those go to reception.")

    @staticmethod
    def _row(t: Transaction) -> dict:
        return {"tx_id": t.tx_id, "kind": t.kind, "description": t.description,
                "amount": t.amount, "date": t.tx_date, "client": t.client_name}

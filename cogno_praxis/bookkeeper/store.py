"""Domain types + the persistence port for the ``bookkeeper`` vertical.

Financial transactions are **structured domain data**, so the vertical owns its store port (a
Protocol + an in-memory default; the host plugs the Pg adapter) — the same pattern as
``scheduler/store.py``. The vertical is **tenant-agnostic**: multi-tenancy is the host pointing
at the right store/scope, never a column the vertical filters. Identity fields are **opaque
strings** the host resolves/authorizes; the bookkeeper just persists and echoes them back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from cogno_praxis.bookkeeper.engine import INCOME, OUTCOME  # noqa: F401 — re-exported for callers

# Roles whose view is UNSCOPED (see every transaction in the scope) — the oversight roles.
# An EMPLOYEE sees only the transactions they recorded (their own identity_id). The vertical
# only maps role→visibility (mechanics); the host decides the role (authorises).
EMPLOYEE_ROLE = "EMPLOYEE"
OVERSIGHT_ROLES: frozenset[str] = frozenset({"SUPERVISOR", "ADMIN", "OWNER"})


def is_oversight(role: str) -> bool:
    return (role or "").upper() in OVERSIGHT_ROLES


@dataclass
class Client:
    """A known client of the business (someone income is attributed to)."""

    client_id: str
    name: str


@dataclass
class Transaction:
    """One financial entry — an income (entrada) or an outcome (saída)."""

    tx_id: str
    kind: str                 # "income" | "outcome"
    identity_id: str          # who recorded it (opaque; the host's identity id)
    description: str
    amount: float
    tx_date: str              # ISO "YYYY-MM-DD"
    client_id: str = ""       # optional (incomes may be attributed to a client)
    client_name: str = ""     # denormalized display name (NOT a key)
    created_at: str = ""      # ISO datetime — recency tiebreaker within a tx_date (set by service)


@runtime_checkable
class BookkeeperStore(Protocol):
    """The persistence port. In-memory default below; the host injects ``PgBookkeeperStore``."""

    # clients
    def upsert_client(self, name: str) -> Client: ...
    def list_clients(self) -> list[Client]: ...

    # transactions
    def add(self, tx: Transaction) -> None: ...
    def get(self, tx_id: str) -> Optional[Transaction]: ...
    def remove(self, tx_id: str) -> None: ...
    def list(self, *, kind: Optional[str] = None, identity_id: Optional[str] = None,
             date_from: Optional[str] = None, date_to: Optional[str] = None) -> list[Transaction]: ...


@dataclass
class InMemoryBookkeeperStore:
    """Process-local store — the standalone demo + unit tests. Production injects the Pg adapter."""

    clients: dict[str, Client] = field(default_factory=dict)      # client_id → Client
    txs: dict[str, Transaction] = field(default_factory=dict)     # tx_id → Transaction
    _seq: int = 0

    def upsert_client(self, name: str) -> Client:
        for c in self.clients.values():
            if c.name.lower() == name.lower():
                return c
        self._seq += 1
        cid = f"c{self._seq}"
        c = Client(client_id=cid, name=name)
        self.clients[cid] = c
        return c

    def list_clients(self) -> list[Client]:
        return list(self.clients.values())

    def add(self, tx: Transaction) -> None:
        self.txs[tx.tx_id] = tx

    def get(self, tx_id: str) -> Optional[Transaction]:
        return self.txs.get(tx_id)

    def remove(self, tx_id: str) -> None:
        self.txs.pop(tx_id, None)

    def list(self, *, kind: Optional[str] = None, identity_id: Optional[str] = None,
             date_from: Optional[str] = None, date_to: Optional[str] = None) -> list[Transaction]:
        out = list(self.txs.values())
        if kind is not None:
            out = [t for t in out if t.kind == kind]
        if identity_id is not None:
            out = [t for t in out if t.identity_id == identity_id]
        if date_from is not None:
            out = [t for t in out if t.tx_date >= date_from]
        if date_to is not None:
            out = [t for t in out if t.tx_date <= date_to]
        # most recent first (by date, then creation time within the day)
        return sorted(out, key=lambda t: (t.tx_date, t.created_at), reverse=True)

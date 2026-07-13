"""The ``bookkeeper`` vertical — financial bookkeeping tools behind a FastMCP server.

Backs the BOOKKEEPER persona (parent SaaS ANALYST). Mirrors the ``scheduler`` vertical:
pure engine + a store port + a service + a FastMCP server, tenant-agnostic with role visibility.
See ``docs/BOOKKEEPER.md``.
"""

from cogno_praxis.bookkeeper.durability import is_perishable_edge
from cogno_praxis.bookkeeper.engine import INCOME, OUTCOME, BookkeeperError
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.bookkeeper.store import (
    BookkeeperStore,
    Client,
    InMemoryBookkeeperStore,
    Transaction,
    is_oversight,
)

__all__ = [
    "BookkeeperError", "BookkeeperService", "BookkeeperStore", "InMemoryBookkeeperStore",
    "Client", "Transaction", "is_oversight", "is_perishable_edge", "INCOME", "OUTCOME",
]

"""The ``coordinator`` vertical — academic class-schedule management.

Backs the COORDINATOR persona (ported from the parent's coordinator_assistant). Like the other
verticals it is pure domain + a store port: the domain (aggregation, deadlines, IBOPE, swaps)
reads through a :class:`SpreadsheetStore` the host injects — in production a Google-download
adapter, in tests :class:`InMemorySpreadsheetStore`. Configured per tenant from ``custom_rules``
via :class:`CoordinatorConfig`. See ``docs/COORDINATOR.md``.
"""

from cogno_praxis.coordinator.config import CoordinatorConfig
from cogno_praxis.coordinator.service import CoordinatorError, CoordinatorService
from cogno_praxis.coordinator.store import InMemorySpreadsheetStore, SpreadsheetStore
from cogno_praxis.coordinator.types import ClassEntry, ColumnLayout

__all__ = [
    "CoordinatorConfig", "CoordinatorService", "CoordinatorError",
    "SpreadsheetStore", "InMemorySpreadsheetStore", "ClassEntry", "ColumnLayout",
]

"""The ``coordinator`` vertical — academic class-schedule management.

Backs the COORDINATOR persona (ported from the parent's coordinator_assistant). Like the other
verticals it is pure domain + a store port: the domain (aggregation, deadlines, IBOPE, swaps)
reads through a :class:`SpreadsheetStore` the host injects — in production a Google-download
adapter, in tests :class:`InMemorySpreadsheetStore`. Configured per tenant from ``custom_rules``
via :class:`CoordinatorConfig`. See ``docs/COORDINATOR.md``.
"""

from cogno_praxis.coordinator.ics import (
    CalendarEvent,
    CalendarSender,
    RecordingCalendarSender,
    build_ics_calendar,
    class_event_uid,
    sequence_now,
)
from cogno_praxis.coordinator.config import CoordinatorConfig
from cogno_praxis.coordinator.pay import (
    BonusTier,
    PayEstimate,
    PayGroup,
    PayHypothesis,
    PayLine,
    fmt_hours,
    fmt_money,
    parse_bonus_tiers,
    parse_money,
    render_pay_block,
)
from cogno_praxis.coordinator.durability import is_perishable_edge
from cogno_praxis.coordinator.server import build_server
from cogno_praxis.coordinator.service import (
    CalendarProposal,
    CoordinatorAccessError,
    CoordinatorConfigError,
    CoordinatorError,
    CoordinatorService,
    month_label,
)
from cogno_praxis.coordinator.store import InMemorySpreadsheetStore, SpreadsheetStore
from cogno_praxis.coordinator.types import (
    ClassEntry,
    ColumnLayout,
    DailyChecks,
    DeadlineDue,
    ReadReport,
    SheetReadError,
)

__all__ = [
    "CoordinatorConfig", "CoordinatorService", "CoordinatorError", "CoordinatorAccessError",
    "CoordinatorConfigError",
    "SpreadsheetStore", "InMemorySpreadsheetStore", "ClassEntry", "ColumnLayout",
    "ReadReport", "SheetReadError", "build_server", "is_perishable_edge",
    # the whole day in one composed read: today's classes, the deadlines, the survey trigger
    "DailyChecks", "DeadlineDue",
    # the calendar export (.ics by e-mail) — the pure builder plus its delivery port
    "CalendarEvent", "CalendarSender", "RecordingCalendarSender", "build_ics_calendar",
    "class_event_uid", "sequence_now",
    # the PROPOSAL half of that export: what a send would put in the mail, read and not sent
    "CalendarProposal", "month_label",
    # the professor's own pay: the estimate, its declared bonus bands, and its block
    "PayEstimate", "PayGroup", "PayLine", "PayHypothesis", "BonusTier",
    "render_pay_block", "parse_bonus_tiers", "parse_money", "fmt_money", "fmt_hours",
]

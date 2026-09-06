"""``scheduler`` — the agenda capability (reception/scheduling).

A FastMCP server exposing scheduling tools, backed by a domain store port (in-memory
default; host injects a real adapter). It ships with the **SECRETARY** persona — the
universal front-door receptionist — whose prompt slots live in ``prompts/`` (the
out-of-the-box default; a company adds its own persona host-side, targeting this same
capability, without touching the scheduler).
"""

from cogno_praxis.scheduler.engine import (
    AvailabilityEngine,
    HolidaysUnavailableError,
    SchedulerConfig,
    Slot,
)
from cogno_praxis.scheduler.durability import is_perishable_edge
from cogno_praxis.scheduler.server import build_server
# The `resolve_date` model-facing text is exported at package level ON PURPOSE: it is a
# CROSS-REPO contract, not an internal detail. The host's cortex builtin publishes the same
# tool name to every non-scheduler persona and imports these, so a rename here breaks a
# consumer in another repository — which is exactly the kind of thing that should have to
# pass through `__all__` rather than through a module path someone reached into.
from cogno_praxis.scheduler.service import (
    DEFAULT_SLOTS,
    RESOLVE_DATE_DESCRIPTION,
    RESOLVE_DATE_SCHEDULER_SUFFIX,
    SchedulerError,
    SchedulerService,
    format_date,
    resolve_date_answer,
    resolve_date_error,
)
from cogno_praxis.scheduler.store import (
    VALID_STATUS,
    Appointment,
    AppointmentStore,
    Host,
    InMemoryAppointmentStore,
)

__all__ = [
    "build_server",
    "is_perishable_edge",
    "SchedulerService",
    "SchedulerError",
    "SchedulerConfig",
    "AvailabilityEngine",
    "HolidaysUnavailableError",
    "Slot",
    "DEFAULT_SLOTS",
    "RESOLVE_DATE_DESCRIPTION",
    "RESOLVE_DATE_SCHEDULER_SUFFIX",
    "format_date",
    "resolve_date_answer",
    "resolve_date_error",
    "VALID_STATUS",
    "Appointment",
    "Host",
    "AppointmentStore",
    "InMemoryAppointmentStore",
]

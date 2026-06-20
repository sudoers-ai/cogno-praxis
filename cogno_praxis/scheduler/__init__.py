"""``scheduler`` — the agenda capability (reception/scheduling).

A FastMCP server exposing scheduling tools, backed by a domain store port (in-memory
default; host injects a real adapter). It ships with the **SECRETARY** persona — the
universal front-door receptionist — whose prompt slots live in ``prompts/`` (the
out-of-the-box default; a company adds its own persona host-side, targeting this same
capability, without touching the scheduler).
"""

from cogno_praxis.scheduler.server import build_server
from cogno_praxis.scheduler.service import DEFAULT_SLOTS, SchedulerError, SchedulerService
from cogno_praxis.scheduler.store import (
    VALID_STATUS,
    Appointment,
    AppointmentStore,
    Host,
    InMemoryAppointmentStore,
)

__all__ = [
    "build_server",
    "SchedulerService",
    "SchedulerError",
    "DEFAULT_SLOTS",
    "VALID_STATUS",
    "Appointment",
    "Host",
    "AppointmentStore",
    "InMemoryAppointmentStore",
]

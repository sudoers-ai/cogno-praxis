"""SECRETARY (reception) vertical — the entry point for any client.

A FastMCP server exposing reception/scheduling tools, backed by a domain store
port (in-memory default; host injects a real adapter). The host connects to it via
cogno-mcp and binds it to the SECRETARY persona (prompts in ``persona/``).
"""

from cogno_praxis.secretary.server import build_server
from cogno_praxis.secretary.service import DEFAULT_SLOTS, SecretaryError, SecretaryService
from cogno_praxis.secretary.store import (
    Appointment,
    AppointmentStore,
    Host,
    InMemoryAppointmentStore,
)

__all__ = [
    "build_server",
    "SecretaryService",
    "SecretaryError",
    "DEFAULT_SLOTS",
    "Appointment",
    "Host",
    "AppointmentStore",
    "InMemoryAppointmentStore",
]

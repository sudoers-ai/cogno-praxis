"""Reception/scheduling domain logic — pure, over an ``AppointmentStore``.

No MCP here: the service is the testable core (book / cancel / availability). The
FastMCP ``server`` is a thin wrapper that turns these into MCP tools. Domain errors
(unknown host, slot taken, unknown appointment) raise ``SecretaryError``; the server
maps them to recoverable tool errors.
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from cogno_praxis.secretary.store import (
    Appointment,
    AppointmentStore,
    Host,
    InMemoryAppointmentStore,
)

# Default bookable slots (a real deployment configures these per host).
DEFAULT_SLOTS: tuple[str, ...] = (
    "09:00", "10:00", "11:00", "14:00", "15:00", "16:00",
)


class SecretaryError(RuntimeError):
    """A recoverable domain error (unknown host, slot taken, unknown appointment)."""


class SecretaryService:
    def __init__(
        self,
        store: Optional[AppointmentStore] = None,
        *,
        slots: Sequence[str] = DEFAULT_SLOTS,
    ) -> None:
        self.store: AppointmentStore = store or InMemoryAppointmentStore()
        self._slots = tuple(slots)

    # ── reads ──────────────────────────────────────────────────────────
    def list_hosts(self) -> list[Host]:
        return self.store.list_hosts()

    def check_availability(self, host_id: str, date: str) -> list[str]:
        if self.store.get_host(host_id) is None:
            raise SecretaryError(f"unknown host: {host_id}")
        taken = self.store.booked_times(host_id, date)
        return [s for s in self._slots if s not in taken]

    def list_appointments(self, *, host_id: Optional[str] = None,
                          with_name: Optional[str] = None) -> list[Appointment]:
        return self.store.list(host_id=host_id, with_name=with_name)

    # ── writes ─────────────────────────────────────────────────────────
    def book(self, host_id: str, date: str, time: str, with_name: str,
             notes: str = "") -> Appointment:
        if self.store.get_host(host_id) is None:
            raise SecretaryError(f"unknown host: {host_id}")
        if time not in self._slots:
            raise SecretaryError(f"{time} is not a bookable slot")
        if time in self.store.booked_times(host_id, date):
            raise SecretaryError(f"{time} on {date} is already booked")
        appt = Appointment(
            appointment_id=uuid.uuid4().hex[:8], host_id=host_id, date=date,
            time=time, with_name=with_name, notes=notes)
        self.store.add(appt)
        return appt

    def cancel(self, appointment_id: str) -> Appointment:
        appt = self.store.get(appointment_id)
        if appt is None:
            raise SecretaryError(f"unknown appointment: {appointment_id}")
        appt.status = "cancelled"
        self.store.update(appt)
        return appt

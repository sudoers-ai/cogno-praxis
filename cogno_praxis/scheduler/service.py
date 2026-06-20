"""Scheduling domain logic — pure, over an ``AppointmentStore``.

No MCP here: the service is the testable core (book / cancel / availability /
status transitions). The FastMCP ``server`` is a thin wrapper that turns these into
MCP tools. Domain errors (unknown host, slot taken, past date, unknown appointment)
raise ``SchedulerError``; the server maps them to recoverable tool errors.

Domain rules live here (they are the *vertical's* business rules, not orchestration):
a slot must be free, and an appointment can only be booked **from tomorrow on** (the
parent's "never today or a past date" policy). Tenant scoping, RBAC and notifications
are the host's job, not the scheduler's.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Callable, Optional, Sequence

from cogno_praxis.scheduler.store import (
    CANCELED,
    VALID_STATUS,
    Appointment,
    AppointmentStore,
    Host,
    InMemoryAppointmentStore,
)

# Default bookable slots (a real deployment configures these per host).
DEFAULT_SLOTS: tuple[str, ...] = (
    "09:00", "10:00", "11:00", "14:00", "15:00", "16:00",
)


class SchedulerError(RuntimeError):
    """A recoverable domain error (unknown host, slot taken, past date, unknown id)."""


class SchedulerService:
    def __init__(
        self,
        store: Optional[AppointmentStore] = None,
        *,
        slots: Sequence[str] = DEFAULT_SLOTS,
        today: Optional[Callable[[], date]] = None,
    ) -> None:
        self.store: AppointmentStore = store or InMemoryAppointmentStore()
        self._slots = tuple(slots)
        # Injectable clock keeps the "start from tomorrow" rule deterministic in tests.
        self._today: Callable[[], date] = today or date.today

    # ── reads ──────────────────────────────────────────────────────────
    def list_hosts(self) -> list[Host]:
        return self.store.list_hosts()

    def check_availability(self, host_id: str, date: str) -> list[str]:
        if self.store.get_host(host_id) is None:
            raise SchedulerError(f"unknown host: {host_id}")
        self._require_future(date)
        taken = self.store.booked_times(host_id, date)
        return [s for s in self._slots if s not in taken]

    def list_appointments(self, *, host_id: Optional[str] = None,
                          with_name: Optional[str] = None) -> list[Appointment]:
        return self.store.list(host_id=host_id, with_name=with_name)

    # ── writes ─────────────────────────────────────────────────────────
    def book(self, host_id: str, date: str, time: str, with_name: str,
             notes: str = "") -> Appointment:
        if self.store.get_host(host_id) is None:
            raise SchedulerError(f"unknown host: {host_id}")
        self._require_future(date)
        if time not in self._slots:
            raise SchedulerError(f"{time} is not a bookable slot")
        if time in self.store.booked_times(host_id, date):
            raise SchedulerError(f"{time} on {date} is already booked")
        appt = Appointment(
            appointment_id=uuid.uuid4().hex[:8], host_id=host_id, date=date,
            time=time, with_name=with_name, notes=notes)   # status defaults to PENDING
        self.store.add(appt)
        return appt

    def update_status(self, appointment_id: str, new_status: str) -> Appointment:
        appt = self.store.get(appointment_id)
        if appt is None:
            raise SchedulerError(f"unknown appointment: {appointment_id}")
        status = new_status.upper()
        if status not in VALID_STATUS:
            raise SchedulerError(f"invalid status: {new_status}")
        appt.status = status
        self.store.update(appt)
        return appt

    def cancel(self, appointment_id: str, reason: str = "") -> Appointment:
        appt = self.store.get(appointment_id)
        if appt is None:
            raise SchedulerError(f"unknown appointment: {appointment_id}")
        appt.status = CANCELED
        appt.cancel_reason = reason
        self.store.update(appt)
        return appt

    # ── domain rules ───────────────────────────────────────────────────
    def _require_future(self, iso_date: str) -> None:
        """Enforce the parent's policy: never book today or a past date."""
        try:
            d = date.fromisoformat(iso_date)
        except ValueError as exc:
            raise SchedulerError(f"invalid date: {iso_date} (use YYYY-MM-DD)") from exc
        if d <= self._today():
            raise SchedulerError(
                f"{iso_date} is today or in the past; scheduling starts from tomorrow")

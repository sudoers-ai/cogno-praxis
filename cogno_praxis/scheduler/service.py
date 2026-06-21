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

import unicodedata
import uuid
from datetime import date, timedelta
from typing import Callable, Optional, Sequence

from cogno_praxis.scheduler.store import (
    ACTIVE_STATUS,
    CANCELED,
    CONFIRMED,
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

# Weekday name → Python weekday index (Mon=0). PT + EN, accent-folded.
_WEEKDAYS = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode("ascii")


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

    def block_schedule(self, host_id: str, date: str, *, start_time: str = "",
                       end_time: str = "", description: str = "") -> list[Appointment]:
        """Make a host unavailable for a slot, a time range, or the whole day.

        Mirrors the parent's ``block_schedule``: a block is a host self-occupation,
        stored as a CONFIRMED appointment **with no client** (``is_block``) so it removes
        the slot from availability exactly like a real booking. With no ``start_time`` the
        **entire working day** is blocked; with ``start_time`` alone a single slot; with
        both, every slot in ``[start_time, end_time)``. Refuses if a real client booking
        already sits in the range (never silently bury a patient). Idempotent: an
        already-blocked slot is skipped, not duplicated.

        **Role-blind:** *who* may block (the parent's GUEST-can't / EMPLOYEE-own-only rule)
        is the host's call — the host scopes ``host_id`` per identity and gates tool
        visibility; the vertical only enforces the domain rules (future date, no conflict).
        """
        if self.store.get_host(host_id) is None:
            raise SchedulerError(f"unknown host: {host_id}")
        self._require_not_past(date)
        targets = self._slots_in_range(start_time, end_time)
        active = {a.time: a for a in self.store.list(host_id=host_id)
                  if a.date == date and a.status in ACTIVE_STATUS}
        conflicts = sorted(t for t in targets if t in active and not active[t].is_block)
        if conflicts:
            raise SchedulerError(
                f"cannot block {date}: client appointments exist at {', '.join(conflicts)}")
        note = description.strip() or "Bloqueado"
        created: list[Appointment] = []
        for t in targets:
            if t in active:        # already blocked → idempotent skip
                continue
            appt = Appointment(
                appointment_id=uuid.uuid4().hex[:8], host_id=host_id, date=date,
                time=t, with_name="", status=CONFIRMED, notes=note)
            self.store.add(appt)
            created.append(appt)
        return created

    def _slots_in_range(self, start_time: str, end_time: str) -> list[str]:
        if not start_time:
            return list(self._slots)                       # whole working day
        if not end_time:
            if start_time not in self._slots:
                raise SchedulerError(f"{start_time} is not a bookable slot")
            return [start_time]                            # single slot
        targets = [s for s in self._slots if start_time <= s < end_time]
        if not targets:
            raise SchedulerError(f"no bookable slots between {start_time} and {end_time}")
        return targets

    # ── date resolution ────────────────────────────────────────────────
    def resolve_date(self, expression: str) -> str:
        """Deterministically resolve a relative/named date phrase to an ISO date.

        Handles "hoje/today", "amanhã/tomorrow", "depois de amanhã", and weekday names
        (PT + EN, with or without "próxima"/"que vem") → the NEXT occurrence of that
        weekday strictly after today (if today is that weekday, +7). This exists because
        LLM weekday arithmetic is unreliable; the model calls this instead of guessing.
        Raises ``SchedulerError`` when no date can be parsed (the caller then asks / uses
        an explicit date).
        """
        e = _fold(expression)
        today = self._today()
        if "depois de amanha" in e or "day after tomorrow" in e:
            return (today + timedelta(days=2)).isoformat()
        if "amanha" in e or "tomorrow" in e:
            return (today + timedelta(days=1)).isoformat()
        if "hoje" in e or "today" in e:
            return today.isoformat()
        for word, wd in _WEEKDAYS.items():
            if word in e:
                ahead = (wd - today.weekday()) % 7 or 7   # strictly the NEXT occurrence
                return (today + timedelta(days=ahead)).isoformat()
        raise SchedulerError(f"could not resolve a date from: {expression!r}")

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

    def _require_not_past(self, iso_date: str) -> None:
        """Blocking is allowed from today on (a host can mark *today* as unavailable),
        only a strictly past date is refused — mirrors the parent's ``block_schedule``."""
        try:
            d = date.fromisoformat(iso_date)
        except ValueError as exc:
            raise SchedulerError(f"invalid date: {iso_date} (use YYYY-MM-DD)") from exc
        if d < self._today():
            raise SchedulerError(f"{iso_date} is in the past; cannot block past dates")

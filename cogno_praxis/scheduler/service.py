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

import re
import unicodedata
import uuid
from datetime import date, timedelta
from typing import Callable, Iterable, Optional

from cogno_praxis.scheduler.engine import AvailabilityEngine, SchedulerConfig
from cogno_praxis.scheduler.store import (
    ACTIVE_STATUS,
    CANCELED,
    COMPLETED,
    CONFIRMED,
    EMPLOYEE_ROLE,
    GUEST_ROLE,
    OVERSIGHT_ROLES,
    PENDING,
    VALID_STATUS,
    Appointment,
    AppointmentStore,
    Host,
    InMemoryAppointmentStore,
)

# The default working day (SchedulerConfig defaults: 09:00–17:00, 60-min, lunch 12:00–14:00)
# yields exactly these slot starts — the classic set, before any tenant config.
DEFAULT_SLOTS: tuple[str, ...] = (
    "09:00", "10:00", "11:00", "14:00", "15:00", "16:00",
)

# Weekday name → Python weekday index (Mon=0). PT + EN, accent-folded.
_WEEKDAYS = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
}


_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# Numeric, DAY-FIRST (pt-BR locale): 09/07, 09-07-2026, 9.7.26 → day, month, [year].
_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?\b")
# Named: "9 de julho", "09 julho de 2026", "9 jul".
_NAMED_RE = re.compile(r"\b(\d{1,2})\s*(?:de\s+)?([a-z]+)(?:\s+de\s+(\d{4}))?")


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode("ascii")


def _year_for(day: int, month: int, today: date) -> Optional[date]:
    """Pick the year that puts (day, month) today-or-later — this year, else next.
    Returns None for an impossible day/month (e.g. 31/02)."""
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d
    return None


def _parse_calendar_date(e: str, today: date) -> Optional[date]:
    """Resolve an explicit calendar date from a folded phrase (ISO, numeric dd/mm,
    or a named month). Returns None when the phrase carries no such date. Day-first
    (pt-BR) — '09/07' is 9 July, not September 7."""
    m = _ISO_RE.search(e)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _NUMERIC_RE.search(e)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        if m.group(3):                      # explicit year (2- or 4-digit)
            y = int(m.group(3))
            y += 2000 if y < 100 else 0
            try:
                return date(y, month, day)
            except ValueError:
                return None
        return _year_for(day, month, today)
    m = _NAMED_RE.search(e)
    if m and m.group(2) in _MONTHS:
        day, month = int(m.group(1)), _MONTHS[m.group(2)]
        if m.group(3):
            try:
                return date(int(m.group(3)), month, day)
            except ValueError:
                return None
        return _year_for(day, month, today)
    return None


def _norm_host(s: str) -> str:
    """Fold to a comparable key for fuzzy host matching: accent-free, no honorific, alnum only —
    so 'dr_jose_luiz_manzoli', 'Dr. José Luiz Manzoli' and 'joseluizmanzoli' all collapse equal."""
    folded = _fold(s)
    for hon in ("dra", "dr", "sr", "sra"):
        folded = folded.replace(hon, "")
    return "".join(ch for ch in folded if ch.isalnum())


class SchedulerError(RuntimeError):
    """A recoverable domain error (unknown host, slot taken, past date, unknown id)."""


class SchedulerService:
    def __init__(
        self,
        store: Optional[AppointmentStore] = None,
        *,
        config: Optional[SchedulerConfig] = None,
        country: Optional[str] = None,
        state: Optional[str] = None,
        holidays: Optional[Iterable[date]] = None,
        today: Optional[Callable[[], date]] = None,
    ) -> None:
        self.store: AppointmentStore = store or InMemoryAppointmentStore()
        # The tenant's rules (hours/lunch/weekends/slot) drive the availability engine; the
        # host injects config + location (country/state → holidays) per tenant. With none,
        # sensible defaults apply (classic 09–17 working day, no holiday filtering).
        self._config = config or SchedulerConfig()
        self._country, self._state = country, state
        self._holidays = list(holidays) if holidays is not None else None
        self._engine = AvailabilityEngine(self._config, country=country, state=state,
                                          holidays=self._holidays)
        self._slots: tuple[str, ...] = tuple(self._engine.slot_starts())
        # Injectable clock keeps the "start from tomorrow" rule deterministic in tests.
        self._today: Callable[[], date] = today or date.today

    # ── settings (config read/write — the host authorises WHO via RBAC) ──
    def get_settings(self) -> dict:
        """The tenant's current scheduling rules (hours/lunch/weekends/slot/policy)."""
        return self._config.to_dict()

    def set_settings(self, **overrides: object) -> dict:
        """Update scheduling rules and rebuild the availability engine. Only the fields
        passed (non-None) change; raises on a malformed value. The *vertical* applies the
        change; the *host* decides who may call it (supervisor) — this is just the writer.
        """
        raw = {**self._config.to_dict(),
               **{k: v for k, v in overrides.items() if v is not None}}
        try:
            new_config = SchedulerConfig(raw)
        except (ValueError, TypeError) as exc:
            raise SchedulerError(f"invalid schedule settings: {exc}") from exc
        self._config = new_config
        self._engine = AvailabilityEngine(self._config, country=self._country,
                                          state=self._state, holidays=self._holidays)
        self._slots = tuple(self._engine.slot_starts())
        return self._config.to_dict()

    def set_auto_confirm(self, host_id: str, value: bool) -> Host:
        """Set a professional's auto_confirm flag (the EMPLOYEE's own choice; the host pins
        host_id to the caller's own agenda for non-supervisors via RBAC)."""
        host = self.store.get_host(host_id)
        if host is None:
            raise SchedulerError(f"unknown host: {host_id}")
        host.auto_confirm = bool(value)
        return host

    # ── host resolution ────────────────────────────────────────────────
    def _resolve_host_id(self, host_id: str) -> str:
        """Tolerate a model that invents a name-slug id ('dr_jose_luiz_manzoli') instead of the
        catalog id: exact match first, then a normalized match against every host's id AND name
        (accent/honorific/separator-insensitive), then a **single specialty** match ('o
        cardiologista' → the one cardiologist). An ambiguous specialty (more than one host with
        that role) stays unresolved, so the caller lists them and the user picks. Returns the real
        id, or the input unchanged so the 'unknown host' error still fires when nothing matches."""
        if self.store.get_host(host_id) is not None:
            return host_id
        target = _norm_host(host_id)
        if not target:
            return host_id
        for h in self.store.list_hosts():
            if _norm_host(h.host_id) == target or _norm_host(h.name) == target:
                return h.host_id
        # specialty/role: booking "com o cardiologista" is valid when exactly one host has it.
        by_role = [h for h in self.store.list_hosts() if h.role and _norm_host(h.role) == target]
        if len(by_role) == 1:
            return by_role[0].host_id
        return host_id

    # ── reads ──────────────────────────────────────────────────────────
    def list_hosts(self) -> list[Host]:
        return self.store.list_hosts()

    def check_availability(self, host_id: str, date: str) -> list[str]:
        host_id = self._resolve_host_id(host_id)
        if self.store.get_host(host_id) is None:
            raise SchedulerError(f"unknown host: {host_id}")
        self._require_future(date)
        self._require_working_day(date)
        taken = self.store.booked_times(host_id, date)
        return [s for s in self._slots if s not in taken]

    def list_appointments(self, *, identity_id: Optional[str] = None,
                          role: Optional[str] = None, host_id: Optional[str] = None,
                          guest_id: Optional[str] = None,
                          with_name: Optional[str] = None,
                          status: Optional[str] = None,
                          include_history: bool = False) -> list[Appointment]:
        """Role-based visibility (parent parity), resolved in the VERTICAL:

        - GUEST → only their own bookings (``guest_id == identity_id``)
        - EMPLOYEE → only their own host agenda (``host_id == identity_id``)
        - SUPERVISOR / ADMIN / SECRETARY → everything in the scope (no id filter)

        The host AUTHORISES (it assigns the ``identity_id`` + ``role``); the vertical just maps
        role→column and the store filters. When ``role`` is omitted the explicit
        ``host_id``/``guest_id``/``with_name`` filters pass through (internal / test use).

        By default only the LIVE agenda is returned — ``ACTIVE_STATUS`` (PENDING/CONFIRMED).
        Terminal rows (CANCELED/COMPLETED) are hidden so a stale cancellation never leaks into
        the reply (the parent's ``status != 'CANCELED'`` default; here also drops COMPLETED so
        the professional sees only what is still on the calendar). ``include_history=True``
        brings everything back when the user explicitly asks for past/canceled appointments.

        ``status`` is an exact-status filter ("traga só os pendentes" → ``PENDING``) applied
        AFTER the role visibility. Deterministic here — leaving it to the model ("only pending"
        as a prompt constraint over a mixed listing) is exactly what made the executor act on
        the wrong subset. An explicit terminal status (CANCELED/COMPLETED) implies history."""
        if role is not None:
            r = role.upper()
            if r == GUEST_ROLE:
                appts = self.store.list(guest_id=identity_id or "")
            elif r == EMPLOYEE_ROLE:
                appts = self.store.list(host_id=identity_id or "")
            elif r in OVERSIGHT_ROLES:
                appts = self.store.list()         # unscoped oversight — all agendas in scope
            else:
                # unknown role → fail-safe to the narrowest view (own bookings), never "see all"
                appts = self.store.list(guest_id=identity_id or "")
        else:
            appts = self.store.list(host_id=host_id, guest_id=guest_id, with_name=with_name)
        if status is not None and status.strip():
            s = status.strip().upper()
            if s not in VALID_STATUS:
                raise SchedulerError(
                    f"invalid status filter: {status} (use one of {', '.join(VALID_STATUS)})")
            return [a for a in appts if a.status == s]
        if not include_history:
            appts = [a for a in appts if a.status in ACTIVE_STATUS]
        return appts

    # ── writes ─────────────────────────────────────────────────────────
    def book(self, host_id: str, date: str, time: str, with_name: str,
             notes: str = "", *, guest_id: str = "", host_name: str = "") -> Appointment:
        host_id = self._resolve_host_id(host_id)
        host = self.store.get_host(host_id)
        if host is None:
            raise SchedulerError(f"unknown host: {host_id}")
        self._require_future(date)
        self._require_working_day(date)
        self._enforce_policies(host_id, date, time, with_name, guest_id=guest_id)
        if time not in self._slots:
            raise SchedulerError(f"{time} is not a bookable slot")
        if time in self.store.booked_times(host_id, date):
            # Idempotent: re-booking the IDENTICAL appointment (same host/date/time/client)
            # returns the existing one instead of erroring. This makes the host's EGO↔judge
            # correction loop safe — a retry that re-issues the same booking succeeds rather
            # than colliding with its own first attempt. A *different* client still conflicts.
            existing = next(
                (a for a in self.store.list(host_id=host_id)
                 if a.date == date and a.time == time and a.status in ACTIVE_STATUS), None)
            # "same client" = same stable guest_id when we have one, else the display name.
            if existing is not None and not existing.is_block and (
                    (guest_id.strip() and existing.guest_id.strip() == guest_id.strip())
                    or (not guest_id.strip() and with_name.strip()
                        and existing.with_name.strip().lower() == with_name.strip().lower())):
                return existing
            # Carry the free alternatives IN the error (the parent's SLOT_UNAVAILABLE
            # pattern) so the model offers them in one shot instead of re-looping.
            free = [s for s in self._slots if s not in self.store.booked_times(host_id, date)]
            free_txt = ", ".join(free) if free else "none that day"
            raise SchedulerError(
                f"{time} on {date} is already booked. Free slots on {date}: {free_txt}")
        # The professional's auto_confirm decides: instant CONFIRMED, or PENDING until they
        # accept (update_appointment_status). The booker's *role* never enters here — RBAC is
        # the host's job; the vertical only reads the professional's own setting.
        status = CONFIRMED if host.auto_confirm else PENDING
        appt = Appointment(
            appointment_id=uuid.uuid4().hex[:8], host_id=host_id, date=date,
            time=time, with_name=with_name, status=status, notes=notes,
            guest_id=guest_id, host_name=host_name or host.name)
        self.store.add(appt)
        return appt

    def _authorize(self, appt: Appointment, identity_id: Optional[str],
                   role: Optional[str]) -> None:
        """Row-level ownership gate for the destructive mutations (cancel / update_status /
        reschedule). The parent enforced this INSIDE the tool; here the host injects the
        authenticated ``identity_id`` + ``role`` (exactly as it already does for
        ``list_appointments``) and the vertical maps role→column:

        - GUEST may only touch their OWN booking (``guest_id``)
        - EMPLOYEE may only touch their OWN agenda (``host_id``)
        - SUPERVISOR / ADMIN / SECRETARY → unscoped oversight

        When ``role`` is omitted (internal / test callers, or the demo guest with no stable id
        — the host does not inject then) the check is skipped: the host is what authorises,
        the same contract as ``list_appointments``. Visibility already hides other people's
        rows; this is the second layer — a stale/leaked id can no longer mutate a row the
        caller does not own."""
        if role is None:
            return
        r = role.upper()
        if r in OVERSIGHT_ROLES:
            return
        if r == GUEST_ROLE:
            owned = bool(identity_id) and appt.guest_id == identity_id
        elif r == EMPLOYEE_ROLE:
            owned = bool(identity_id) and appt.host_id == identity_id
        else:
            owned = False    # unknown role → deny (fail-safe, mirrors list's narrowest view)
        if not owned:
            raise SchedulerError(
                f"appointment {appt.appointment_id} is not yours to modify")

    def update_status(self, appointment_id: str, new_status: str, *,
                      identity_id: Optional[str] = None, role: Optional[str] = None,
                      ) -> tuple[Appointment, bool]:
        """Move an appointment along its lifecycle. Returns ``(appt, changed)``.

        Ownership (parent parity; host-authorised) is enforced via ``_authorize``.

        Two guards (live finding — a bulk "confirme os pendentes" acting on stale ids):
        - **no-op transition** is idempotent (``changed=False``), never an error — a judge-
          rejected retry that re-issues the same call must succeed (same rationale as book's
          idempotency), but the caller can now SAY "it was already CONFIRMED" so the model
          notices it acted on the wrong id instead of celebrating a change that never happened;
        - a **past appointment never goes (back) to PENDING/CONFIRMED** — confirming yesterday
          is meaningless; closing out the past (COMPLETED/CANCELED) stays allowed."""
        appt = self.store.get(appointment_id)
        if appt is None:
            raise SchedulerError(f"unknown appointment: {appointment_id}")
        self._authorize(appt, identity_id, role)
        status = new_status.upper()
        if status not in VALID_STATUS:
            raise SchedulerError(f"invalid status: {new_status}")
        if appt.status == status:
            return appt, False
        if status in ACTIVE_STATUS:
            try:
                appt_day = date.fromisoformat(appt.date)
            except ValueError:
                appt_day = None
            if appt_day is not None and appt_day < self._today():
                raise SchedulerError(
                    f"{appt.appointment_id} was on {appt.date} (past); a past appointment "
                    f"cannot go to {status} — mark it COMPLETED or CANCELED instead")
        appt.status = status
        self.store.update(appt)
        return appt, True

    def cancel(self, appointment_id: str, reason: str = "", *,
               identity_id: Optional[str] = None, role: Optional[str] = None,
               ) -> tuple[Appointment, bool]:
        """Cancel an active appointment. Returns ``(appt, changed)`` — mirrors ``update_status``.

        Ownership (parent parity; host-authorised) is enforced via ``_authorize``.

        Status guard — ``cancel`` was the one mutation missing it (its siblings ``reschedule``
        and ``update_status`` already guard status):
        - already CANCELED → idempotent no-op (``changed=False``), retry-safe like book /
          update_status, but the caller can now SAY "it was already canceled" so the model
          notices it acted on a stale id instead of narrating a fresh cancellation;
        - COMPLETED → refused: a finished appointment cannot be un-completed by a cancel (the
          integrity hole the parent closed by blocking terminal rows outright)."""
        appt = self.store.get(appointment_id)
        if appt is None:
            raise SchedulerError(f"unknown appointment: {appointment_id}")
        self._authorize(appt, identity_id, role)
        if appt.status == CANCELED:
            return appt, False
        if appt.status == COMPLETED:
            raise SchedulerError(
                f"{appointment_id} is COMPLETED and cannot be canceled")
        appt.status = CANCELED
        appt.cancel_reason = reason
        self.store.update(appt)
        return appt, True

    def reschedule(self, appointment_id: str, new_date: str, new_time: str, *,
                   identity_id: Optional[str] = None, role: Optional[str] = None,
                   ) -> Appointment:
        """Move an existing appointment to a new date/time in ONE atomic step (keeps the id).

        Ownership (parent parity; host-authorised) is enforced via ``_authorize``.

        This is the dedicated "remarcar" path — far more reliable than asking a model to
        orchestrate cancel + rebook, and it never leaves the client double-booked. Domain
        rules mirror book: future date, valid+free slot (a conflict carries the free slots).
        Moving to the slot it already occupies is a no-op. The appointment keeps its status
        (the host may treat a reschedule as needing re-confirmation via its own flow).
        """
        appt = self.store.get(appointment_id)
        if appt is None:
            raise SchedulerError(f"unknown appointment: {appointment_id}")
        self._authorize(appt, identity_id, role)
        if appt.status not in ACTIVE_STATUS:
            raise SchedulerError(
                f"appointment {appointment_id} is {appt.status}; only an active "
                f"appointment can be rescheduled")
        self._require_future(new_date)
        self._require_working_day(new_date)
        if new_time not in self._slots:
            raise SchedulerError(f"{new_time} is not a bookable slot")
        if (new_date, new_time) == (appt.date, appt.time):
            return appt                                       # already there → no-op
        taken = {a.time for a in self.store.list(host_id=appt.host_id)
                 if a.date == new_date and a.status in ACTIVE_STATUS
                 and a.appointment_id != appointment_id}
        if new_time in taken:
            free = [s for s in self._slots if s not in taken]
            free_txt = ", ".join(free) if free else "none that day"
            raise SchedulerError(
                f"{new_time} on {new_date} is already booked. Free slots on {new_date}: {free_txt}")
        appt.date = new_date
        appt.time = new_time
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

        Handles "hoje/today", "amanhã/tomorrow", "depois de amanhã", weekday names
        (PT + EN, with or without "próxima"/"que vem") → the NEXT occurrence of that
        weekday strictly after today (if today is that weekday, +7), AND explicit
        calendar dates — ISO (2026-07-09), numeric DAY-FIRST pt-BR (09/07, 9-7-26),
        or a named month ("9 de julho"). A bare day/month with no year rolls to the
        year that puts it today-or-later. This exists because LLM date arithmetic is
        unreliable; the model calls this instead of guessing. Raises ``SchedulerError``
        when no date can be parsed (the caller then asks the user).
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
        # Explicit calendar date (ISO / numeric dd/mm / named month) — deterministic,
        # so the model never has to interpret "09/07" itself (which made it flail).
        cal = _parse_calendar_date(e, today)
        if cal is not None:
            return cal.isoformat()
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

    def _mine(self, *, guest_id: str, with_name: str) -> list[Appointment]:
        """A client's own appointments, keyed by the STABLE ``guest_id`` when present (parent
        parity — active/cooldown checks follow the identity, not a display name), else by name."""
        if guest_id.strip():
            return self.store.list(guest_id=guest_id.strip())
        client = with_name.strip()
        return self.store.list(with_name=client) if client else []

    def _enforce_policies(self, host_id: str, iso_date: str, time: str, with_name: str,
                          *, guest_id: str = "") -> None:
        """Opt-in business guards (ported from the parent; all OFF by default so behaviour
        is unchanged unless a tenant configures them):

        - **booking window** (`booking_window_days`) — reject a date too far ahead
          (the parent's DATE_TOO_FAR; guards against an LLM weekday miscalc / abuse).
        - **single active** (`max_active_per_client`) — a client may not hold more active
          appointments than allowed (the parent's ACTIVE_APPOINTMENT_EXISTS); this is what
          stops the "same client booked at 9h AND 11h" inconsistency at the root.
        - **cooldown** (`cooldown_days`) — wait N days after the last COMPLETED appointment
          before booking again (the parent's COOLDOWN_ACTIVE).
        """
        cfg = self._config
        client = with_name.strip()
        # booking window — how far ahead a booking is allowed
        if cfg.booking_window_days > 0:
            d = date.fromisoformat(iso_date)
            max_date = self._today() + timedelta(days=cfg.booking_window_days)
            if d > max_date:
                raise SchedulerError(
                    f"{iso_date} is beyond the booking window of {cfg.booking_window_days} "
                    f"days (latest bookable date: {max_date.isoformat()})")
        if not client and not guest_id.strip():   # a block / nameless hold skips client policies
            return
        mine = [a for a in self._mine(guest_id=guest_id, with_name=with_name)
                if a.status in ACTIVE_STATUS]
        # single-active — re-booking the SAME slot is idempotent (handled later), not a 2nd
        if cfg.max_active_per_client is not None:
            already_here = any(a.host_id == host_id and a.date == iso_date and a.time == time
                               for a in mine)
            if not already_here and len(mine) >= cfg.max_active_per_client:
                ex = mine[0]
                raise SchedulerError(
                    f"{client} already has an active appointment on {ex.date} at {ex.time} "
                    f"(id {ex.appointment_id}); cancel or reschedule it before booking another")
        # cooldown — N days after the last COMPLETED appointment
        if cfg.cooldown_days > 0:
            completed = [date.fromisoformat(a.date)
                         for a in self._mine(guest_id=guest_id, with_name=with_name)
                         if a.status == COMPLETED]
            if completed:
                eligible = max(completed) + timedelta(days=cfg.cooldown_days)
                remaining = (eligible - self._today()).days
                if remaining > 0:
                    raise SchedulerError(
                        f"{client} must wait {remaining} more day(s) after the last "
                        f"appointment before booking again")

    def _require_working_day(self, iso_date: str) -> None:
        """Reject a holiday or a non-working weekday (per the tenant's config + location).
        Called after the date is already validated as a future ISO date. The error names
        the next working day so the caller can OFFER it instead of dead-ending (never
        silently book a different day than the user asked)."""
        d = date.fromisoformat(iso_date)
        working, reason = self._engine.is_working_day(d)
        if not working:
            nwd = self._engine.next_working_day(d)
            hint = f" — o próximo dia útil é {nwd.isoformat()}" if nwd else ""
            raise SchedulerError(f"{iso_date}: {reason}{hint}")

    def _require_not_past(self, iso_date: str) -> None:
        """Blocking is allowed from today on (a host can mark *today* as unavailable),
        only a strictly past date is refused — mirrors the parent's ``block_schedule``."""
        try:
            d = date.fromisoformat(iso_date)
        except ValueError as exc:
            raise SchedulerError(f"invalid date: {iso_date} (use YYYY-MM-DD)") from exc
        if d < self._today():
            raise SchedulerError(f"{iso_date} is in the past; cannot block past dates")

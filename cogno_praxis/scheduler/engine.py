"""Availability engine — pure slot computation from a tenant's schedule config.

Ported from the parent (cogno/mcp/modules/scheduler/engine.py). Computes the bookable
slots for a date respecting: working hours, lunch break, weekend rules, holidays
(country/state), slot duration. No I/O, no side effects — it reads config + existing
appointments and produces time windows.

Holidays come from one of two sources (the host decides per tenant):
  - an explicit ``holidays`` set[date] injected by the host (deterministic, dep-free), or
  - the optional ``holidays`` library via ``country``/``state`` (``pip install
    cogno-praxis[holidays]``) — graceful-degrades to "no holiday filtering" if absent.
With neither, holiday filtering is simply off (weekends still apply).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

log = logging.getLogger(__name__)


class HolidaysUnavailableError(RuntimeError):
    """Raised when a tenant configured a ``country`` (opting into holiday-aware scheduling) but
    the ``holidays`` package is not importable. We refuse to run with holiday filtering silently
    OFF — that would let the scheduler offer/book slots on a national/regional holiday. Install
    ``cogno-praxis[holidays]``. (No ``country`` set → no expectation → no error, filtering off.)
    """


class SchedulerConfig:
    """A tenant's scheduling rules (the parent's ``schedule_config`` JSONB).

    Sensible defaults so the engine works before a tenant configures anything. The default
    working day (09:00–17:00, 60-min slots, lunch 12:00–14:00) yields the classic
    09/10/11/14/15/16 slots; a real tenant overrides these via the host.
    """

    def __init__(self, raw: Optional[dict] = None) -> None:
        raw = raw or {}
        self.timezone: str = raw.get("timezone", "America/Sao_Paulo")
        self.work_start: time = self._parse_time(raw.get("work_start", "09:00"))
        self.work_end: time = self._parse_time(raw.get("work_end", "17:00"))
        self.lunch_start: time = self._parse_time(raw.get("lunch_start", "12:00"))
        self.lunch_end: time = self._parse_time(raw.get("lunch_end", "14:00"))
        self.work_saturdays: bool = raw.get("work_saturdays", False)
        self.work_sundays: bool = raw.get("work_sundays", False)
        self.slot_duration_minutes: int = int(raw.get("slot_duration_minutes", 60))
        # Business-policy knobs (enforced by the service; 0/None = disabled → no behaviour
        # change unless a tenant opts in). booking_delay_days kept for parent-config fidelity.
        self.booking_delay_days: int = int(raw.get("booking_delay_days", 0))
        self.booking_window_days: int = int(raw.get("booking_window_days", 0))
        self.cooldown_days: int = int(raw.get("cooldown_days", 0))
        _mac = raw.get("max_active_per_client")
        self.max_active_per_client: Optional[int] = int(_mac) if _mac is not None else None

    @staticmethod
    def _parse_time(value: str) -> time:
        parts = str(value).split(":")
        return time(int(parts[0]), int(parts[1]))

    def to_dict(self) -> dict:
        """Round-trippable raw form (feeds set_settings merges + get_schedule_settings)."""
        return {
            "timezone": self.timezone,
            "work_start": f"{self.work_start:%H:%M}",
            "work_end": f"{self.work_end:%H:%M}",
            "lunch_start": f"{self.lunch_start:%H:%M}",
            "lunch_end": f"{self.lunch_end:%H:%M}",
            "work_saturdays": self.work_saturdays,
            "work_sundays": self.work_sundays,
            "slot_duration_minutes": self.slot_duration_minutes,
            "booking_delay_days": self.booking_delay_days,
            "booking_window_days": self.booking_window_days,
            "cooldown_days": self.cooldown_days,
            "max_active_per_client": self.max_active_per_client,
        }

    def __repr__(self) -> str:
        return (f"SchedulerConfig(work={self.work_start:%H:%M}-{self.work_end:%H:%M}, "
                f"lunch={self.lunch_start:%H:%M}-{self.lunch_end:%H:%M}, "
                f"slot={self.slot_duration_minutes}min, sat={self.work_saturdays}, "
                f"sun={self.work_sundays})")


class Slot:
    """A single bookable time window [start, end)."""

    def __init__(self, start: time, end: time) -> None:
        self.start = start
        self.end = end

    def __repr__(self) -> str:
        return f"{self.start:%H:%M}-{self.end:%H:%M}"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Slot) and (self.start, self.end) == (other.start, other.end)

    def __hash__(self) -> int:
        return hash((self.start, self.end))


def _load_holiday_set(country: Optional[str], state: Optional[str]) -> dict[date, str]:
    """Load {date: name} for this/next year via the optional ``holidays`` lib.

    No ``country`` → filtering is simply off (empty map). But once a tenant DID configure a
    ``country`` they expect holiday-awareness, so a missing ``holidays`` package is a hard
    misconfiguration (``HolidaysUnavailableError``) rather than a silent degrade to "books on
    holidays" — that silent-off was the bug this guards against. An unsupported locale still
    degrades to empty (the lib is present; it just has no calendar for that country/state).
    """
    if not country:
        return {}
    try:
        import holidays as hol_lib
    except ImportError as exc:
        raise HolidaysUnavailableError(
            f"holiday-aware scheduling was requested (country={country!r}) but the 'holidays' "
            f"package is not installed. Install cogno-praxis[holidays]. Refusing to run with "
            f"holiday filtering silently OFF (it would offer/book slots on holidays)."
        ) from exc
    try:
        kwargs: dict = {"subdiv": state} if state else {}
        year = datetime.now().year
        hols = hol_lib.country_holidays(country, years=[year, year + 1], **kwargs)
        return {d: name for d, name in hols.items()}
    except Exception as exc:  # unsupported country/state, etc.
        log.warning("failed to load holidays for %s/%s: %s", country, state, exc)
        return {}


class AvailabilityEngine:
    """Computes available slots for a date. Stateless across queries, reusable."""

    def __init__(
        self,
        config: SchedulerConfig,
        *,
        country: Optional[str] = None,
        state: Optional[str] = None,
        holidays: Optional[Iterable[date]] = None,
    ) -> None:
        self._config = config
        if holidays is not None:
            self._holidays: dict[date, str] = {d: "Feriado" for d in holidays}
        else:
            self._holidays = _load_holiday_set(country, state)

    # ── working-day rules ──────────────────────────────────────────────
    def is_holiday(self, target_date: date) -> Optional[str]:
        """The holiday name if ``target_date`` is one, else None."""
        return self._holidays.get(target_date)

    def is_working_day(self, target_date: date) -> tuple[bool, str]:
        """(True, "") on a working day, else (False, reason) — holiday + weekend rules."""
        holiday = self.is_holiday(target_date)
        if holiday:
            return False, f"Feriado: {holiday}"
        weekday = target_date.weekday()          # 0=Mon … 5=Sat 6=Sun
        if weekday == 5 and not self._config.work_saturdays:
            return False, "não há expediente aos sábados"
        if weekday == 6 and not self._config.work_sundays:
            return False, "não há expediente aos domingos"
        return True, ""

    def next_working_day(self, from_date: date, *, inclusive: bool = False) -> Optional[date]:
        """The next working day at/after ``from_date`` (strictly after unless ``inclusive``).
        Returns None if none is found within a year (a config with no working day at all)."""
        d = from_date if inclusive else from_date + timedelta(days=1)
        for _ in range(366):
            if self.is_working_day(d)[0]:
                return d
            d += timedelta(days=1)
        return None

    # ── slot generation ────────────────────────────────────────────────
    def generate_all_slots(self) -> list[Slot]:
        """All slots of a working day: work_start→work_end by slot_duration, minus lunch."""
        slots: list[Slot] = []
        duration = timedelta(minutes=self._config.slot_duration_minutes)
        ref = datetime(2000, 1, 1)
        cur = ref.replace(hour=self._config.work_start.hour, minute=self._config.work_start.minute)
        end = ref.replace(hour=self._config.work_end.hour, minute=self._config.work_end.minute)
        lunch_a = ref.replace(hour=self._config.lunch_start.hour, minute=self._config.lunch_start.minute)
        lunch_b = ref.replace(hour=self._config.lunch_end.hour, minute=self._config.lunch_end.minute)
        while cur + duration <= end:
            nxt = cur + duration
            if not _overlaps(cur, nxt, lunch_a, lunch_b):
                slots.append(Slot(cur.time(), nxt.time()))
            cur = nxt
        return slots

    def slot_starts(self) -> list[str]:
        """The slot start times as 'HH:MM' strings (the service's interface)."""
        return [f"{s.start:%H:%M}" for s in self.generate_all_slots()]

    def get_available_slots(
        self, target_date: date, taken_starts: Optional[set[str]] = None,
    ) -> list[str]:
        """Free slot-start times for a date: [] if non-working, else all minus ``taken``."""
        working, _ = self.is_working_day(target_date)
        if not working:
            return []
        taken = taken_starts or set()
        return [s for s in self.slot_starts() if s not in taken]


def _overlaps(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    """[a0,a1) overlaps [b0,b1) ⇔ a0 < b1 and b0 < a1."""
    return a0 < b1 and b0 < a1

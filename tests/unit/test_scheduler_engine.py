"""Unit tests for the AvailabilityEngine + SchedulerConfig (pure, no I/O)."""

from datetime import date

import pytest

from cogno_praxis.scheduler import (
    AvailabilityEngine,
    Host,
    InMemoryAppointmentStore,
    SchedulerConfig,
    SchedulerError,
    SchedulerService,
)

# A fixed clock (2026-06-30 is a Tuesday) so weekday-derived dates below are deterministic.
_TODAY = date(2026, 6, 30)
_WED = "2026-07-01"
_SAT = "2026-07-04"
_SUN = "2026-07-05"


def test_default_config_yields_classic_slots():
    eng = AvailabilityEngine(SchedulerConfig())
    assert eng.slot_starts() == ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]


def test_custom_hours_and_duration():
    cfg = SchedulerConfig({"work_start": "08:00", "work_end": "10:00",
                           "lunch_start": "00:00", "lunch_end": "00:00",
                           "slot_duration_minutes": 30})
    assert AvailabilityEngine(cfg).slot_starts() == ["08:00", "08:30", "09:00", "09:30"]


def test_lunch_break_is_excluded():
    cfg = SchedulerConfig({"work_start": "11:00", "work_end": "15:00",
                           "lunch_start": "12:00", "lunch_end": "14:00",
                           "slot_duration_minutes": 60})
    # 11–12 ok, 12–13 & 13–14 overlap lunch, 14–15 ok
    assert AvailabilityEngine(cfg).slot_starts() == ["11:00", "14:00"]


def test_weekend_is_non_working_by_default():
    eng = AvailabilityEngine(SchedulerConfig())
    assert eng.is_working_day(date.fromisoformat(_SAT))[0] is False
    assert eng.is_working_day(date.fromisoformat(_SUN))[0] is False
    assert eng.is_working_day(date.fromisoformat(_WED))[0] is True


def test_work_saturdays_flag_opens_saturday():
    eng = AvailabilityEngine(SchedulerConfig({"work_saturdays": True}))
    assert eng.is_working_day(date.fromisoformat(_SAT)) == (True, "")


def test_injected_holiday_blocks_the_day():
    eng = AvailabilityEngine(SchedulerConfig(), holidays={date.fromisoformat(_WED)})
    working, reason = eng.is_working_day(date.fromisoformat(_WED))
    assert working is False and "Feriado" in reason
    assert eng.get_available_slots(date.fromisoformat(_WED)) == []


def test_get_available_slots_filters_taken():
    eng = AvailabilityEngine(SchedulerConfig())
    free = eng.get_available_slots(date.fromisoformat(_WED), taken_starts={"09:00"})
    assert "09:00" not in free and "10:00" in free


# ── service-level: the engine's working-day rules reach book/availability ──
def _svc(**kw):
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    return SchedulerService(store, today=lambda: _TODAY, **kw)


def test_book_on_weekend_is_rejected():
    with pytest.raises(SchedulerError, match="domingo"):
        _svc().book("dr_silva", _SUN, "09:00", "Ana")
    with pytest.raises(SchedulerError, match="sábado|sabado|expediente"):
        _svc().book("dr_silva", _SAT, "09:00", "Ana")


def test_book_on_holiday_is_rejected():
    svc = _svc(holidays={date.fromisoformat(_WED)})
    with pytest.raises(SchedulerError, match="Feriado"):
        svc.book("dr_silva", _WED, "09:00", "Ana")


def test_availability_reflects_tenant_config_slots():
    cfg = SchedulerConfig({"work_start": "08:00", "work_end": "10:00",
                           "lunch_start": "00:00", "lunch_end": "00:00",
                           "slot_duration_minutes": 60})
    svc = _svc(config=cfg)
    assert svc.check_availability("dr_silva", _WED) == ["08:00", "09:00"]

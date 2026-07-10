"""Unit tests for the AvailabilityEngine + SchedulerConfig (pure, no I/O)."""

import sys
from datetime import date

import pytest

from cogno_praxis.scheduler import (
    AvailabilityEngine,
    HolidaysUnavailableError,
    Host,
    InMemoryAppointmentStore,
    SchedulerConfig,
    SchedulerError,
    SchedulerService,
)
from cogno_praxis.scheduler.store import COMPLETED, Appointment

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


# ── the REAL production path: country/state → the `holidays` lib (not an injected set) ──
# This is the path the host actually uses (it passes the tenant's country/state, never a set),
# so it must be exercised directly — the injected-set tests above bypass `import holidays`.
def test_country_state_loads_real_holidays_from_the_lib():
    pytest.importorskip("holidays")  # skip LOUDLY if the extra is absent (never a silent pass)
    eng = AvailabilityEngine(SchedulerConfig(), country="BR", state="SP")
    # 2026-09-07 is Brazil's Independence Day (a Monday — so weekends can't explain the block).
    working, reason = eng.is_working_day(date(2026, 9, 7))
    assert working is False and "Feriado" in reason
    assert eng.get_available_slots(date(2026, 9, 7)) == []
    assert eng.is_working_day(date(2026, 9, 8))[0] is True  # the Tuesday after is a working day


def test_missing_holidays_lib_with_country_raises_not_degrades(monkeypatch):
    # A tenant configured a country (opted into holiday-awareness) but the package is missing:
    # this MUST fail loudly, not silently book on holidays. Force `import holidays` to fail.
    monkeypatch.setitem(sys.modules, "holidays", None)
    with pytest.raises(HolidaysUnavailableError, match="cogno-praxis\\[holidays\\]"):
        AvailabilityEngine(SchedulerConfig(), country="BR", state="SP")


def test_no_country_never_raises_even_without_the_lib(monkeypatch):
    # No country → no holiday expectation → filtering is simply off, and weekends still apply.
    monkeypatch.setitem(sys.modules, "holidays", None)
    eng = AvailabilityEngine(SchedulerConfig())              # no country, no lib → fine
    assert eng.is_working_day(date.fromisoformat(_WED))[0] is True
    assert eng.is_working_day(date.fromisoformat(_SAT))[0] is False  # weekend rule needs no lib


def test_get_available_slots_filters_taken():
    eng = AvailabilityEngine(SchedulerConfig())
    free = eng.get_available_slots(date.fromisoformat(_WED), taken_starts={"09:00"})
    assert "09:00" not in free and "10:00" in free


def test_next_working_day_skips_weekends_and_holidays():
    eng = AvailabilityEngine(SchedulerConfig())
    # Fri 2026-07-03 → next working strictly after is Mon 2026-07-06 (skips Sat+Sun)
    assert eng.next_working_day(date(2026, 7, 3)) == date(2026, 7, 6)
    assert eng.next_working_day(date.fromisoformat(_SAT)) == date(2026, 7, 6)
    assert eng.next_working_day(date.fromisoformat(_SUN)) == date(2026, 7, 6)
    assert eng.next_working_day(date.fromisoformat(_WED)) == date(2026, 7, 2)  # Wed → Thu
    # inclusive: a working day maps to itself; a weekend rolls forward
    assert eng.next_working_day(date.fromisoformat(_WED), inclusive=True) == date.fromisoformat(_WED)
    assert eng.next_working_day(date.fromisoformat(_SUN), inclusive=True) == date(2026, 7, 6)
    # a holiday is skipped too
    eng_h = AvailabilityEngine(SchedulerConfig(), holidays={date(2026, 7, 2)})
    assert eng_h.next_working_day(date.fromisoformat(_WED)) == date(2026, 7, 3)  # Thu is holiday → Fri


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


def test_non_working_day_error_names_the_next_working_day():
    # The error must be ACTIONABLE — it names the next working day so the model offers it
    # instead of proposing an impossible slot / dead-ending.
    svc = _svc()
    with pytest.raises(SchedulerError, match="2026-07-06"):   # Sun 05/07 → Mon 06/07
        svc.check_availability("dr_silva", _SUN)
    with pytest.raises(SchedulerError, match="2026-07-06"):
        svc.book("dr_silva", _SAT, "09:00", "Ana")


def test_availability_reflects_tenant_config_slots():
    cfg = SchedulerConfig({"work_start": "08:00", "work_end": "10:00",
                           "lunch_start": "00:00", "lunch_end": "00:00",
                           "slot_duration_minutes": 60})
    svc = _svc(config=cfg)
    assert svc.check_availability("dr_silva", _WED) == ["08:00", "09:00"]


# ── Phase B: opt-in business-policy guards (all OFF by default) ─────────────
def test_policies_off_by_default_allow_multiple_bookings():
    svc = _svc()                                 # default config → no policy guards
    svc.book("dr_silva", _WED, "09:00", "Ana")
    svc.book("dr_silva", _WED, "11:00", "Ana")   # 2nd active for Ana → allowed (guard off)
    assert len(svc.list_appointments(with_name="Ana")) == 2


def test_booking_window_rejects_far_dates():
    svc = _svc(config=SchedulerConfig({"booking_window_days": 5}))  # today = 2026-06-30
    svc.book("dr_silva", "2026-07-02", "09:00", "Ana")             # within window → ok
    with pytest.raises(SchedulerError, match="beyond the booking window"):
        svc.book("dr_silva", "2026-07-10", "09:00", "Ana")        # > 5 days → DATE_TOO_FAR


def test_single_active_blocks_second_appointment():
    svc = _svc(config=SchedulerConfig({"max_active_per_client": 1}))
    svc.book("dr_silva", _WED, "09:00", "Ana")
    with pytest.raises(SchedulerError, match="already has an active appointment"):
        svc.book("dr_silva", _WED, "11:00", "Ana")                # 2nd active for Ana → blocked
    # re-booking the SAME slot is still idempotent (not a 2nd active)
    assert svc.book("dr_silva", _WED, "09:00", "Ana").time == "09:00"
    # a different client is unaffected
    svc.book("dr_silva", _WED, "11:00", "Bob")


def test_single_active_lets_you_rebook_after_cancel():
    svc = _svc(config=SchedulerConfig({"max_active_per_client": 1}))
    a = svc.book("dr_silva", _WED, "09:00", "Ana")
    svc.cancel(a.appointment_id)                                   # frees the active slot
    svc.book("dr_silva", _WED, "11:00", "Ana")                    # now allowed


def test_get_and_set_settings_rebuild_slots():
    svc = _svc()
    assert svc.get_settings()["work_start"] == "09:00"
    assert "08:00" not in svc._slots
    updated = svc.set_settings(work_start="08:00", slot_duration_minutes=60)
    assert updated["work_start"] == "08:00"
    assert "08:00" in svc.check_availability("dr_silva", _WED)   # engine recomputed


def test_set_settings_invalid_value_raises():
    with pytest.raises(SchedulerError, match="invalid schedule settings"):
        _svc().set_settings(work_start="notatime")


def test_set_settings_only_changes_passed_fields():
    svc = _svc()
    svc.set_settings(work_saturdays=True)
    s = svc.get_settings()
    assert s["work_saturdays"] is True and s["work_start"] == "09:00"   # rest untouched


def test_set_auto_confirm_toggles_booking_status():
    svc = _svc()
    svc.set_auto_confirm("dr_silva", False)
    assert svc.book("dr_silva", _WED, "09:00", "Ana").status == "PENDING"
    svc.set_auto_confirm("dr_silva", True)
    assert svc.book("dr_silva", _WED, "10:00", "Bob").status == "CONFIRMED"


def test_set_auto_confirm_unknown_host_raises():
    with pytest.raises(SchedulerError, match="unknown host"):
        _svc().set_auto_confirm("ghost", False)


def test_cooldown_blocks_until_elapsed():
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    # a COMPLETED appointment 2 days ago (relative to _TODAY = 2026-06-30)
    store.add(Appointment(appointment_id="old1", host_id="dr_silva", date="2026-06-28",
                          time="09:00", with_name="Ana", status=COMPLETED))
    svc = SchedulerService(store, today=lambda: _TODAY,
                           config=SchedulerConfig({"cooldown_days": 5}))
    with pytest.raises(SchedulerError, match="must wait .* day"):
        svc.book("dr_silva", _WED, "09:00", "Ana")               # 06-28 + 5 = 07-03 > today
    # without the cooldown guard the same booking is fine
    svc2 = SchedulerService(store, today=lambda: _TODAY)
    assert svc2.book("dr_silva", _WED, "10:00", "Ana").time == "10:00"

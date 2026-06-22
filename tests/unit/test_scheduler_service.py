"""Unit tests for the scheduler domain logic (service + store), no MCP."""

from datetime import date

import pytest

from cogno_praxis.scheduler import (
    Host,
    InMemoryAppointmentStore,
    SchedulerError,
    SchedulerService,
)
from cogno_praxis.scheduler.store import CANCELED, COMPLETED, CONFIRMED, PENDING

# A fixed "today" so the "start from tomorrow" rule is deterministic; the test dates
# below (2026-07-xx) are comfortably in the future relative to it.
_TODAY = date(2026, 6, 30)


def _svc():
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    return SchedulerService(store, today=lambda: _TODAY)


def test_list_hosts():
    svc = _svc()
    assert [h.host_id for h in svc.list_hosts()] == ["dr_silva"]


def test_availability_all_slots_when_empty():
    svc = _svc()
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert free == list(svc._slots)


def test_availability_unknown_host_raises():
    with pytest.raises(SchedulerError, match="unknown host"):
        _svc().check_availability("ghost", "2026-07-01")


def test_book_then_slot_disappears():
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    assert appt.status == PENDING
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")


def test_book_unknown_host_raises():
    with pytest.raises(SchedulerError, match="unknown host"):
        _svc().book("ghost", "2026-07-01", "09:00", "Ana")


def test_book_invalid_slot_raises():
    with pytest.raises(SchedulerError, match="not a bookable slot"):
        _svc().book("dr_silva", "2026-07-01", "03:00", "Ana")


def test_double_booking_raises():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    with pytest.raises(SchedulerError, match="already booked"):
        svc.book("dr_silva", "2026-07-01", "09:00", "Bob")


def test_same_slot_different_date_ok():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    appt = svc.book("dr_silva", "2026-07-02", "09:00", "Bob")
    assert appt.date == "2026-07-02"


def test_list_appointments_filters():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    svc.book("dr_silva", "2026-07-01", "10:00", "Bob")
    assert len(svc.list_appointments()) == 2
    assert len(svc.list_appointments(with_name="ana")) == 1   # case-insensitive


def test_cancel_frees_the_slot():
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    cancelled = svc.cancel(appt.appointment_id, reason="patient request")
    assert cancelled.status == CANCELED
    assert cancelled.cancel_reason == "patient request"
    assert "09:00" in svc.check_availability("dr_silva", "2026-07-01")


def test_cancel_unknown_raises():
    with pytest.raises(SchedulerError, match="unknown appointment"):
        _svc().cancel("nope")


def test_update_status_lifecycle():
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    assert svc.update_status(appt.appointment_id, "confirmed").status == CONFIRMED
    assert svc.update_status(appt.appointment_id, "COMPLETED").status == COMPLETED
    # a COMPLETED appointment frees the slot again
    assert "09:00" in svc.check_availability("dr_silva", "2026-07-01")


def test_update_status_invalid_raises():
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    with pytest.raises(SchedulerError, match="invalid status"):
        svc.update_status(appt.appointment_id, "MAYBE")


def test_update_status_unknown_appointment_raises():
    with pytest.raises(SchedulerError, match="unknown appointment"):
        _svc().update_status("nope", "CONFIRMED")


def test_book_today_or_past_raises():
    svc = _svc()
    with pytest.raises(SchedulerError, match="starts from tomorrow"):
        svc.book("dr_silva", _TODAY.isoformat(), "09:00", "Ana")
    with pytest.raises(SchedulerError, match="starts from tomorrow"):
        svc.book("dr_silva", "2026-06-01", "09:00", "Ana")


def test_availability_today_or_past_raises():
    with pytest.raises(SchedulerError, match="starts from tomorrow"):
        _svc().check_availability("dr_silva", _TODAY.isoformat())


def test_book_malformed_date_raises():
    with pytest.raises(SchedulerError, match="invalid date"):
        _svc().book("dr_silva", "07/01/2026", "09:00", "Ana")


def test_resolve_date_relative():
    svc = _svc()  # today = 2026-06-30 (Tuesday)
    assert svc.resolve_date("amanhã") == "2026-07-01"
    assert svc.resolve_date("tomorrow") == "2026-07-01"
    assert svc.resolve_date("depois de amanhã") == "2026-07-02"
    assert svc.resolve_date("hoje") == "2026-06-30"


def test_resolve_date_weekdays():
    svc = _svc()  # today = 2026-06-30 (Tuesday, weekday=1)
    assert svc.resolve_date("próxima sexta-feira") == "2026-07-03"   # Fri
    assert svc.resolve_date("sexta que vem") == "2026-07-03"
    assert svc.resolve_date("quarta") == "2026-07-01"                 # Wed (next day)
    assert svc.resolve_date("segunda") == "2026-07-06"               # next Monday
    # today is Tuesday → "terça" means the NEXT one, +7
    assert svc.resolve_date("terça") == "2026-07-07"


def test_resolve_date_unparseable_raises():
    with pytest.raises(SchedulerError, match="could not resolve"):
        _svc().resolve_date("qualquer coisa sem data")


def test_store_is_injectable_port():
    assert isinstance(InMemoryAppointmentStore(), __import__(
        "cogno_praxis.scheduler.store", fromlist=["AppointmentStore"]).AppointmentStore)

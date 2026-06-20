"""Unit tests for the SECRETARY domain logic (service + store), no MCP."""

import pytest

from cogno_praxis.secretary import (
    Host,
    InMemoryAppointmentStore,
    SecretaryError,
    SecretaryService,
)


def _svc():
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    return SecretaryService(store)


def test_list_hosts():
    svc = _svc()
    assert [h.host_id for h in svc.list_hosts()] == ["dr_silva"]


def test_availability_all_slots_when_empty():
    svc = _svc()
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert free == list(svc._slots)


def test_availability_unknown_host_raises():
    with pytest.raises(SecretaryError, match="unknown host"):
        _svc().check_availability("ghost", "2026-07-01")


def test_book_then_slot_disappears():
    svc = _svc()
    appt = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    assert appt.status == "booked"
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")


def test_book_unknown_host_raises():
    with pytest.raises(SecretaryError, match="unknown host"):
        _svc().book("ghost", "2026-07-01", "09:00", "Ana")


def test_book_invalid_slot_raises():
    with pytest.raises(SecretaryError, match="not a bookable slot"):
        _svc().book("dr_silva", "2026-07-01", "03:00", "Ana")


def test_double_booking_raises():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    with pytest.raises(SecretaryError, match="already booked"):
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
    cancelled = svc.cancel(appt.appointment_id)
    assert cancelled.status == "cancelled"
    assert "09:00" in svc.check_availability("dr_silva", "2026-07-01")


def test_cancel_unknown_raises():
    with pytest.raises(SecretaryError, match="unknown appointment"):
        _svc().cancel("nope")


def test_store_is_injectable_port():
    assert isinstance(InMemoryAppointmentStore(), __import__(
        "cogno_praxis.secretary.store", fromlist=["AppointmentStore"]).AppointmentStore)

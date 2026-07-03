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
    assert appt.status == CONFIRMED          # dr_silva auto_confirms (default)
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")


def test_book_resolves_a_name_slug_host_id():
    # a small model invents 'dr_jose_luiz_manzoli' instead of the catalog id (a numeric user_id);
    # fuzzy resolution matches it by normalized name so the booking still lands on the real host
    store = InMemoryAppointmentStore()
    store.hosts["8443"] = Host("8443", "Dr. José Luiz Manzoli", "Endócrino")
    svc = SchedulerService(store, today=lambda: _TODAY)
    appt = svc.book("dr_jose_luiz_manzoli", "2026-07-01", "09:00", "Ana")
    assert appt.host_id == "8443"            # resolved to the real catalog id
    # and availability accepts the slug too
    assert "09:00" not in svc.check_availability("dr_jose_luiz_manzoli", "2026-07-01")
    # a genuinely unknown host still errors
    with pytest.raises(SchedulerError, match="unknown host"):
        svc.book("ghost_doctor", "2026-07-01", "10:00", "Ana")


def test_book_resolves_a_single_specialty():
    # "marca com o cardiologista" is valid when exactly one host has that specialty (role).
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Vinicius Vale", "Cardiologista")
    store.hosts["dr_m"] = Host("dr_m", "Dr. Manzoli", "Endócrino")
    svc = SchedulerService(store, today=lambda: _TODAY)
    appt = svc.book("cardiologista", "2026-07-01", "09:00", "Ana")
    assert appt.host_id == "dr_silva"        # the one cardiologist
    assert "09:00" not in svc.check_availability("dr_silva", "2026-07-01")  # slot now taken


def test_ambiguous_specialty_stays_unresolved():
    # two cardiologists → the specialty is ambiguous; do NOT guess (the caller lists + user picks).
    store = InMemoryAppointmentStore()
    store.hosts["dr_a"] = Host("dr_a", "Dr. A", "Cardiologista")
    store.hosts["dr_b"] = Host("dr_b", "Dr. B", "Cardiologista")
    svc = SchedulerService(store, today=lambda: _TODAY)
    with pytest.raises(SchedulerError, match="unknown host"):
        svc.book("cardiologista", "2026-07-01", "09:00", "Ana")


def test_auto_confirm_false_keeps_pending():
    store = InMemoryAppointmentStore()
    store.hosts["dr_x"] = Host("dr_x", "Dr. X", "GP", auto_confirm=False)
    svc = SchedulerService(store, today=lambda: _TODAY)
    appt = svc.book("dr_x", "2026-07-01", "09:00", "Ana")
    assert appt.status == PENDING            # waits for the professional to accept
    accepted = svc.update_status(appt.appointment_id, "CONFIRMED")
    assert accepted.status == CONFIRMED


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


def test_book_is_idempotent_for_same_client():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    b = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")     # identical → returns existing
    assert b.appointment_id == a.appointment_id
    assert len(svc.list_appointments()) == 1                   # not duplicated
    # a DIFFERENT client at the same slot still conflicts
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


def test_reschedule_moves_slot_keeps_id():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    moved = svc.reschedule(a.appointment_id, "2026-07-01", "11:00")
    assert moved.appointment_id == a.appointment_id          # same appointment
    assert (moved.date, moved.time) == ("2026-07-01", "11:00")
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert "09:00" in free and "11:00" not in free           # old freed, new taken


def test_reschedule_to_taken_slot_errors_with_alternatives():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    svc.book("dr_silva", "2026-07-01", "11:00", "Bob")
    with pytest.raises(SchedulerError, match="already booked. Free slots"):
        svc.reschedule(a.appointment_id, "2026-07-01", "11:00")


def test_reschedule_same_slot_is_noop():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    same = svc.reschedule(a.appointment_id, "2026-07-01", "09:00")
    assert same.appointment_id == a.appointment_id


def test_reschedule_unknown_raises():
    with pytest.raises(SchedulerError, match="unknown appointment"):
        _svc().reschedule("nope", "2026-07-01", "11:00")


def test_reschedule_past_date_raises():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    with pytest.raises(SchedulerError, match="starts from tomorrow"):
        svc.reschedule(a.appointment_id, _TODAY.isoformat(), "11:00")


def test_reschedule_canceled_appointment_raises():
    svc = _svc()
    a = svc.book("dr_silva", "2026-07-01", "09:00", "Ana")
    svc.cancel(a.appointment_id)
    with pytest.raises(SchedulerError, match="only an active"):
        svc.reschedule(a.appointment_id, "2026-07-01", "11:00")


def test_block_whole_day_removes_all_slots():
    svc = _svc()
    blocks = svc.block_schedule("dr_silva", "2026-07-01")
    assert len(blocks) == len(svc._slots)
    assert all(b.is_block and b.status == CONFIRMED for b in blocks)
    assert svc.check_availability("dr_silva", "2026-07-01") == []


def test_block_single_slot():
    svc = _svc()
    svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00")
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert "09:00" not in free and "10:00" in free


def test_block_time_range():
    svc = _svc()
    svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00", end_time="11:00")
    free = svc.check_availability("dr_silva", "2026-07-01")
    assert "09:00" not in free and "10:00" not in free   # [09:00, 11:00)
    assert "11:00" in free                                # end is exclusive


def test_block_refuses_when_client_booked_in_range():
    svc = _svc()
    svc.book("dr_silva", "2026-07-01", "10:00", "Ana")
    with pytest.raises(SchedulerError, match="client appointments exist"):
        svc.block_schedule("dr_silva", "2026-07-01")        # whole day clashes with Ana@10:00


def test_block_is_idempotent():
    svc = _svc()
    first = svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00")
    second = svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00")
    assert len(first) == 1 and second == []                 # already blocked → skipped


def test_block_allows_today_but_not_past():
    svc = _svc()  # today = 2026-06-30
    # blocking today is allowed (a host can mark today unavailable), unlike booking
    assert svc.block_schedule("dr_silva", _TODAY.isoformat(), start_time="09:00")
    with pytest.raises(SchedulerError, match="in the past"):
        svc.block_schedule("dr_silva", "2026-06-01")


def test_block_unknown_host_raises():
    with pytest.raises(SchedulerError, match="unknown host"):
        _svc().block_schedule("ghost", "2026-07-01")


def test_block_invalid_single_slot_raises():
    with pytest.raises(SchedulerError, match="not a bookable slot"):
        _svc().block_schedule("dr_silva", "2026-07-01", start_time="03:00")


def test_block_empty_range_raises():
    with pytest.raises(SchedulerError, match="no bookable slots"):
        _svc().block_schedule("dr_silva", "2026-07-01", start_time="12:00", end_time="13:00")


def test_block_does_not_appear_as_client_booking():
    svc = _svc()
    svc.block_schedule("dr_silva", "2026-07-01", start_time="09:00")
    # a block carries no client name → filtering by a real name never returns it
    assert svc.list_appointments(with_name="Ana") == []
    blocks = [a for a in svc.list_appointments() if a.is_block]
    assert len(blocks) == 1


def test_resolve_date_unparseable_raises():
    with pytest.raises(SchedulerError, match="could not resolve"):
        _svc().resolve_date("qualquer coisa sem data")


def test_store_is_injectable_port():
    assert isinstance(InMemoryAppointmentStore(), __import__(
        "cogno_praxis.scheduler.store", fromlist=["AppointmentStore"]).AppointmentStore)

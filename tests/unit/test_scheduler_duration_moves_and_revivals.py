"""A booking that MOVES or COMES BACK re-occupies its whole interval — guarded like a new one.

A reschedule and a revival (a status back to the live agenda) write an interval just as a booking
does, so they go through the same overlap guard: the store's ``update_if_free`` (on Postgres, under
the same per-professional/day advisory lock as ``add_if_free``). A revival checks by INTERVAL, not
by equal start. And a service start that cannot hold the service's whole duration (lunch, end of
day, off the grid) is refused WITH the starts where it fits. Without a catalog, every message is the
fixed-slot one of before, byte for byte. Every name here is invented.
"""
from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.scheduler.catalog import KIND_SERVICE, CatalogItem
from cogno_praxis.scheduler.engine import SchedulerConfig
from cogno_praxis.scheduler.service import SchedulerError, SchedulerService
from cogno_praxis.scheduler.store import (
    ACTIVE_STATUS,
    CANCELED,
    Appointment,
    Host,
    InMemoryAppointmentStore,
    SlotTakenError,
)

TODAY = date(2026, 7, 6)          # a Monday
TOMORROW = "2026-07-07"           # a Tuesday
LATER = "2026-07-08"              # a Wednesday


def _service(name: str, minutes: int) -> CatalogItem:
    return CatalogItem(item_id=f"service:{name}", kind=KIND_SERVICE, name=name,
                       value_text="R$ 75,00", duration_minutes=minutes, all_hosts=True)


class _CountingStore(InMemoryAppointmentStore):
    """Counts which write door the service takes."""

    def __init__(self) -> None:
        super().__init__()
        self.guarded_updates = 0
        self.plain_updates = 0

    def update_if_free(self, appointment: Appointment, *, slot_minutes: int) -> None:
        self.guarded_updates += 1
        super().update_if_free(appointment, slot_minutes=slot_minutes)

    def update(self, appointment: Appointment) -> None:
        self.plain_updates += 1
        super().update(appointment)


def _svc(catalog=(), store=None):
    st = store if store is not None else InMemoryAppointmentStore()
    st.put_host(Host(host_id="pro_quintino", name="Quintino Abravel"))
    return st, SchedulerService(st, config=SchedulerConfig(), today=lambda: TODAY,
                                catalog=catalog or ())


_CATALOG = (_service("Coloração Vendrim", 120), _service("Manicure Ostral", 30))


def _active(st):
    return sorted((a.time, a.duration_minutes) for a in st.appointments.values()
                  if a.status in ACTIVE_STATUS)


# ── a revival re-occupies its whole interval ────────────────────────────────────────────────
def test_a_revived_long_booking_cannot_land_on_one_made_inside_its_interval():
    st, svc = _svc(_CATALOG)
    x = svc.book("pro_quintino", TOMORROW, "10:00", "Belmira Quostral",
                 service_id="service:Coloração Vendrim")
    svc.cancel(x.appointment_id, "mudou de ideia")
    svc.book("pro_quintino", TOMORROW, "11:00", "Odilse Ferrantim",
             service_id="service:Manicure Ostral")
    with pytest.raises(SchedulerError, match="cannot return to the agenda"):
        svc.update_status(x.appointment_id, "CONFIRMED")
    assert _active(st) == [("11:00", 30)]                      # no overlap survives
    assert st.appointments[x.appointment_id].status == CANCELED


def test_control_a_revival_with_nothing_in_its_interval_returns():
    st, svc = _svc(_CATALOG)
    x = svc.book("pro_quintino", TOMORROW, "10:00", "Belmira Quostral",
                 service_id="service:Coloração Vendrim")
    svc.cancel(x.appointment_id, "mudou de ideia")
    svc.book("pro_quintino", TOMORROW, "14:00", "Odilse Ferrantim",
             service_id="service:Manicure Ostral")
    appt, changed = svc.update_status(x.appointment_id, "CONFIRMED")
    assert changed and appt.status == "CONFIRMED"
    assert _active(st) == [("10:00", 120), ("14:00", 30)]


# ── moves and revivals take the guarded write; a routine confirm does not ───────────────────
def test_a_reschedule_and_a_revival_write_through_update_if_free():
    store = _CountingStore()
    st, svc = _svc(_CATALOG, store)
    x = svc.book("pro_quintino", TOMORROW, "10:00", "Belmira Quostral",
                 service_id="service:Coloração Vendrim")
    svc.reschedule(x.appointment_id, LATER, "14:00")
    assert (store.guarded_updates, store.plain_updates) == (1, 0)
    svc.cancel(x.appointment_id, "mudou de ideia")
    plain_after_cancel = store.plain_updates
    svc.update_status(x.appointment_id, "CONFIRMED")
    assert store.guarded_updates == 2 and store.plain_updates == plain_after_cancel


def test_control_a_routine_confirm_keeps_the_plain_update():
    store = _CountingStore()
    st, svc = _svc(_CATALOG, store)
    st.put_host(Host(host_id="pro_quintino", name="Quintino Abravel", auto_confirm=False))
    x = svc.book("pro_quintino", TOMORROW, "10:00", "Belmira Quostral",
                 service_id="service:Coloração Vendrim")
    assert x.status == "PENDING"                    # the professional does not auto-confirm
    svc.update_status(x.appointment_id, "CONFIRMED")
    assert store.guarded_updates == 0 and store.plain_updates == 1


def test_the_in_memory_update_if_free_refuses_an_overlapping_move():
    st, svc = _svc(_CATALOG)
    a = svc.book("pro_quintino", TOMORROW, "10:00", "Belmira Quostral",
                 service_id="service:Coloração Vendrim")
    b = svc.book("pro_quintino", TOMORROW, "14:00", "Odilse Ferrantim",
                 service_id="service:Manicure Ostral")
    moved = Appointment(**{**b.__dict__, "time": "11:00"})       # bypass the service pre-check
    with pytest.raises(SlotTakenError):
        st.update_if_free(moved, slot_minutes=60)
    assert st.appointments[b.appointment_id].time == "14:00"
    gone = Appointment(**{**b.__dict__, "time": "11:00", "status": CANCELED})
    st.update_if_free(gone, slot_minutes=60)                    # inactive occupies nothing
    assert st.appointments[b.appointment_id].status == CANCELED
    assert a.appointment_id in st.appointments


# ── a service start that cannot hold the duration says where it fits ─────────────────────────
def test_a_service_start_that_would_cross_lunch_is_refused_with_where_it_fits():
    st, svc = _svc(_CATALOG)
    with pytest.raises(SchedulerError) as exc:
        svc.book("pro_quintino", TOMORROW, "11:00", "Belmira Quostral",
                 service_id="service:Coloração Vendrim")
    msg = str(exc.value)
    assert "Starts where it fits" in msg and "10:00" in msg and "14:00" in msg
    assert "11:00," not in msg.split("Starts where it fits", 1)[1]
    assert st.appointments == {}


def test_a_long_reschedule_onto_lunch_is_refused_with_where_it_fits():
    st, svc = _svc(_CATALOG)
    x = svc.book("pro_quintino", TOMORROW, "09:00", "Belmira Quostral",
                 service_id="service:Coloração Vendrim")
    with pytest.raises(SchedulerError) as exc:
        svc.reschedule(x.appointment_id, LATER, "11:00")
    assert "Starts where it fits" in str(exc.value)
    assert st.appointments[x.appointment_id].time == "09:00"


def test_control_without_a_catalog_the_not_bookable_message_is_the_old_one():
    st, svc = _svc(())
    with pytest.raises(SchedulerError) as exc:
        svc.book("pro_quintino", TOMORROW, "11:30", "Belmira Quostral")
    assert str(exc.value) == "11:30 is not a bookable slot"

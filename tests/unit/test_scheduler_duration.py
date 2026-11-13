"""The agenda books by a SERVICE's DURATION, per professional.

Deterministic, no model: a service occupies its whole interval (a 2-hour colour takes two hours),
conflict is OVERLAP of intervals (not an equal start), the grid of starts is 30-minute-spaced and
never straddles lunch, each professional's day is independent, and a professional is refused a
service they do not perform — with the list of who does. Without a catalog the agenda is byte for
byte the fixed-slot behaviour it had before.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.scheduler.catalog import KIND_SERVICE, CatalogItem
from cogno_praxis.scheduler.engine import SchedulerConfig
from cogno_praxis.scheduler.service import SchedulerError, SchedulerService
from cogno_praxis.scheduler.store import Host, InMemoryAppointmentStore

TODAY = date(2026, 7, 6)          # a Monday
TOMORROW = "2026-07-07"           # a Tuesday — a working day
LATER = "2026-07-08"              # a Wednesday


def _service(name, minutes, host_ids=(), *, all_hosts=False):
    return CatalogItem(item_id=f"service:{name}", kind=KIND_SERVICE, name=name,
                       value_text="R$ 260,00", duration_minutes=minutes,
                       all_hosts=all_hosts, host_ids=tuple(host_ids))


def _svc(catalog=(), *, hosts=(("krusvel", "Ulpiano Krusvel"), ("simbroe", "Draventa Simbroe"))):
    store = InMemoryAppointmentStore()
    for hid, name in hosts:
        store.put_host(Host(host_id=hid, name=name))
    return SchedulerService(store, config=SchedulerConfig(), today=lambda: TODAY,
                            catalog=catalog or ())


# ── fitting_starts: a service occupies its whole interval, clear of lunch ────────────────────
def test_two_hour_service_does_not_start_where_it_would_hit_lunch_or_overrun():
    svc = _svc([_service("coloracao", 120, ["krusvel"])])
    free = svc.check_availability("krusvel", TOMORROW, service_id="service:coloracao")
    # 09:00/09:30/10:00 fit before lunch (10:00→10:00-12:00 touches but does not cross);
    # 10:30/11:00/11:30 would run into lunch (12:00-14:00) → not offered; 14:00/14:30/15:00 fit
    # after it; 15:30 would overrun 17:00.
    assert "10:00" in free and "11:00" not in free
    assert "15:00" in free and "15:30" not in free
    assert free == ["09:00", "09:30", "10:00", "14:00", "14:30", "15:00"]


def test_booking_a_two_hour_service_removes_both_hours_it_covers():
    svc = _svc([_service("coloracao", 120, ["krusvel"]),
                _service("manicure", 30, ["krusvel", "simbroe"])])
    appt = svc.book("krusvel", TOMORROW, "10:00", "Belmira Quostral Vendrim",
                    service_id="service:coloracao")
    assert appt.duration_minutes == 120 and appt.service_id == "service:coloracao"
    assert appt.value_text == "R$ 260,00"
    # A 30-min manicure anywhere inside the colour's 10:00-12:00 interval is gone; the starts
    # before it (09:00, 09:30, the last ending at 10:00) stay clear.
    free_manicure = svc.check_availability("krusvel", TOMORROW, service_id="service:manicure")
    assert {"10:00", "10:30", "11:00", "11:30"}.isdisjoint(free_manicure)
    assert "09:00" in free_manicure and "09:30" in free_manicure


def test_overlapping_durations_from_different_starts_conflict():
    svc = _svc([_service("coloracao", 120, ["krusvel"]),
                _service("manicure", 30, ["krusvel", "simbroe"])])
    svc.book("krusvel", TOMORROW, "10:00", "Belmira Quostral Vendrim", service_id="service:coloracao")
    # 10:30 is a valid start for a 30-min service, but it lands inside the 10:00-12:00 colour.
    with pytest.raises(SchedulerError) as ei:
        svc.book("krusvel", TOMORROW, "10:30", "Odilse Trankave Murno", service_id="service:manicure")
    assert "already booked" in str(ei.value)
    # The refusal carries the starts where a 30-min service still fits that day.
    assert "14:00" in str(ei.value)


# ── per professional: one professional's day does not touch another's ─────────────────────────
def test_same_interval_different_professionals_both_book():
    svc = _svc([_service("manicure", 30, ["krusvel", "simbroe"])])
    a = svc.book("krusvel", TOMORROW, "10:00", "Belmira Quostral Vendrim", service_id="service:manicure")
    b = svc.book("simbroe", TOMORROW, "10:00", "Odilse Trankave Murno", service_id="service:manicure")
    assert a.host_id == "krusvel" and b.host_id == "simbroe"
    assert a.time == b.time == "10:00"


def test_a_professional_who_does_not_perform_the_service_is_refused_with_who_does():
    # Coloração is Ulpiano Krusvel's only; Draventa Simbroe does not perform it.
    svc = _svc([_service("coloracao", 120, ["krusvel"])])
    with pytest.raises(SchedulerError) as ei:
        svc.book("simbroe", TOMORROW, "10:00", "Belmira Quostral Vendrim",
                 service_id="service:coloracao")
    msg = str(ei.value)
    assert "Draventa Simbroe does not perform" in msg and "NOTHING was written" in msg
    assert "Ulpiano Krusvel [krusvel]" in msg            # the roster of who DOES perform it
    # 0 writes.
    assert svc.store.list(host_id="simbroe") == []
    # check_availability for the same mismatch refuses too (never offers Bia's slots for it).
    with pytest.raises(SchedulerError):
        svc.check_availability("simbroe", TOMORROW, service_id="service:coloracao")


def test_all_hosts_service_is_bookable_by_anyone_with_an_agenda():
    svc = _svc([_service("corte", 60, all_hosts=True)])
    a = svc.book("krusvel", TOMORROW, "09:00", "Belmira Quostral Vendrim", service_id="service:corte")
    b = svc.book("simbroe", TOMORROW, "09:00", "Odilse Trankave Murno", service_id="service:corte")
    assert a.host_id == "krusvel" and b.host_id == "simbroe"


# ── carrier present → stricter: a catalog write must name its service ─────────────────────────
def test_catalog_present_booking_without_a_service_is_refused():
    svc = _svc([_service("coloracao", 120, ["krusvel"]),
                _service("manicure", 30, ["krusvel", "simbroe"])])
    with pytest.raises(SchedulerError) as ei:
        svc.book("krusvel", TOMORROW, "10:00", "Belmira Quostral Vendrim")
    assert "which service" in str(ei.value) and "NOTHING was written" in str(ei.value)
    assert svc.store.list(host_id="krusvel") == []      # 0 writes


def test_catalog_of_one_service_books_without_naming_it():
    svc = _svc([_service("coloracao", 120, ["krusvel"])])
    appt = svc.book("krusvel", TOMORROW, "10:00", "Belmira Quostral Vendrim")
    assert appt.service_id == "service:coloracao" and appt.duration_minutes == 120


# ── a long booking blocks the fixed slot / the block even without a service_id on the read ────
def test_a_long_booking_removes_a_fixed_slot_and_a_block_over_it():
    svc = _svc([_service("coloracao", 120, ["krusvel"])])
    svc.book("krusvel", TOMORROW, "10:00", "Belmira Quostral Vendrim", service_id="service:coloracao")
    # A no-service availability read (tenant fixed slots) drops the slots the colour covers.
    free_slots = svc.check_availability("krusvel", TOMORROW)
    assert "10:00" not in free_slots and "11:00" not in free_slots and "09:00" in free_slots
    # Blocking 11:00 is refused — the colour occupies [10:00,12:00).
    with pytest.raises(SchedulerError) as ei:
        svc.block_schedule("krusvel", TOMORROW, start_time="11:00")
    assert "client appointments exist" in str(ei.value)


# ── reschedule keeps the booked duration and re-checks the whole interval ─────────────────────
def test_reschedule_a_long_booking_onto_an_occupied_interval_is_refused_with_alternatives():
    svc = _svc([_service("coloracao", 120, ["krusvel"]),
                _service("manicure", 30, ["krusvel", "simbroe"])])
    colour = svc.book("krusvel", TOMORROW, "09:00", "Belmira Quostral Vendrim",
                      service_id="service:coloracao")
    svc.book("krusvel", TOMORROW, "14:30", "Odilse Trankave Murno", service_id="service:manicure")
    # Move the 2-hour colour to 14:00 → its [14:00,16:00) swallows the 14:30 manicure → refuse.
    with pytest.raises(SchedulerError) as ei:
        svc.reschedule(colour.appointment_id, TOMORROW, "14:00")
    assert "already booked" in str(ei.value)
    # The colour did not move.
    assert svc.store.get(colour.appointment_id).time == "09:00"


def test_reschedule_a_long_booking_to_a_free_interval_moves_it():
    svc = _svc([_service("coloracao", 120, ["krusvel"])])
    colour = svc.book("krusvel", TOMORROW, "09:00", "Belmira Quostral Vendrim",
                      service_id="service:coloracao")
    moved = svc.reschedule(colour.appointment_id, LATER, "14:00")
    assert moved.date == LATER and moved.time == "14:00" and moved.duration_minutes == 120


# ── compatibility: no catalog → exactly today ────────────────────────────────────────────────
def test_without_a_catalog_the_fixed_slot_behaviour_is_unchanged():
    svc = _svc()        # no catalog
    free = svc.check_availability("krusvel", TOMORROW)
    assert free == ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]
    appt = svc.book("krusvel", TOMORROW, "10:00", "Belmira Quostral Vendrim")
    assert appt.service_id == "" and appt.duration_minutes == 60   # the tenant slot
    # A 60-min booking blocks only its own slot (no interval spill).
    after = svc.check_availability("krusvel", TOMORROW)
    assert "10:00" not in after and "11:00" in after and "09:00" in after

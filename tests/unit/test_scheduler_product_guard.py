"""The PRODUCT guard: a catalog product is never scheduled; an unknown service id is
refused with the services; a bare service id passes through; and with NO catalog the booking path
is exactly what it was before (the compatibility control). The Secretary explains a product and
its price, but it does not book it and it does not sell it.
"""

from __future__ import annotations

import pytest

from cogno_praxis.scheduler import catalog as C
from cogno_praxis.scheduler.service import SchedulerError, SchedulerService
from cogno_praxis.scheduler.store import Host, InMemoryAppointmentStore

_DAY = "2026-11-20"           # a Friday, a working day, in the future relative to the fixed clock


def _svc(with_catalog: bool) -> SchedulerService:
    store = InMemoryAppointmentStore()
    for h in (Host("belmira", "Belmira Quostral", "Cabeleireira"),):
        store.hosts[h.host_id] = h
    catalog = ()
    if with_catalog:
        block = ("SERVIÇOS:\n- Coloração | 120 min | R$ 260,00 | Belmira\n"
                 "PRODUTOS:\n- Shampoo reparador | R$ 60,00\n")
        catalog = C.parse_catalog_block(block, [Host("belmira", "Belmira Quostral",
                                                     "Cabeleireira")]).items
    return SchedulerService(store, catalog=catalog, today=lambda: __import__("datetime").date(2026, 11, 1))


def test_a_product_id_is_never_booked_and_nothing_is_written():
    svc = _svc(with_catalog=True)
    with pytest.raises(SchedulerError) as exc:
        svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim",
                 service_id="product:shampoo_reparador")
    assert "PRODUCT" in str(exc.value) and "NOTHING was written" in str(exc.value)
    assert svc.store.list() == []


def test_an_unknown_service_id_is_refused_with_the_services():
    svc = _svc(with_catalog=True)
    with pytest.raises(SchedulerError) as exc:
        svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim", service_id="service:nao_existe")
    assert "Coloração" in str(exc.value) and "service:coloracao" in str(exc.value)
    assert svc.store.list() == []


def test_a_service_id_passes_the_guard_and_books():
    svc = _svc(with_catalog=True)
    appt = svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim", service_id="service:coloracao")
    assert appt.host_id == "belmira" and len(svc.store.list()) == 1


def test_the_guard_also_covers_check_and_reschedule():
    svc = _svc(with_catalog=True)
    with pytest.raises(SchedulerError):
        svc.check_availability("belmira", _DAY, service_id="product:shampoo_reparador")
    appt = svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim")
    with pytest.raises(SchedulerError):
        svc.reschedule(appt.appointment_id, _DAY, "11:00",
                       service_id="product:shampoo_reparador")


def test_without_a_catalog_a_service_id_is_inert_and_booking_is_unchanged():
    """The compatibility control: no catalog → the guard does nothing, a service_id is ignored and
    the booking lands exactly as it did before this slice."""
    svc = _svc(with_catalog=False)
    appt = svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim", service_id="anything")
    assert appt.host_id == "belmira" and len(svc.store.list()) == 1

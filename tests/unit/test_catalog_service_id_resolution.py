"""`services_for_choice` is the ONE predicate for "a booking must name a service": the
services when there are two or more, else empty (none, or exactly one which is used). A
`service_id` given as a NAME or slug resolves to the exact id when it names exactly one SERVICE;
nobody or two → the refusal of before; a PRODUCT stays refused.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.scheduler import Host, InMemoryAppointmentStore, SchedulerService, services_for_choice
from cogno_praxis.scheduler.catalog import CatalogItem
from cogno_praxis.scheduler.service import SchedulerError

_DAY = "2026-11-20"


def _svc(*items: CatalogItem) -> SchedulerService:
    store = InMemoryAppointmentStore()
    store.hosts["belmira"] = Host("belmira", "Belmira Quostral", "Cabeleireira")
    return SchedulerService(store, catalog=items, today=lambda: date(2026, 11, 1))


def _service(name: str, item_id: str) -> CatalogItem:
    return CatalogItem(item_id=item_id, kind="service", name=name, value_text="R$ 10,00",
                       duration_minutes=30, all_hosts=True)


def _product(name: str, item_id: str) -> CatalogItem:
    return CatalogItem(item_id=item_id, kind="product", name=name, value_text="R$ 5,00")


# ── services_for_choice ───────────────────────────────────────────────────────────────────
def test_services_for_choice_is_empty_for_none_or_one_and_the_set_for_two_or_more():
    assert services_for_choice(()) == ()
    assert services_for_choice((_product("Shampoo", "product:shampoo"),)) == ()      # products only
    one = (_service("Coloração", "service:coloracao"),)
    assert services_for_choice(one) == ()                                            # exactly one
    two = (_service("Coloração", "service:coloracao"), _service("Corte", "service:corte"))
    assert services_for_choice(two) == two                                           # two → choose


def test_require_service_when_catalog_uses_the_same_predicate():
    # two services, no id → refuse (the choice set); one service → use it; none → slot (None)
    with pytest.raises(SchedulerError) as exc:
        _svc(_service("Coloração", "service:coloracao"),
             _service("Corte", "service:corte")).book("belmira", _DAY, "10:00", "Thessaly Vendrim")
    assert "which service?" in str(exc.value)
    appt = _svc(_service("Coloração", "service:coloracao")).book(
        "belmira", _DAY, "10:00", "Thessaly Vendrim")                                # one → used
    assert appt.service_id == "service:coloracao"


# ── service_id by name / slug ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("token", ["service:coloracao", "coloracao", "Coloração", "COLORAÇÃO"])
def test_a_service_named_by_id_slug_or_name_all_book(token):
    svc = _svc(_service("Coloração", "service:coloracao"), _product("Shampoo", "product:shampoo"))
    appt = svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim", service_id=token)
    assert appt.service_id == "service:coloracao"


def test_a_product_named_by_name_is_still_refused():
    svc = _svc(_service("Coloração", "service:coloracao"), _product("Shampoo", "product:shampoo"))
    with pytest.raises(SchedulerError) as exc:
        svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim", service_id="Shampoo")
    assert "PRODUCT" in str(exc.value)


def test_an_ambiguous_name_is_refused_not_guessed():
    # two services whose names FOLD the same («Corte» / «côrte») → resolve_item_token returns None
    svc = _svc(_service("Corte", "service:corte"), _service("côrte", "service:corte2"))
    with pytest.raises(SchedulerError) as exc:
        svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim", service_id="corte")
    assert "unknown service" in str(exc.value)


def test_an_unknown_name_is_refused():
    svc = _svc(_service("Coloração", "service:coloracao"))
    with pytest.raises(SchedulerError) as exc:
        svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim", service_id="manicure")
    assert "unknown service" in str(exc.value)


# ── the same name/slug resolution on the other two surfaces ─────────────────────────────────────
def test_check_availability_accepts_a_service_by_name_or_slug():
    svc = _svc(_service("Coloração", "service:coloracao"), _product("Shampoo", "product:shampoo"))
    assert isinstance(svc.check_availability("belmira", _DAY, service_id="Coloração"), list)
    assert isinstance(svc.check_availability("belmira", _DAY, service_id="coloracao"), list)
    with pytest.raises(SchedulerError):                       # a product by name is still refused
        svc.check_availability("belmira", _DAY, service_id="Shampoo")


def test_reschedule_accepts_a_service_by_name():
    svc = _svc(_service("Coloração", "service:coloracao"), _product("Shampoo", "product:shampoo"))
    appt = svc.book("belmira", _DAY, "10:00", "Thessaly Vendrim", service_id="service:coloracao")
    moved = svc.reschedule(appt.appointment_id, _DAY, "11:00", service_id="Coloração")
    assert moved.time == "11:00"
    with pytest.raises(SchedulerError):                       # a product by name is still refused
        svc.reschedule(appt.appointment_id, _DAY, "12:00", service_id="Shampoo")

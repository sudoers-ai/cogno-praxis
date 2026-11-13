"""The booking TOOLS carry ``service_id`` to the service, and the secretary's system prompt
gains a catalog step only when a catalog exists.

Before this change the ``book_appointment`` / ``check_availability`` tool wrappers dropped
``service_id`` on the floor: the duration-aware booking and the product guard lived on the
SERVICE methods but no tool reached them. A PRODUCT id handed to the booking tool therefore
booked a normal slot. These twins drive the TOOLS (not the service methods) and fail on that
older wrapper; the control is the no-service and no-catalog paths, which are unchanged.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.scheduler import Host, InMemoryAppointmentStore, SchedulerService
from cogno_praxis.scheduler import catalog as C
from cogno_praxis.scheduler.server import build_server

_TODAY = date(2026, 6, 30)
_DAY = "2026-07-01"           # tomorrow, a working day


def _catalog_service() -> SchedulerService:
    store = InMemoryAppointmentStore()
    store.hosts["belmira"] = Host("belmira", "Belmira Quostral", "Cabeleireira")
    items = C.parse_catalog_block(
        "SERVIÇOS:\n- Coloração | 120 min | R$ 260,00 | Belmira\n"
        "PRODUTOS:\n- Shampoo | R$ 60,00\n",
        [Host("belmira", "Belmira Quostral", "Cabeleireira")]).items
    return SchedulerService(store, today=lambda: _TODAY, catalog=items)


def _text(call_result) -> str:
    content = call_result[0]
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


async def test_book_appointment_tool_refuses_a_product_id_and_writes_nothing():
    """A product id reaches the product guard THROUGH the tool — the wrapper forwards
    ``service_id`` (FastMCP surfaces the SchedulerError as a tool error). The old wrapper
    ignored it and booked the slot (the red)."""
    svc = _catalog_service()
    with pytest.raises(Exception) as exc:
        await build_server(svc).call_tool(
            "book_appointment",
            {"host_id": "belmira", "date": _DAY, "time": "10:00",
             "with_name": "Thessaly Vendrim", "service_id": "product:shampoo"})
    assert "PRODUCT" in str(exc.value) and "NOTHING was written" in str(exc.value)
    assert svc.store.list() == []


async def test_check_availability_tool_refuses_a_product_id():
    svc = _catalog_service()
    with pytest.raises(Exception) as exc:
        await build_server(svc).call_tool(
            "check_availability",
            {"host_id": "belmira", "date": _DAY, "service_id": "product:shampoo"})
    assert "PRODUCT" in str(exc.value)


async def test_book_appointment_tool_books_a_service_by_id():
    svc = _catalog_service()
    out = _text(await build_server(svc).call_tool(
        "book_appointment",
        {"host_id": "belmira", "date": _DAY, "time": "10:00",
         "with_name": "Thessaly Vendrim", "service_id": "service:coloracao"}))
    assert "Booked" in out
    assert len(svc.store.list()) == 1


async def test_the_booking_occupies_the_service_duration_through_the_tool():
    """A 120 min service booked at 10:00 occupies 10:00–12:00 for that professional, so 11:00
    is no longer offered — the duration-aware path, reached from the tool via ``service_id``."""
    svc = _catalog_service()
    server = build_server(svc)
    await server.call_tool(
        "book_appointment",
        {"host_id": "belmira", "date": _DAY, "time": "10:00",
         "with_name": "Thessaly Vendrim", "service_id": "service:coloracao"})
    out = _text(await server.call_tool(
        "check_availability",
        {"host_id": "belmira", "date": _DAY, "service_id": "service:coloracao"}))
    assert "11:00" not in out


async def test_no_service_id_is_unchanged_the_compatibility_control():
    """Without ``service_id`` the tools behave as before: a plain slot booking lands and the
    free slots read normally. (No catalog is exercised by the module's other suites.)"""
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    svc = SchedulerService(store, today=lambda: _TODAY)
    out = _text(await build_server(svc).call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": _DAY, "time": "10:00", "with_name": "Thessaly Vendrim"}))
    assert "Booked" in out and len(svc.store.list()) == 1


def test_services_system_block_is_empty_without_a_catalog_and_present_with_one():
    """The ``{{SERVICES_CATALOG}}`` fill: "" with no catalog (so the system prompt is byte for
    byte what it was), the fixed block with one. It carries NO tenant text (names/prices reach
    the model only as the guarded result of ``list_services``), so a catalog edit does not move
    it."""
    assert C.services_system_block(None) == ""
    assert C.services_system_block({}) == ""
    assert C.services_system_block({"catalog": []}) == ""
    cfg = {"catalog": [
        {"item_id": "service:coloracao", "kind": "service", "name": "Coloração",
         "duration_minutes": 120, "value_text": "R$ 260,00", "all_hosts": True}]}
    block = C.services_system_block(cfg)
    assert block.startswith("\n## Services, Products & Prices")
    assert block.endswith("\n")
    assert "list_services" in block and "service_id" in block
    assert "never scheduled and never sold" in block
    # No tenant text leaks into the fixed block.
    assert "Coloração" not in block and "260" not in block

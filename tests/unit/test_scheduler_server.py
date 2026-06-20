"""Unit tests for the FastMCP server wrapper (tools + annotations), in-process."""

from datetime import date

import pytest

from cogno_praxis.scheduler import Host, InMemoryAppointmentStore, SchedulerService
from cogno_praxis.scheduler.server import build_server

# Fixed clock so the "start from tomorrow" rule is deterministic regardless of run date.
_TODAY = date(2026, 6, 30)


def _server():
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    return build_server(SchedulerService(store, today=lambda: _TODAY))


def _text(call_result):
    # FastMCP call_tool returns (content_blocks, structured)
    content = call_result[0]
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


async def test_tools_and_annotations():
    tools = await _server().list_tools()
    ann = {t.name: t.annotations for t in tools}
    assert set(ann) == {"list_schedulable_hosts", "check_availability",
                        "book_appointment", "list_appointments",
                        "update_appointment_status", "cancel_appointment"}
    assert ann["check_availability"].readOnlyHint is True
    assert ann["book_appointment"].readOnlyHint is False
    assert ann["update_appointment_status"].readOnlyHint is False
    assert ann["cancel_appointment"].destructiveHint is True


async def test_list_hosts_tool():
    out = _text(await _server().call_tool("list_schedulable_hosts", {}))
    assert "dr_silva" in out and "Dr. Silva" in out


async def test_book_then_list_then_cancel_flow():
    mcp = _server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    assert "Booked" in booked and "PENDING" in booked

    listed = _text(await mcp.call_tool("list_appointments", {"with_name": "Ana"}))
    assert "Ana" in listed and "dr_silva" in listed

    # availability no longer shows the taken slot
    avail = _text(await mcp.call_tool(
        "check_availability", {"host_id": "dr_silva", "date": "2026-07-01"}))
    assert "09:00" not in avail


async def test_update_status_tool():
    mcp = _server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    appt_id = booked.split()[1].rstrip(":")
    out = _text(await mcp.call_tool(
        "update_appointment_status", {"appointment_id": appt_id, "new_status": "CONFIRMED"}))
    assert "CONFIRMED" in out


async def test_cancel_tool_with_reason():
    mcp = _server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "10:00", "with_name": "Ana"}))
    appt_id = booked.split()[1].rstrip(":")
    out = _text(await mcp.call_tool(
        "cancel_appointment", {"appointment_id": appt_id, "reason": "no longer needed"}))
    assert "Cancelled" in out and "no longer needed" in out


async def test_empty_state_messages():
    empty = build_server(SchedulerService(InMemoryAppointmentStore(), today=lambda: _TODAY))
    assert "No schedulable hosts" in _text(await empty.call_tool("list_schedulable_hosts", {}))
    assert "No appointments" in _text(await empty.call_tool("list_appointments", {}))


async def test_no_free_slots_message():
    mcp = _server()
    for t in ("09:00", "10:00", "11:00", "14:00", "15:00", "16:00"):
        await mcp.call_tool("book_appointment", {
            "host_id": "dr_silva", "date": "2026-07-01", "time": t, "with_name": "X"})
    out = _text(await mcp.call_tool("check_availability", {"host_id": "dr_silva", "date": "2026-07-01"}))
    assert "no free slots" in out.lower()


async def test_book_taken_slot_errors():
    mcp = _server()
    args = {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}
    await mcp.call_tool("book_appointment", args)
    with pytest.raises(Exception):  # FastMCP surfaces the SchedulerError as a tool error
        await mcp.call_tool("book_appointment", {**args, "with_name": "Bob"})


async def test_book_today_errors():
    mcp = _server()
    with pytest.raises(Exception):  # past/today date rejected by the domain rule
        await mcp.call_tool("book_appointment", {
            "host_id": "dr_silva", "date": _TODAY.isoformat(), "time": "09:00", "with_name": "Ana"})

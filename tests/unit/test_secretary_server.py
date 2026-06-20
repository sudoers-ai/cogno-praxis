"""Unit tests for the FastMCP server wrapper (tools + annotations), in-process."""

import pytest

from cogno_praxis.secretary import Host, InMemoryAppointmentStore, SecretaryService
from cogno_praxis.secretary.server import build_server


def _server():
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    return build_server(SecretaryService(store))


def _text(call_result):
    # FastMCP call_tool returns (content_blocks, structured)
    content = call_result[0]
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


async def test_tools_and_annotations():
    tools = await _server().list_tools()
    ann = {t.name: t.annotations for t in tools}
    assert set(ann) == {"list_schedulable_hosts", "check_availability",
                        "book_appointment", "list_appointments", "cancel_appointment"}
    assert ann["check_availability"].readOnlyHint is True
    assert ann["book_appointment"].readOnlyHint is False
    assert ann["cancel_appointment"].destructiveHint is True


async def test_list_hosts_tool():
    out = _text(await _server().call_tool("list_schedulable_hosts", {}))
    assert "dr_silva" in out and "Dr. Silva" in out


async def test_book_then_list_then_cancel_flow():
    mcp = _server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    assert "Booked" in booked

    listed = _text(await mcp.call_tool("list_appointments", {"with_name": "Ana"}))
    assert "Ana" in listed and "dr_silva" in listed

    # availability no longer shows the taken slot
    avail = _text(await mcp.call_tool(
        "check_availability", {"host_id": "dr_silva", "date": "2026-07-01"}))
    assert "09:00" not in avail


async def test_cancel_tool():
    mcp = _server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "10:00", "with_name": "Ana"}))
    appt_id = booked.split()[1].rstrip(":")
    out = _text(await mcp.call_tool("cancel_appointment", {"appointment_id": appt_id}))
    assert "Cancelled" in out


async def test_empty_state_messages():
    empty = build_server(SecretaryService(InMemoryAppointmentStore()))
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
    with pytest.raises(Exception):  # FastMCP surfaces the SecretaryError as a tool error
        await mcp.call_tool("book_appointment", {**args, "with_name": "Bob"})

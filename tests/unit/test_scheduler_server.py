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
    assert set(ann) == {"resolve_date", "list_schedulable_hosts", "check_availability",
                        "book_appointment", "block_schedule", "list_appointments",
                        "reschedule_appointment", "update_appointment_status",
                        "cancel_appointment", "get_schedule_settings",
                        "set_schedule_settings", "set_auto_confirm"}
    assert ann["get_schedule_settings"].readOnlyHint is True
    assert ann["set_schedule_settings"].readOnlyHint is False
    assert ann["set_auto_confirm"].readOnlyHint is False
    assert ann["resolve_date"].readOnlyHint is True
    assert ann["check_availability"].readOnlyHint is True
    assert ann["book_appointment"].readOnlyHint is False
    assert ann["block_schedule"].readOnlyHint is False
    assert ann["update_appointment_status"].readOnlyHint is False
    assert ann["cancel_appointment"].destructiveHint is True
    # reschedule is a confirmed (destructive) action → EGO gate B holds it
    assert ann["reschedule_appointment"].destructiveHint is True


async def test_list_hosts_tool():
    out = _text(await _server().call_tool("list_schedulable_hosts", {}))
    assert "dr_silva" in out and "Dr. Silva" in out


async def test_book_then_list_then_cancel_flow():
    mcp = _server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    assert "Booked" in booked and "CONFIRMED" in booked   # dr_silva auto_confirms

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


async def test_schedule_settings_tools():
    mcp = _server()
    before = _text(await mcp.call_tool("get_schedule_settings", {}))
    assert "work_start=09:00" in before
    out = _text(await mcp.call_tool("set_schedule_settings", {"work_start": "08:00"}))
    assert "work_start=08:00" in out
    # the change took effect on availability
    avail = _text(await mcp.call_tool(
        "check_availability", {"host_id": "dr_silva", "date": "2026-07-01"}))
    assert "08:00" in avail


async def test_set_auto_confirm_tool():
    mcp = _server()
    out = _text(await mcp.call_tool(
        "set_auto_confirm", {"host_id": "dr_silva", "auto_confirm": False}))
    assert "dr_silva" in out and "False" in out
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    assert "PENDING" in booked      # now waits for the professional to accept


async def test_reschedule_tool_moves_appointment():
    mcp = _server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    appt_id = booked.split()[1].rstrip(":")
    out = _text(await mcp.call_tool(
        "reschedule_appointment",
        {"appointment_id": appt_id, "new_date": "2026-07-01", "new_time": "11:00"}))
    assert "Rescheduled" in out and "11:00" in out
    # 09:00 is free again, 11:00 is now taken
    avail = _text(await mcp.call_tool(
        "check_availability", {"host_id": "dr_silva", "date": "2026-07-01"}))
    assert "09:00" in avail and "11:00" not in avail


async def test_block_schedule_tool():
    mcp = _server()
    out = _text(await mcp.call_tool(
        "block_schedule", {"host_id": "dr_silva", "date": "2026-07-01",
                           "description": "Férias"}))
    assert "Blocked" in out and "Férias" in out
    # the whole day is now gone from availability
    avail = _text(await mcp.call_tool(
        "check_availability", {"host_id": "dr_silva", "date": "2026-07-01"}))
    assert "no free slots" in avail.lower()


async def test_block_schedule_conflict_errors():
    mcp = _server()
    await mcp.call_tool("book_appointment", {
        "host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"})
    with pytest.raises(Exception):   # a client booking in range → SchedulerError as tool error
        await mcp.call_tool("block_schedule", {"host_id": "dr_silva", "date": "2026-07-01"})


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


def test_catalog_hosts_from_env_replaces_demo(monkeypatch):
    """COGNO_SCHEDULER_HOSTS injects the tenant's real catalog and replaces the demo doctors."""
    import json

    from cogno_praxis.scheduler.server import _catalog_hosts

    # unset → the built-in demo (standalone/tests stay usable)
    monkeypatch.delenv("COGNO_SCHEDULER_HOSTS", raising=False)
    assert {h.host_id for h in _catalog_hosts()} == {"dr_silva", "dr_souza", "ana"}

    # set → exactly the injected catalog, no demo leakage; auto_confirm defaults to False
    monkeypatch.setenv("COGNO_SCHEDULER_HOSTS", json.dumps(
        [{"host_id": "comercial", "name": "Equipe Comercial", "role": "Demo"},
         {"host_id": "suporte", "name": "Suporte", "role": "Onboarding", "auto_confirm": True}]))
    hosts = {h.host_id: h for h in _catalog_hosts()}
    assert set(hosts) == {"comercial", "suporte"}          # demo gone
    assert hosts["comercial"].auto_confirm is False        # safe default
    assert hosts["suporte"].auto_confirm is True

    # empty list → a real tenant with NO professionals shows none (not the demo)
    monkeypatch.setenv("COGNO_SCHEDULER_HOSTS", "[]")
    assert _catalog_hosts() == []

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


def _clocked_server():
    """A server whose "today" moves, so a booking can be played forward to its own day.

    Needed since 2026-08-18: only an appointment that has already come due may be COMPLETED
    (completing a FUTURE booking used to evaporate it and free the slot, through a tool with
    no destructiveHint). Booking still requires a future date, so any test that completes has
    to travel."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    clock = {"d": _TODAY}
    return build_server(SchedulerService(store, today=lambda: clock["d"])), clock


def _text(call_result):
    # FastMCP call_tool returns (content_blocks, structured)
    content = call_result[0]
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


async def test_tools_and_annotations():
    tools = await _server().list_tools()
    ann = {t.name: t.annotations for t in tools}
    assert set(ann) == {"resolve_date", "list_schedulable_hosts", "check_availability",
                        "book_appointment", "block_schedule", "list_appointments",
                        "reschedule_appointment", "confirm_appointment",
                        "complete_appointment",
                        "cancel_appointment", "get_schedule_settings",
                        "set_schedule_settings", "set_auto_confirm"}
    assert ann["get_schedule_settings"].readOnlyHint is True
    assert ann["set_schedule_settings"].readOnlyHint is False
    assert ann["set_auto_confirm"].readOnlyHint is False
    assert ann["resolve_date"].readOnlyHint is True
    assert ann["check_availability"].readOnlyHint is True
    assert ann["book_appointment"].readOnlyHint is False
    assert ann["block_schedule"].readOnlyHint is False
    assert ann["confirm_appointment"].readOnlyHint is False
    assert ann["complete_appointment"].readOnlyHint is False
    assert ann["cancel_appointment"].destructiveHint is True
    # reschedule is a confirmed (destructive) action → EGO gate B holds it
    assert ann["reschedule_appointment"].destructiveHint is True
    # THE point of the split (2026-08-18). The host's confirmation gate decides by tool NAME
    # (`requires_confirmation(name)`, no arguments), so a single tool taking a free-text status
    # spanned opposite risks: cancelling was reachable through the non-destructive twin while
    # `cancel_appointment` was held. Measured before the split:
    # `update_appointment_status(id, "CANCELED")` cancelled the appointment and freed the slot,
    # with `destructiveHint=None`. Neither confirm nor complete may carry a cancel path.
    assert "update_appointment_status" not in ann, (
        "the status catch-all is a cancellation bypass — it must not come back")
    assert ann["confirm_appointment"].destructiveHint in (None, False)
    assert ann["complete_appointment"].destructiveHint in (None, False)


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
    # the listing now shows the professional's DISPLAY name (host_name), not the raw host_id
    assert "Ana" in listed and "Dr. Silva" in listed

    # availability no longer shows the taken slot
    avail = _text(await mcp.call_tool(
        "check_availability", {"host_id": "dr_silva", "date": "2026-07-01"}))
    assert "09:00" not in avail


async def test_complete_appointment_tool():
    mcp, clock = _clocked_server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    appt_id = booked.split()[1].rstrip(":")
    clock["d"] = date(2026, 7, 1)          # the consultation day arrives
    out = _text(await mcp.call_tool("complete_appointment", {"appointment_id": appt_id}))
    assert f"Appointment {appt_id} is now COMPLETED" in out


async def test_neither_status_verb_can_reach_CANCELED():
    """The bypass, pinned shut by EFFECT — and with both legs actually exercised.

    First cut of this test used the auto-confirming host, so the "confirm" leg only ever hit
    the ALREADY-CONFIRMED no-op branch and the closing assertion read a listing that renders
    "No CANCELED appointments found." — it would have passed with the id simply absent. A host
    with ``auto_confirm=False`` makes PENDING→CONFIRMED a real transition, and the history
    listing shows the status per row, so both legs discriminate.
    """
    store = InMemoryAppointmentStore()
    store.hosts["dr_souza"] = Host("dr_souza", "Dr. Souza", "GP", auto_confirm=False)
    clock = {"d": _TODAY}
    mcp = build_server(SchedulerService(store, today=lambda: clock["d"]))

    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_souza", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    appt_id = booked.split()[1].rstrip(":")
    assert "PENDING" in booked                       # the transition below is real, not a no-op

    # FastMCP does not reject an unknown argument — it IGNORES it. So "the tool has no status
    # parameter" is not observable from an exception, and asserting one would have been a test
    # that passes for the wrong reason. Assert the EFFECT: the extra argument changes nothing.
    out = _text(await mcp.call_tool(
        "confirm_appointment", {"appointment_id": appt_id, "new_status": "CANCELED"}))
    assert "is now CONFIRMED" in out, f"confirm honoured a smuggled status: {out!r}"

    clock["d"] = date(2026, 7, 1)
    out = _text(await mcp.call_tool(
        "complete_appointment", {"appointment_id": appt_id, "new_status": "CANCELED"}))
    assert "is now COMPLETED" in out, f"complete honoured a smuggled status: {out!r}"

    # …and the row's real status in the history listing, which prints one per line.
    history = _text(await mcp.call_tool("list_appointments", {"include_history": True}))
    row = next(line for line in history.splitlines() if appt_id in line)
    assert "[COMPLETED]" in row and "CANCELED" not in row, row

    # The tool that IS allowed to cancel still does — this is a gate, not a lockout.
    other = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_souza", "date": "2026-07-02", "time": "09:00", "with_name": "Bia"}))
    other_id = other.split()[1].rstrip(":")
    _text(await mcp.call_tool("cancel_appointment", {"appointment_id": other_id}))
    history = _text(await mcp.call_tool("list_appointments", {"include_history": True}))
    row = next(line for line in history.splitlines() if other_id in line)
    assert "[CANCELED]" in row, row


async def test_confirm_noop_says_already():
    """dr_silva auto_confirms → re-confirming is a NO-OP: the tool must SAY so (the model
    otherwise celebrates a change that never happened — the bulk-confirm live bug)."""
    mcp = _server()
    booked = _text(await mcp.call_tool(
        "book_appointment",
        {"host_id": "dr_silva", "date": "2026-07-01", "time": "09:00", "with_name": "Ana"}))
    appt_id = booked.split()[1].rstrip(":")   # already CONFIRMED (auto_confirm)
    out = _text(await mcp.call_tool("confirm_appointment", {"appointment_id": appt_id}))
    assert "ALREADY CONFIRMED" in out and "no change" in out


async def test_list_appointments_status_filter_tool():
    mcp = _server()
    await mcp.call_tool("book_appointment", {"host_id": "dr_silva", "date": "2026-07-01",
                                             "time": "09:00", "with_name": "Ana"})
    # dr_silva auto_confirms → nothing PENDING; the filter says so AND points at the
    # CONFIRMED row (a bare miss reads as "nothing to act on" — see the hint test below)
    out = _text(await mcp.call_tool("list_appointments", {"status": "PENDING"}))
    assert out.startswith("No PENDING appointments found")
    assert "another status" in out
    conf = _text(await mcp.call_tool("list_appointments", {"status": "confirmed"}))
    assert "Ana" in conf and "[CONFIRMED]" in conf


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


def test_pg_seed_reconciles_when_catalog_env_set(monkeypatch):
    """With COGNO_SCHEDULER_HOSTS set the injected catalog is AUTHORITATIVE over the Pg store:
    the seed must sync (upsert + delete the rest), not upsert-only — a professional removed on
    the dashboard once lingered as a bookable ghost doctor forever."""
    import json

    from cogno_praxis.scheduler import server as srv

    calls: dict = {}

    class _FakePg:
        def __init__(self, dsn, scope):
            calls["init"] = (dsn, scope)

        def sync_hosts(self, hosts):
            calls["sync"] = [h.host_id for h in hosts]

        def add_host(self, host):
            calls.setdefault("add", []).append(host.host_id)

    import cogno_praxis.scheduler.stores.postgres as pgmod
    monkeypatch.setattr(pgmod, "PgAppointmentStore", _FakePg)
    monkeypatch.setenv("COGNO_SCHEDULER_DSN", "postgresql://x")
    monkeypatch.delenv("COGNO_SCHEDULER_SEED", raising=False)

    # catalog env SET → reconcile (sync), never plain upserts
    monkeypatch.setenv("COGNO_SCHEDULER_HOSTS", json.dumps(
        [{"host_id": "dr_real", "name": "Dr. Real", "role": "GP"}]))
    srv._seeded_service()
    assert calls.get("sync") == ["dr_real"] and "add" not in calls

    # catalog env UNSET (standalone demo over Pg) → upsert-only, never wipe a real store
    calls.clear()
    monkeypatch.delenv("COGNO_SCHEDULER_HOSTS", raising=False)
    srv._seeded_service()
    assert "sync" not in calls and set(calls.get("add", [])) == {"dr_silva", "dr_souza", "ana"}


def test_seed_appointments_from_env(monkeypatch):
    """COGNO_SCHEDULER_SEED pre-loads appointments with EXPLICIT ids (harness channel)."""
    import json

    from cogno_praxis.scheduler.server import _seeded_service

    monkeypatch.delenv("COGNO_SCHEDULER_HOSTS", raising=False)
    monkeypatch.delenv("COGNO_SCHEDULER_DSN", raising=False)
    monkeypatch.setenv("COGNO_SCHEDULER_SEED", json.dumps([
        {"appointment_id": "e4d1a201", "host_id": "dr_souza", "date": "2099-01-04",
         "time": "09:00", "with_name": "Maria", "status": "PENDING", "guest_id": "maria"},
        {"appointment_id": "b7c3f902", "host_id": "dr_souza", "date": "2099-01-04",
         "time": "14:00", "with_name": "Paula", "status": "CONFIRMED", "guest_id": "paula"},
    ]))
    svc = _seeded_service()
    appts = {a.appointment_id: a for a in svc.list_appointments(host_id="dr_souza")}
    assert set(appts) == {"e4d1a201", "b7c3f902"}          # exactly the seeded rows, ids kept
    assert appts["e4d1a201"].status == "PENDING"
    assert appts["b7c3f902"].with_name == "Paula"

    # unset → no seeding (production path untouched)
    monkeypatch.delenv("COGNO_SCHEDULER_SEED", raising=False)
    assert _seeded_service().list_appointments(host_id="dr_souza") == []


async def test_empty_status_filter_hints_other_statuses():
    """A status-filtered miss must not be a dead end: point at rows with other statuses
    (the 'cancela meu agendamento' → list PENDING → 'nothing to cancel' regression)."""
    from datetime import timedelta

    mcp = _server()
    day = (_TODAY + timedelta(days=1)).isoformat()
    await mcp.call_tool("book_appointment", {
        "host_id": "dr_silva", "date": day, "time": "09:00", "with_name": "Ana"})
    # dr_silva auto-confirms → the row is CONFIRMED, not PENDING
    out = _text(await mcp.call_tool("list_appointments", {"status": "PENDING"}))
    assert "No PENDING appointments found" in out
    assert "another status" in out and "WITHOUT" in out
    # a miss with NO other rows stays a plain miss (no misleading hint)
    out2 = _text(await mcp.call_tool("list_appointments",
                                     {"status": "COMPLETED", "with_name": "Bruno"}))
    assert "another status" not in out2

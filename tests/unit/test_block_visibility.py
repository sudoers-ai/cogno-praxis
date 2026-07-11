"""Reproduction: a self-block is invisible/indistinguishable in list_appointments.

Mirrors the live bug (Dr. Vinicius blocked 16/17 July, but the agent could not
surface it): block_schedule stores the marker in `notes` (never rendered) and
leaves `with_name=""`, so the list render flattens a block into a nameless
CONFIRMED row indistinguishable from a broken client booking.

Parent (`cogno`) put the marker in the rendered `title` field (default
"Indisponível") and returned structured JSON, so the block survived to the voicer.
"""

from datetime import date

import pytest

from cogno_praxis.scheduler import Host, InMemoryAppointmentStore, SchedulerService
from cogno_praxis.scheduler.server import build_server

_TODAY = date(2026, 6, 30)


def _server():
    store = InMemoryAppointmentStore()
    store.hosts["dr_vinicius"] = Host("dr_vinicius", "Dr. Vinicius Vale", "GP")
    return build_server(SchedulerService(store, today=lambda: _TODAY))


def _text(call_result):
    content = call_result[0]
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


@pytest.mark.asyncio
async def test_block_then_list_loses_block_semantics():
    mcp = _server()

    # 1) A real client booking on the 15th.
    await mcp.call_tool("book_appointment", {
        "host_id": "dr_vinicius", "date": "2026-07-15", "time": "10:00",
        "with_name": "Neymar Junior"})

    # 2) The user blocks the whole day on the 16th (self-occupation).
    blocked = _text(await mcp.call_tool("block_schedule", {
        "host_id": "dr_vinicius", "date": "2026-07-16"}))
    assert "Blocked" in blocked  # the write itself succeeds

    # 3) Now ask for the agenda, exactly like "traga minha agenda".
    listed = _text(await mcp.call_tool("list_appointments", {
        "host_id": "dr_vinicius"}))

    print("\n----- list_appointments output -----\n" + listed + "\n------------------------------------")

    # The block IS in the output (write worked)...
    assert "2026-07-16" in listed

    # ...and now (fix A) it is rendered as an explicit block the EGO/voicer can
    # voice, carrying the 'Bloqueado' marker that used to be dropped.
    block_line = next(ln for ln in listed.splitlines() if "2026-07-16" in ln)
    client_line = next(ln for ln in listed.splitlines() if "2026-07-15" in ln)
    print("block line :", repr(block_line))
    print("client line:", repr(client_line))
    assert "BLOQUEIO" in block_line and "Bloqueado" in block_line
    # A block is no longer confusable with a client booking: no bogus " with " gap.
    assert " with " not in block_line
    # Real client bookings are unchanged.
    assert "Neymar Junior with" in client_line

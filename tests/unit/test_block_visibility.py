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
    #
    # The two rows used to be FOUND by their ISO date, because every line carried one. Since
    # the shared renderer groups by day, the ISO lives in the day HEADER — hoisted, not
    # dropped, which is why the assertion above still reads unchanged. A row is now found by
    # what makes it that row, and the day it was filed under is asserted separately: that
    # pairing is strictly more than the old lookup checked, since a block filed under the
    # wrong header would have passed before.
    lines = listed.splitlines()
    block_line = next(ln for ln in lines if "BLOQUEIO" in ln)
    client_line = next(ln for ln in lines if "Neymar Junior" in ln)
    print("block line :", repr(block_line))
    print("client line:", repr(client_line))
    assert "BLOQUEIO" in block_line and "Bloqueado" in block_line
    assert _day_header_above(lines, block_line) == "*quinta-feira, 16 de julho de 2026 (2026-07-16)*"
    assert _day_header_above(lines, client_line) == "*quarta-feira, 15 de julho de 2026 (2026-07-15)*"
    # A block is no longer confusable with a client booking: no bogus name gap where the
    # guest would be — the marker occupies the "who" field outright.
    assert " with " not in block_line
    # Real client bookings still name the guest and the professional, in that order.
    assert client_line.index("Neymar Junior") < client_line.index("Dr. Vinicius Vale")


def _day_header_above(lines: "list[str]", row: str) -> str:
    """The nearest bold day header preceding ``row`` — which day the listing filed it under."""
    head = ""
    for ln in lines:
        if ln.startswith("*"):
            head = ln
        if ln == row:
            return head
    raise AssertionError(f"row not found in listing: {row!r}")

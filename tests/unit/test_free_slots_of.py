"""Round-trip twin for ``free_slots_of`` — the reader half of the availability line.

``check_availability`` is the only place a FREE slot is printed, and ``free_slots_of`` is its
structured reader in the SAME module. The point of these tests: a slot PRINTED by the real tool
and READ BACK by ``free_slots_of`` gives the SAME set, so a consumer that refuses to act on an
hour no read returned (the host's retention guard) can trust the parse — and a change to the
line's WORDING breaks the twin HERE, in this repo, never a downstream consumer in silence.
"""

from __future__ import annotations

import pytest

from cogno_praxis.scheduler.server import build_server, free_slots_of, _seeded_service

_FUT = "2026-12-14"          # a Monday, well into the future (scheduling starts from tomorrow)


@pytest.mark.asyncio
async def test_round_trip_through_the_real_printer():
    """Print real availability through the MCP tool, read it back — the SAME set of hours.

    Goes through ``build_server`` → ``check_availability``, the actual line the model reads, so a
    change to the f-string's wording (the host's parser depends on it) fails this twin first."""
    mcp = build_server(_seeded_service())
    out = await mcp.call_tool("check_availability", {"host_id": "dr_silva", "date": _FUT})
    text = out[1]["result"]
    assert text.startswith("Free slots for "), text        # the shape we are reading back

    parsed = free_slots_of(text)
    assert list(parsed.keys()) == [("dr_silva", _FUT)], parsed
    hours = parsed[("dr_silva", _FUT)]
    # Every printed HH:MM came back, and only those — the round-trip is lossless.
    for token in text.split(": ", 1)[1].split(", "):
        assert token in hours, (token, hours)
    assert len(hours) == len(text.split(": ", 1)[1].split(", "))


def test_the_overflow_slots_are_filed_under_the_next_day():
    """The full-day overflow line offers the NEXT day's slots; they belong to that day, not the
    full one — a guard that reads this must not arm the full day it says has nothing."""
    line = ("Dr. Silva (dr_silva) has no free slots on 2026-12-14. "
            "Next available day is 2026-12-15: 14:00, 15:00 — offer this to the client.")
    assert free_slots_of(line) == {("dr_silva", "2026-12-15"): {"14:00", "15:00"}}


def test_the_host_id_is_the_parenthesised_tail():
    """The professional is echoed as ``Name (host_id)``; the id the guard matches is the tail."""
    line = "Free slots for Dr. Marina Aloe (pro_marina) on 2026-12-14: 09:00"
    assert free_slots_of(line) == {("pro_marina", "2026-12-14"): {"09:00"}}


@pytest.mark.parametrize("line", [
    "Dr. Silva (dr_silva) has no free slots on 2026-12-14 (and none in the next two weeks).",
    "No appointments found.",
    "Booked dr_silva on 2026-12-14 at 09:00.",
    "",
])
def test_a_line_with_no_free_slots_yields_nothing(line):
    """Anything that is not a free-slot listing — a no-slot line, a booking, a listing, empty —
    reads as ``{}``: the guard then has no anchor and (fail-closed) refuses."""
    assert free_slots_of(line) == {}

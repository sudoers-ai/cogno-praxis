"""The agenda a booking LANDS ON is the agenda the reply NAMES — and a doubt writes nothing.

Live trace 731 (2026-09-03), a fixed-scenario run: ``list_schedulable_hosts`` returned two
professionals, and the model then called ``book_appointment`` with a third id that was in
neither line of that list, carrying ``host_name`` for a professional who does not work here.
The turn answered *"Booked … with <that name>"*. Three separate things let a booking end up on
one person's calendar while the sentence says another's:

* the id was never re-checked against the catalogue the model had just been shown;
* resolution may SUBSTITUTE (a name-slug for a real id, a lone specialty for the one
  host that has it) and both tools echoed the caller's own argument back, so the substitution
  read as agreement;
* ``book`` stored ``host_name or host.name`` — the caller's string won — so the row itself
  recorded a name that need not belong to the agenda it sits in.

The property under test is one sentence: **whoever ends up in the row is who the answer names,
and any doubt about who that is produces a question and zero writes.** A booking that does not
happen costs the client one question; a booking in the wrong calendar costs two people a day
and a rescheduling that may no longer fit.

Every name and id here is invented.
"""
from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.scheduler.server import build_server
from cogno_praxis.scheduler.service import SchedulerError, SchedulerService
from cogno_praxis.scheduler.store import Appointment, Host, InMemoryAppointmentStore

_TODAY = date(2026, 7, 1)
_FUT = "2026-07-02"          # a Thursday, inside the working week


class _WatchedStore(InMemoryAppointmentStore):
    """A store that counts every ``add`` it is asked to perform.

    The assertion that matters in a refusal is not the wording — it is that nothing left the
    vertical. Reading the row dict alone would pass just as happily over a write that was
    inserted and then rolled back, and "no write was attempted" is the stronger claim.
    """

    # A plain class attribute, shadowed per instance on the first write: the parent is a
    # dataclass and this subclass is not, so an annotated field here would never be
    # initialised by the generated ``__init__``.
    writes = 0

    def add(self, appointment: Appointment) -> None:
        self.writes += 1
        super().add(appointment)


def _store() -> InMemoryAppointmentStore:
    st = InMemoryAppointmentStore()
    st.hosts["pro_marina"] = Host("pro_marina", "Dra. Marina Aloe", "Dermatologist")
    st.hosts["pro_nuno"] = Host("pro_nuno", "Dr. Nuno Pilar", "Cardiologist")
    return st


def _watched() -> _WatchedStore:
    st = _WatchedStore()
    st.hosts["pro_marina"] = Host("pro_marina", "Dra. Marina Aloe", "Dermatologist")
    st.hosts["pro_nuno"] = Host("pro_nuno", "Dr. Nuno Pilar", "Cardiologist")
    return st


def _svc(st: InMemoryAppointmentStore | None = None) -> SchedulerService:
    return SchedulerService(st if st is not None else _store(), today=lambda: _TODAY)


def _rows(st: InMemoryAppointmentStore) -> list[Appointment]:
    return list(st.appointments.values())


# ── the id the model chose is not in the catalogue it was shown ───────────────────────
def test_an_id_outside_the_catalogue_is_refused_and_writes_nothing():
    """Trace 731, replayed: an id that ``list_schedulable_hosts`` did not list.

    The refusal has to carry the roster, because the model's next move without one is to guess
    again — and a second guess is the same coin flip that produced the incident.
    """
    st = _watched()
    svc = _svc(st)
    listed = {h.host_id for h in svc.list_hosts()}
    assert "9000000001" not in listed        # the control: the id really is outside the catalogue

    with pytest.raises(SchedulerError) as exc:
        svc.book("9000000001", _FUT, "10:00", "Client One", host_name="Dr. Someone Synthetic")

    msg = str(exc.value)
    assert st.writes == 0, "a refused booking reached the store"
    assert _rows(st) == [], "a refused booking wrote a row"
    assert "Dra. Marina Aloe" in msg and "Dr. Nuno Pilar" in msg, msg
    assert "NOTHING was written" in msg, msg
    assert "Do NOT pick one yourself" in msg, msg


def test_the_read_refuses_the_same_id_the_write_refuses():
    """``check_availability`` answered "Free slots for 9000000001" in the live trace — a read
    that accepts an unlisted agenda is what tells the model the id was fine."""
    svc = _svc()
    with pytest.raises(SchedulerError, match="unknown host"):
        svc.check_availability("9000000001", _FUT)


# ── the id and the name are two different people ──────────────────────────────────────
def test_an_id_and_a_name_that_are_two_people_refuse_and_write_nothing():
    """The client said one professional; the call carries another's id. Nothing is written.

    This is the branch the mutation below removes: taking the id as it came, which is what the
    vertical did when neither field was compared against the other.
    """
    st = _watched()
    svc = _svc(st)

    with pytest.raises(SchedulerError) as exc:
        svc.book("pro_nuno", _FUT, "10:00", "Client Two", host_name="Dra. Marina Aloe")

    msg = str(exc.value)
    assert st.writes == 0, "a refused booking reached the store"
    assert _rows(st) == [], "a booking landed on the id while the client had named someone else"
    assert "Dra. Marina Aloe" in msg and "Dr. Nuno Pilar" in msg, msg
    assert "NOTHING was written" in msg, msg


# ── a name nobody here answers to → the roster, never a substitute ────────────────────
def test_a_name_nobody_answers_to_proposes_the_whole_roster():
    st = _store()
    svc = _svc(st)

    with pytest.raises(SchedulerError) as exc:
        svc.book("", _FUT, "10:00", "Client Three", host_name="Dra. Ines Bramante")

    msg = str(exc.value)
    assert _rows(st) == []
    for h in svc.list_hosts():
        assert h.name in msg, f"{h.name} missing from the proposal: {msg}"
    assert "ask which one they mean" in msg, msg


# ── a name two professionals answer to → a question, not a coin flip ──────────────────
def test_an_ambiguous_name_asks_which_one_and_writes_nothing():
    st = InMemoryAppointmentStore()
    st.hosts["pro_a"] = Host("pro_a", "Dra. Marina Aloe", "Dermatologist")
    st.hosts["pro_b"] = Host("pro_b", "Dr. Marina Bregt", "Cardiologist")
    svc = _svc(st)

    with pytest.raises(SchedulerError) as exc:
        svc.book("", _FUT, "10:00", "Client Four", host_name="Marina")

    msg = str(exc.value)
    assert _rows(st) == []
    assert "ambiguous" in msg and "Dra. Marina Aloe" in msg and "Dr. Marina Bregt" in msg, msg
    assert "do NOT pick one yourself" in msg, msg


# ── the negative twin: strict must not mean paralysed ─────────────────────────────────
def test_a_name_that_resolves_to_exactly_one_professional_books():
    """Without this, "when in doubt write nothing" quietly becomes "never write anything".

    Two shapes that must still go through: the catalogue name in full, and a name the client
    gave partially ("Marina") that only one professional here can be.
    """
    st = _store()
    svc = _svc(st)

    full = svc.book("pro_marina", _FUT, "10:00", "Client Five", host_name="Dra. Marina Aloe")
    assert full.host_id == "pro_marina"

    partial = svc.book("", _FUT, "11:00", "Client Six", host_name="Marina")
    assert partial.host_id == "pro_marina"
    assert len(_rows(st)) == 2


def test_a_plain_catalogue_id_with_no_name_still_books():
    """The commonest call of all — the model matched the roster and passes only the id."""
    st = _store()
    svc = _svc(st)
    appt = svc.book("pro_nuno", _FUT, "10:00", "Client Seven")
    assert appt.host_id == "pro_nuno" and len(_rows(st)) == 1


# ── the substitution is audible ───────────────────────────────────────────────────────
def test_the_row_records_the_agenda_it_sits_in_not_the_word_it_was_given():
    """``host_name`` is an INPUT to the decision, never an output copied down.

    A specialty resolves to the one professional who has it — a legitimate substitution. What
    was not legitimate is that the row and the reply then repeated the caller's own string, so
    nothing downstream (the listing, the notification, the client) could see it happen.
    """
    st = _store()
    svc = _svc(st)
    appt = svc.book("Cardiologist", _FUT, "10:00", "Client Eight")
    assert appt.host_id == "pro_nuno"
    assert appt.host_name == "Dr. Nuno Pilar", "the row kept the caller's word, not the catalogue"

    # And the same when the caller's word points at the RIGHT professional in the wrong words:
    # agreeing on who it is does not make the client's phrasing the row's record of them.
    partial = svc.book("pro_nuno", _FUT, "11:00", "Client Eight Bis", host_name="Nuno")
    assert partial.host_id == "pro_nuno" and partial.host_name == "Dr. Nuno Pilar"


@pytest.mark.asyncio
async def test_the_booking_reply_names_the_professional_the_row_is_under():
    """Through the MCP tool, which is the surface the model and the judge actually read."""
    st = _store()
    mcp = build_server(_svc(st))
    tools = {t.name: t for t in await mcp.list_tools()}
    out = await mcp.call_tool("book_appointment",
                             {"host_id": "Cardiologist", "date": _FUT, "time": "10:00",
                              "with_name": "Client Nine"})
    text = str(out)
    assert "Dr. Nuno Pilar" in text, text
    assert "pro_nuno" in text, text
    assert "host_name" in tools["book_appointment"].inputSchema["properties"]


@pytest.mark.asyncio
async def test_the_availability_reply_names_the_professional_it_read():
    """The live trace echoed the caller's raw argument — "Free slots for <the id it asked
    about>" — so a read of a DIFFERENT agenda was indistinguishable from a read of that one."""
    mcp = build_server(_svc())
    out = str(await mcp.call_tool("check_availability",
                                  {"host_id": "Cardiologist", "date": _FUT}))
    assert "Dr. Nuno Pilar" in out and "pro_nuno" in out, out
    assert "Free slots" in out, out


@pytest.mark.asyncio
async def test_availability_takes_the_clients_word_too():
    """The read carries the same guard as the write, and refuses through the tool surface.

    It reaches the EGO as a recoverable tool error — which is the channel the roster has to
    travel down, since the refusal is the message the model must relay."""
    from mcp.server.fastmcp.exceptions import ToolError

    mcp = build_server(_svc())
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool("check_availability",
                            {"host_id": "pro_nuno", "date": _FUT,
                             "host_name": "Dra. Marina Aloe"})
    msg = str(exc.value)
    assert "Dra. Marina Aloe" in msg and "Dr. Nuno Pilar" in msg, msg
    assert "two different agendas" in msg, msg

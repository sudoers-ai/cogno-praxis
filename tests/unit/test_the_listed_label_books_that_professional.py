"""The line ``list_schedulable_hosts`` prints for a professional resolves back to that professional.

The list names each professional as ``<id>: <name> (<role>)``. A model that is asked to pass
``host_name`` copies the part after the id — ``"Dr. Quintino Abravel (Cardiologista)"`` — and the
resolver used to refuse it: the full key did not equal the name, the word ``cardiologista`` is
not a word of the name, and the whole string is not the role. Measured on a secretary bench run
(local model): the booking was held for confirmation with that ``host_name``, the client said
«sim», and the confirmed call came back "unknown host … nobody bookable here goes by that" for
the very professional the list had just shown. The reply then told the client the doctor was
not available, and every later turn of the reschedule flow worked on a booking that never
existed.

The property: **the label the list prints is accepted as exactly that professional**, and
nothing else about the resolver widens — a label with another role, or another professional's
label next to this one's id, is still refused and writes nothing.

Every name and id here is invented.
"""
from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.scheduler.server import build_server
from cogno_praxis.scheduler.service import SchedulerError, SchedulerService, host_label
from cogno_praxis.scheduler.store import Host, InMemoryAppointmentStore

_TODAY = date(2026, 7, 1)
_FUT = "2026-07-02"          # a Thursday, inside the working week


def _store() -> InMemoryAppointmentStore:
    st = InMemoryAppointmentStore()
    st.hosts["pro_quintino"] = Host("pro_quintino", "Dr. Quintino Abravel", "Cardiologista")
    st.hosts["pro_zelinda"] = Host("pro_zelinda", "Dra. Zelinda Marquesi Toro", "Endócrino")
    st.hosts["pro_sala"] = Host("pro_sala", "Sala de exames", "")
    return st


def _svc(st: InMemoryAppointmentStore | None = None) -> SchedulerService:
    return SchedulerService(st if st is not None else _store(), today=lambda: _TODAY)


def _text(call_result) -> str:
    content = call_result[0]
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


async def _listed_labels(svc: SchedulerService) -> dict[str, str]:
    """{host_id: the text after ``<id>: `` on the line the list tool printed}."""
    out = _text(await build_server(svc).call_tool("list_schedulable_hosts", {}))
    labels = {}
    for line in out.splitlines():
        hid, _, label = line.partition(": ")
        labels[hid] = label
    return labels


# ── the twin: red before the change ─────────────────────────────────────────────
async def test_every_listed_label_resolves_to_its_own_professional():
    svc = _svc()
    labels = await _listed_labels(svc)
    assert labels["pro_quintino"] == "Dr. Quintino Abravel (Cardiologista)"
    for hid, label in labels.items():
        assert svc.resolve_agenda(hid, label).host_id == hid
        assert svc.resolve_agenda("", label).host_id == hid


async def test_a_booking_confirmed_with_the_listed_label_is_written_on_that_agenda():
    st = _store()
    svc = _svc(st)
    label = (await _listed_labels(svc))["pro_quintino"]
    mcp = build_server(svc)
    out = _text(await mcp.call_tool("book_appointment", {
        "host_id": "pro_quintino", "date": _FUT, "time": "10:00",
        "with_name": "Belmira Quostral", "host_name": label}))
    assert out.startswith("Booked "), out
    rows = list(st.appointments.values())
    assert [(r.host_id, r.host_name) for r in rows] == [("pro_quintino", "Dr. Quintino Abravel")]


def test_the_list_line_is_spelled_by_host_label():
    """One spelling: the list prints ``host_label`` and the resolver accepts ``host_label``."""
    h = Host("pro_x", "Dra. Zelinda Marquesi Toro", "Endócrino")
    assert host_label(h) == "Dra. Zelinda Marquesi Toro (Endócrino)"
    assert host_label(Host("pro_y", "Sala de exames", "")) == "Sala de exames"


# ── controls: nothing else widens ───────────────────────────────────────────────
def test_the_name_with_another_role_is_still_refused():
    st = _store()
    svc = _svc(st)
    with pytest.raises(SchedulerError, match="unknown host"):
        svc.resolve_agenda("", "Dr. Quintino Abravel (Dermatologista)")
    with pytest.raises(SchedulerError, match="unknown host"):
        svc.book("", _FUT, "10:00", "Belmira Quostral",
                 host_name="Dr. Quintino Abravel (Dermatologista)")
    assert st.appointments == {}


async def test_another_professionals_label_next_to_this_id_is_still_two_agendas():
    """Now that a label resolves, it must still meet the id: another professional's label next to
    this professional's id is the two-agendas refusal. (Before the change the label resolved to
    nobody, so this was refused as an unknown host — also with nothing written.)"""
    st = _store()
    svc = _svc(st)
    other = (await _listed_labels(svc))["pro_zelinda"]
    with pytest.raises(SchedulerError, match="two different agendas"):
        svc.book("pro_quintino", _FUT, "10:00", "Belmira Quostral", host_name=other)
    assert st.appointments == {}


def test_the_plain_name_and_the_lone_role_resolve_as_before():
    svc = _svc()
    assert svc.resolve_agenda("", "Dr. Quintino Abravel").host_id == "pro_quintino"
    assert svc.resolve_agenda("", "Quintino").host_id == "pro_quintino"
    assert svc.resolve_agenda("", "cardiologista").host_id == "pro_quintino"


def test_the_label_tells_two_namesakes_apart():
    """Two professionals with the same name: the bare name asks which one; the listed label is one."""
    st = InMemoryAppointmentStore()
    st.hosts["pro_a"] = Host("pro_a", "Dra. Odília Fenstra", "Cardiologista")
    st.hosts["pro_b"] = Host("pro_b", "Dra. Odília Fenstra", "Pediatra")
    svc = _svc(st)
    with pytest.raises(SchedulerError, match="ambiguous"):
        svc.resolve_agenda("", "Dra. Odília Fenstra")
    assert svc.resolve_agenda("", "Dra. Odília Fenstra (Pediatra)").host_id == "pro_b"

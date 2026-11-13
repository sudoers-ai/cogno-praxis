"""An invented ``host_id`` is REWRITTEN to the professional the client NAMED — when, and only
when, that name resolves to exactly one bookable host.

The shape, measured live over a scheduling conversation (2026-11): a model held a
``book_appointment`` whose ``host_id`` no professional in the catalogue answers to (``REDACTED``,
a value it made up) beside the professional the client actually named (``host_name="Dr. Ulpiano
Krusvel"``). On the base tree the id's own refusal fires before the name is ever consulted, so
the call answers «unknown host» although the client named a real professional; the
availability read goes through the same door. The repair lets the NAME decide the agenda — the id is rewritten to theirs — which is the
same thing a human reading «Dr. Ulpiano» next to a broken id would do.

The rule is one function, ``names.host_id_rewrite``, shared with the booking door and (in the
host that drives this vertical) its held-booking gate, so what the resolver accepts the gate
arms. It stays STRICT where strictness protects a write:

* a VALID id carrying the name of a DIFFERENT professional is NOT repaired — it is the «two
  agendas» refusal (the id is real; the disagreement is the signal, not noise);
* a name that matches nobody, or two namesakes, does NOT rescue the call — the id's own refusal
  (or «which one?») stays.

Every name and id here is invented.
"""
from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.scheduler.names import host_id_rewrite
from cogno_praxis.scheduler.service import SchedulerError, SchedulerService
from cogno_praxis.scheduler.store import Host, InMemoryAppointmentStore

_TODAY = date(2026, 11, 13)
_FUT = "2026-11-16"           # a Monday — a working day for the default scheduler config

_ULPIANO = Host("h-7f3a2c", "Dr. Ulpiano Krusvel", "Cardiologia")
_BRISELIA = Host("h-91bd04", "Dra. Brisélia Tondravel", "Dermatologia")
# A second Ulpiano, so «Dr. Ulpiano» alone names TWO people (the ambiguity control).
_ULPIANO_2 = Host("h-4c0d11", "Dr. Ulpiano Brendvarn", "Ortopedia")

# The id the model made up in the live trace — no professional answers to it (its word tokens
# are not a subset of any host's name), so it is a genuine invented id, not a spelling of a real
# one. The control below pins that it truly resolves to nobody on its own.
_INVENTED = "REDACTED"


def _svc(*hosts: Host) -> SchedulerService:
    store = InMemoryAppointmentStore()
    for h in (hosts or (_ULPIANO, _BRISELIA)):
        store.hosts[h.host_id] = h
    return SchedulerService(store, today=lambda: _TODAY)


# ── the pure rule ────────────────────────────────────────────────────────────────────────────
def test_the_invented_id_on_its_own_names_nobody():
    """The control for the whole file: the invented id is not a spelling of a real id."""
    svc = _svc()
    from cogno_praxis.scheduler.names import host_candidates
    assert host_candidates(_INVENTED, svc.list_hosts()) == []


def test_an_invented_id_is_rewritten_to_the_named_professional():
    hosts = _svc().list_hosts()
    # the measured held form carries the FULL name; a PARTIAL name — «Dr. Ulpiano» ⊆ «Dr. Ulpiano
    # Krusvel», the honorific dropped — resolves too, because he is the only Ulpiano.
    assert host_id_rewrite(_INVENTED, "Dr. Ulpiano", hosts).host_id == "h-7f3a2c"
    assert host_id_rewrite(_INVENTED, "Dr. Ulpiano Krusvel", hosts).host_id == "h-7f3a2c"


def test_a_name_that_matches_nobody_does_not_repair():
    assert host_id_rewrite(_INVENTED, "Dra. Belmira Quostral", _svc().list_hosts()) is None


def test_a_blank_name_does_not_repair():
    assert host_id_rewrite(_INVENTED, "", _svc().list_hosts()) is None


def test_two_namesakes_do_not_repair():
    hosts = _svc(_ULPIANO, _ULPIANO_2, _BRISELIA).list_hosts()
    assert host_id_rewrite(_INVENTED, "Dr. Ulpiano", hosts) is None


def test_a_valid_id_is_left_alone_even_with_another_name():
    # The id already names someone → not a repair case; the «two agendas» refusal below is what
    # judges a valid id against a conflicting name, not this rewrite.
    hosts = _svc().list_hosts()
    assert host_id_rewrite("h-7f3a2c", "Dra. Brisélia Tondravel", hosts) is None


def test_a_one_character_initial_never_decides_an_agenda():
    # host_candidates drops 1-char query tokens on purpose; the rewrite inherits that, so «U.»
    # does not resolve «Ulpiano». (No prefix matching was added.)
    assert host_id_rewrite(_INVENTED, "Dr. U", _svc().list_hosts()) is None


# ── through resolve_agenda: the read and the write share the door ─────────────────────────────
def test_resolve_agenda_repairs_the_read():
    # check_availability's door is resolve_agenda; on the base tree it raised «unknown host».
    host = _svc().resolve_agenda(_INVENTED, "Dr. Ulpiano")
    assert host.host_id == "h-7f3a2c" and host.name == "Dr. Ulpiano Krusvel"


def test_the_read_returns_slots_instead_of_unknown_host():
    # On the base tree this read raised «unknown host» (the id's refusal, before the name was
    # consulted); repaired, it returns the Ulpiano's free slots for the day.
    svc = _svc()
    slots = svc.check_availability(_INVENTED, _FUT, host_name="Dr. Ulpiano")
    assert slots and "14:00" in slots


def test_the_write_books_the_named_agenda():
    svc = _svc()
    appt = svc.book(_INVENTED, _FUT, "14:00", "Teodulo Varnisk", host_name="Dr. Ulpiano")
    assert appt.host_id == "h-7f3a2c"


# ── the controls stay as they were (nothing is repaired past the rule) ────────────────────────
def test_a_valid_id_with_another_persons_name_is_two_agendas_not_repaired():
    """Trace 731: a real id + a name for a DIFFERENT professional writes nothing, and is NOT
    quietly rewritten to either."""
    svc = _svc()
    with pytest.raises(SchedulerError) as exc:
        svc.book("h-7f3a2c", _FUT, "14:00", "Teodulo Varnisk", host_name="Dra. Brisélia Tondravel")
    msg = str(exc.value)
    assert "two different" in msg or "two agenda" in msg
    assert "Dr. Ulpiano Krusvel" in msg and "Dra. Brisélia Tondravel" in msg


def test_an_invented_id_with_an_unknown_name_keeps_the_id_refusal():
    svc = _svc()
    with pytest.raises(SchedulerError) as exc:
        svc.check_availability(_INVENTED, _FUT, host_name="Dra. Belmira Quostral")
    assert "unknown host" in str(exc.value)


def test_an_invented_id_with_an_ambiguous_name_lists_the_candidates():
    svc = _svc(_ULPIANO, _ULPIANO_2, _BRISELIA)
    with pytest.raises(SchedulerError) as exc:
        svc.check_availability(_INVENTED, _FUT, host_name="Dr. Ulpiano")
    msg = str(exc.value)
    assert "Dr. Ulpiano Krusvel" in msg and "Dr. Ulpiano Brendvarn" in msg

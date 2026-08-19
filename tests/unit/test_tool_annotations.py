"""A mutating tool is either GATED or UNDOABLE — swept across every vertical.

The host's confirmation gate (cogno-anima gate B) decides by tool NAME, with no arguments, and
it is opt-in: a tool that does not declare ``destructiveHint`` is simply never held. So every
mutating tool the model can reach is one of two things, and the file that ships it has to say
which:

  * ``destructiveHint=True`` — the gate holds it, the host runs its confirm UX;
  * on ``_UNDOABLE`` below — reachable damage can be walked back, and the entry names HOW.

`update_appointment_status` was neither, and that is the whole story of 2026-08-18: a single
tool taking a free-text status spanned opposite risks, so cancelling was reachable through the
non-destructive twin while `cancel_appointment` itself was held. The per-tool assertions in
`test_scheduler_server.py` pin what each annotation IS; nothing pinned that the SET of them
covers every mutation. This does, for all three verticals at once — a new mutating tool cannot
be added anywhere without an author saying, here, which of the two it is.

The claims are MEASURED, not asserted: `test_every_undoable_tool_really_undoes` below performs
each undo. An entry on this list that is merely believed is exactly the failure it exists to
prevent — `complete_appointment` sat here in spirit from 2026-08-19 while being reversible only
on the appointment's own DAY, because the "already due" rule and the "no past CONFIRMED" rule
closed on each other. Marking yesterday's attendance was permanent through a non-destructive
verb, which is the same bypass, on the side that had just been declared safe.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from cogno_praxis.bookkeeper.server import build_server as build_bookkeeper
from cogno_praxis.coordinator.server import build_server as build_coordinator
from cogno_praxis.scheduler.server import build_server as build_scheduler

# tool → how the damage is walked back. Being here is a CLAIM, made once, and measured below.
_UNDOABLE: "dict[str, str]" = {
    "book_appointment": "cancel_appointment frees the slot again",
    "block_schedule": "a block IS an appointment row — cancel_appointment reopens the time",
    # NOT "back to PENDING": server.py's split deliberately dropped that transition and no
    # tool exposes it. The first version of this entry claimed it anyway, and the test below
    # "measured" it through `svc.update_status` — the SERVICE api, one layer under the
    # surface this file is about. A claim asserted at the wrong layer is the same mistake the
    # header credits for the `complete_appointment` hole.
    "confirm_appointment": "cancel_appointment ends the row a wrong confirm accepted",
    "complete_appointment": "update_status moves it back to CONFIRMED — including in the past",
    "set_auto_confirm": "call it again with the other value",
    "set_schedule_settings": "write the previous values back",
    "add_income": "remove_by_search",
    "add_outcome": "remove_by_search",
}

_BUILDERS = {"scheduler": build_scheduler, "bookkeeper": build_bookkeeper,
             "coordinator": build_coordinator}


async def _annotations(vertical: str) -> "dict[str, object]":
    return {t.name: t.annotations for t in await _BUILDERS[vertical]().list_tools()}


@pytest.mark.parametrize("vertical", sorted(_BUILDERS))
async def test_every_mutating_tool_is_gated_or_declared_undoable(vertical):
    ann = await _annotations(vertical)
    ungoverned = []
    for name, a in sorted(ann.items()):
        read_only = getattr(a, "readOnlyHint", None)
        if read_only is True:
            continue                                    # a read cannot damage anything
        if read_only is None:
            # NOT a read — an UNDECLARED tool. `@mcp.tool()` with no `annotations=` yields
            # `annotations is None`, which is the DEFAULT, so skipping it let the dangerous
            # case through the one check written to catch it: such a tool escapes this sweep
            # and gate B (opt-in on destructiveHint) at the same time. Verified against
            # FastMCP. Fall through and demand a declaration.
            ungoverned.append(f"{name} (sem annotations)")
            continue
        if getattr(a, "destructiveHint", None) is True:
            continue                                    # gate B holds it
        if name not in _UNDOABLE:
            ungoverned.append(name)
    assert not ungoverned, (
        f"{vertical}: {ungoverned} mutate, carry no destructiveHint, and claim no undo. The "
        f"confirmation gate decides by NAME and is opt-in, so these are reachable damage "
        f"nothing holds. Either annotate destructiveHint=True or add the tool to _UNDOABLE "
        f"saying how it is walked back — and add its case to "
        f"test_every_undoable_tool_really_undoes, because an undo nobody performs is how "
        f"`complete_appointment` spent a day being 'reversible' in one direction only.")


async def test_the_undoable_list_has_no_stale_or_contradictory_entries():
    """An entry naming a tool that no longer exists, or one the gate already holds, is noise
    that makes the sweep above read as broader coverage than it has."""
    live = {}
    for vertical in _BUILDERS:
        live.update(await _annotations(vertical))
    unknown = sorted(set(_UNDOABLE) - set(live))
    assert not unknown, f"_UNDOABLE names tools that do not exist: {unknown}"
    both = sorted(n for n in _UNDOABLE
                  if getattr(live[n], "destructiveHint", None) is True)
    assert not both, f"gated AND claimed undoable — say one thing: {both}"
    reads = sorted(n for n in _UNDOABLE
                   if getattr(live[n], "readOnlyHint", None) is not False)
    assert not reads, f"_UNDOABLE lists a read-only tool: {reads}"


# ── the claims, performed ─────────────────────────────────────────────────────────────
_TODAY = date(2026, 7, 6)
_FUT = (_TODAY + timedelta(days=1)).isoformat()


def _sched(today: date = _TODAY):
    from cogno_praxis.scheduler import (Host, InMemoryAppointmentStore, SchedulerService)
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    return SchedulerService(store, today=lambda: today)


def _past_row(days_back: int, status: str = "CONFIRMED"):
    from cogno_praxis.scheduler import (Host, InMemoryAppointmentStore, SchedulerService)
    from cogno_praxis.scheduler.store import Appointment
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "GP")
    store.add(Appointment(appointment_id="x1", host_id="dr_silva", host_name="Dr. Silva",
                          date=(_TODAY - timedelta(days=days_back)).isoformat(),
                          time="09:00", with_name="Ana", status=status))
    return SchedulerService(store, today=lambda: _TODAY)


def test_every_undoable_tool_really_undoes():
    """Each claim in `_UNDOABLE`, performed rather than believed."""
    svc = _sched()
    a = svc.book("dr_silva", _FUT, "09:00", "Ana")           # book → cancel
    svc.cancel(a.appointment_id)
    assert "09:00" in svc.check_availability("dr_silva", _FUT)

    svc = _sched()                                            # block → cancel
    blocks = svc.block_schedule("dr_silva", _FUT, start_time="09:00")
    assert "09:00" not in svc.check_availability("dr_silva", _FUT)
    svc.cancel(blocks[0].appointment_id)
    assert "09:00" in svc.check_availability("dr_silva", _FUT)

    svc = _sched()                                            # confirm → cancel
    a = svc.book("dr_silva", _FUT, "09:00", "Ana")
    svc.update_status(a.appointment_id, "CONFIRMED")
    assert svc.cancel(a.appointment_id)[0].status == "CANCELED"

    svc = _sched()                                            # set_auto_confirm → flip back
    before = svc.store.get_host("dr_silva").auto_confirm
    svc.set_auto_confirm("dr_silva", not before)
    assert svc.set_auto_confirm("dr_silva", before).auto_confirm == before

    svc = _sched()                                            # settings → write back
    before_cfg = svc.get_settings()
    svc.set_settings(work_start="08:00")
    svc.set_settings(work_start=before_cfg["work_start"])
    assert svc.get_settings() == before_cfg

    from cogno_praxis.bookkeeper.service import BookkeeperService  # add_* → remove_by_search
    from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore
    bk = BookkeeperService(InMemoryBookkeeperStore())
    bk.add_income("consulta Ana", 150.0, identity_id="e1")
    bk.add_outcome("material Ana", 20.0, identity_id="e1")
    assert bk.remove_by_search("consulta Ana", identity_id="e1") is not None
    assert bk.remove_by_search("material Ana", identity_id="e1") is not None


@pytest.mark.parametrize("days_back", [0, 1, 7])
def test_undoing_a_completion_reaches_the_PAST_too(days_back):
    """The claim that lets `complete_appointment` ship with no destructiveHint.

    It was true only for ``days_back=0``. Only an already-due appointment may COMPLETE, and a
    past one may not go back to CONFIRMED — the two rules closed on each other, so the window
    was the appointment's own day and nothing after it. The real use is "a Beatriz veio ontem":
    the professional closes out yesterday's attendances, and marking the wrong row was then
    permanent, through a verb the confirmation gate never holds."""
    svc = _past_row(days_back)
    assert svc.update_status("x1", "COMPLETED")[0].status == "COMPLETED"
    assert svc.update_status("x1", "CONFIRMED")[0].status == "CONFIRMED"


@pytest.mark.parametrize("start,target", [
    ("CONFIRMED", "PENDING"),      # confirming/unconfirming the past stays meaningless
    ("PENDING", "CONFIRMED"),
    ("CANCELED", "CONFIRMED"),     # it did not happen; a revival is a new booking
    ("CANCELED", "PENDING"),
    ("COMPLETED", "PENDING"),      # the undo is to CONFIRMED, not back to un-accepted
])
def test_the_past_rule_still_refuses_everything_else(start, target):
    """The control arm. The exemption is ONE transition — an undo of a completion — and
    widening the past rule any further would trade the bypass for a different one."""
    from cogno_praxis.scheduler import SchedulerError

    with pytest.raises(SchedulerError, match="past"):
        _past_row(1, status=start).update_status("x1", target)


def test_the_expired_exemption_does_not_compose_into_a_past_revival():
    """O braço-controle acima semeia um CANCELED NU, e o produto não produz esses.

    `_sweep_expired` escreve `cancel_reason='expired'` em todo PENDING vencido, e com essa
    linha as DUAS isenções se encadeiam: completar (isenção do 'expired') e depois desfazer
    (isenção do undo) chega ao passado-CONFIRMED que o passo direto recusa — e a varredura
    seguinte o torna COMPLETED, isto é, receita faturável numa consulta que ninguém nunca
    confirmou. O teste de um passo ficava verde os dois lados, então "a isenção é UMA
    transição" tinha um teste passando por trás de uma afirmação falsa."""
    from cogno_praxis.scheduler import SchedulerError

    svc = _past_row(1, status="CANCELED")
    svc.store.get("x1").cancel_reason = "expired"          # como a varredura a deixa
    assert svc.update_status("x1", "COMPLETED")[0].status == "COMPLETED"
    with pytest.raises(SchedulerError, match="past"):
        svc.update_status("x1", "CONFIRMED")

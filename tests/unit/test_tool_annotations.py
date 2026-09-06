"""A mutating tool is GATED, UNDOABLE, or it ASKS BY ITSELF — swept across every vertical.

The host's confirmation gate (cogno-anima gate B) decides by tool NAME, with no arguments, and
it is opt-in: a tool that does not declare ``destructiveHint`` is simply never held. So every
mutating tool the model can reach is one of three things, and the file that ships it has to say
which:

  * ``destructiveHint=True`` — gate B holds it, the host runs its confirm UX;
  * on ``_UNDOABLE`` below — reachable damage can be walked back, and the entry names HOW;
  * on ``_ASKS_ITSELF`` below — the call RUNS, READS, and refuses to commit until a second call
    carries an argument it can only have learned from the first. That is cogno-anima's gate C.

The third arrived on 2026-09-03 with one member, and it is a WIDENING of this sweep, so it is
worth saying exactly what it does and does not buy. Gate B is a claim about a NAME, resolved
before anything runs: it can say a deletion is coming and never say WHICH row. Gate C is a fact
about a CALL, and only a call that RAN can state it. The two cannot be held at once — B
pre-empts C by construction, because a tool it holds never executes — so a tool whose danger is
per-call has to give up the first in order to reach the second.

What keeps that from being a hole is that the third category is not a promise about behaviour,
it is a claim about REACHABILITY: the tool's write path must be unreachable without the
argument. ``test_every_asking_tool_really_refuses_to_commit_unasked`` performs it, in the same
spirit as its ``_UNDOABLE`` neighbour and for the same reason — measured 2026-09-03, reverting
``remove_by_search`` to its one-shot ancestor turns 10 tests red, and a gate C leaning on an
UNMEASURED promise would be the ``complete_appointment`` failure a third time.

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
from cogno_praxis.company.server import build_server as build_company
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
    # The row's key is DERIVED from the accent-folded name, so this is the `set_auto_confirm`
    # shape of undo: the correction IS the same call. The residual is named rather than
    # implied — a typo in the NAME keys a DIFFERENT row, and the stray registration stays; no
    # tool removes it (the store port carries `delete` and deliberately does not expose it,
    # because a delete tool here is a new destructive capability, not part of a move).
    "company_registration": "register the same company again — the folded name is the key, so "
                            "the corrected values UPDATE that row",
}

# tool → the argument it requires in order to commit, which a caller can only have learned from
# the tool's own first answer. Being here is a CLAIM — that the write path is UNREACHABLE
# without that argument — and it is performed by
# ``test_every_asking_tool_really_refuses_to_commit_unasked`` below.
_ASKS_ITSELF: "dict[str, str]" = {
    "remove_by_search": "confirm_tx_id — the id of the row it proposed after reading the ledger",
}

_BUILDERS = {"scheduler": build_scheduler, "bookkeeper": build_bookkeeper,
             "coordinator": build_coordinator, "company": build_company}


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
        if name in _ASKS_ITSELF:
            continue                                    # gate C: it runs, reads, and asks
        if name not in _UNDOABLE:
            ungoverned.append(name)
    assert not ungoverned, (
        f"{vertical}: {ungoverned} mutate, carry no destructiveHint, claim no undo and do not "
        f"ask by themselves. The confirmation gate decides by NAME and is opt-in, so these are "
        f"reachable damage nothing holds. Say which of the THREE they are: annotate "
        f"destructiveHint=True; or add the tool to _UNDOABLE saying how it is walked back; or "
        f"add it to _ASKS_ITSELF naming the argument it requires in order to commit — and add "
        f"its case to the matching performed test, because a claim nobody performs is how "
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
    # the third list, held to the same standard
    unknown = sorted(set(_ASKS_ITSELF) - set(live))
    assert not unknown, f"_ASKS_ITSELF names tools that do not exist: {unknown}"
    gated = sorted(n for n in _ASKS_ITSELF
                   if getattr(live[n], "destructiveHint", None) is True)
    assert not gated, (
        f"gate B AND gate C claimed for the same tool: {gated}. They cannot both hold — B "
        f"stops the call by NAME before it runs, so the question C exists to ask is never "
        f"asked. Pick one, and if it is C, drop the destructiveHint.")
    reads = sorted(n for n in _ASKS_ITSELF
                   if getattr(live[n], "readOnlyHint", None) is not False)
    assert not reads, f"_ASKS_ITSELF lists a read-only tool: {reads}"


async def test_exactly_these_tools_are_gated_by_name():
    """The blast radius of 2026-09-03, pinned: ONE tool changed annotation, and these did not.

    ``remove_by_search`` moved from gate B to gate C. Nothing else moved, and this is the
    assertion that says so — a reviewer reading "they removed a destructiveHint" needs to see
    the boundary of it, and a future edit that quietly widens the exemption is red here.

    The three that remain are gate B's proper shape: each commits on its FIRST call, so none of
    them has anything to base a grounded question on. Deferring gate B for them — executing and
    only then deciding to hold — would run the cancellation and record the hold afterwards,
    which is why the pre-emption is not a defect to be fixed generically.

    ``send_schedule_to_calendar`` joined them: it MAILS a calendar, which is a write that leaves
    the house and is the one kind no undo reaches — there is no un-sending an e-mail, so the
    ``_UNDOABLE`` door was never open to it, and it commits on its FIRST call, so gate C's door
    was not either. It is here because it is genuinely gate B's shape, not because a
    destructiveHint was the convenient way to satisfy this sweep."""
    live = {}
    for vertical in _BUILDERS:
        live.update(await _annotations(vertical))
    gated = sorted(n for n, a in live.items()
                   if getattr(a, "destructiveHint", None) is True)
    assert gated == ["cancel_appointment", "confirm_swap", "reschedule_appointment",
                     "send_schedule_to_calendar"]


def test_every_asking_tool_really_refuses_to_commit_unasked():
    """Each claim in ``_ASKS_ITSELF``, performed rather than believed.

    The claim is REACHABILITY, so the test is an attempt: call the tool the way a model that
    never got a proposal would, and show the row is still there. Then show the second call —
    carrying the argument the tool itself named — does commit, because a gate that also blocked
    the confirmed path would protect the ledger by breaking it.

    A stale or guessed id must not degrade into "the most recent match": that fallback is what
    would make the id decorative, and it is the difference between an argument that carries
    consent and one that merely accompanies it."""
    from cogno_praxis.bookkeeper.service import BookkeeperService
    from cogno_praxis.bookkeeper.store import InMemoryBookkeeperStore

    assert set(_ASKS_ITSELF) == {"remove_by_search"}, "a new entry needs its own arm here"

    bk = BookkeeperService(InMemoryBookkeeperStore())
    bk.add_outcome("internet janeiro", 100, "e1", tx_date="2026-01-10")
    bk.add_outcome("internet marco", 149.90, "e1", tx_date="2026-03-10")

    def _rows() -> int:
        return int(bk.get_summary("e1", "EMPLOYEE")["outcome_count"])

    # 1. unasked → nothing leaves the store, and the answer is the question
    out = bk.remove_by_search("internet", "e1")
    assert out.needs_confirmation is True and out.removed is None and _rows() == 2

    # 2. a guessed id is not a shortcut into the write path
    assert bk.remove_by_search("internet", "e1", confirm_tx_id="deadbeefcafe").removed is None
    assert _rows() == 2

    # 3. the argument the tool named DOES commit — exactly one row, the one proposed
    proposed = out.proposal
    assert proposed is not None
    removed = bk.remove_by_search("internet", "e1",
                                  confirm_tx_id=proposed.confirm_tx_id).removed
    assert removed is not None and removed["tx_id"] == proposed.entry["tx_id"]
    assert _rows() == 1


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
    # The undo is TWO calls (propose → confirm) and the claim is that the row LEAVES. Asserting
    # the first call is "not None" would now pass over a removal that never happened — the
    # proposal is also not None.
    for q in ("consulta Ana", "material Ana"):
        proposal = bk.remove_by_search(q, identity_id="e1").proposal
        assert proposal is not None, q
        assert bk.remove_by_search(q, identity_id="e1",
                                   confirm_tx_id=proposal.confirm_tx_id).removed is not None, q
    summary = bk.get_summary("e1", "ADMIN")
    assert summary["income_count"] == 0 and summary["outcome_count"] == 0

    from cogno_praxis.company import CompanyService, InMemoryCompanyStore  # register → register
    co = CompanyService(InMemoryCompanyStore())
    co.register("Padaria São João", visual_identity="azul")
    co.register("padaria sao joao", visual_identity="verde")   # the correction, same call
    rows = co.list_companies()
    # The claim is that the wrong value LEAVES and no second row appears. Asserting only the
    # new value would pass over an undo that added a row beside the mistake instead of
    # replacing it — which is exactly the failure mode a name-derived key exists to prevent.
    assert len(rows) == 1 and rows[0].visual_identity == {"visual_identity": "verde"}


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

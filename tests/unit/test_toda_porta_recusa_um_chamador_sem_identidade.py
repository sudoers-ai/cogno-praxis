"""Every public door of the coordinator refuses a caller the turn could not NAME.

``identity_label`` is who is asking. ``""`` is not a caller with no privileges — it is nobody,
and the companies vertical already landed the rule this file points at the coordinator: **an
empty id is not the author of anything, neither to read nor to write.**

**The defect this was written over, measured on 2026-09-23 against ``origin/main``
(``18deebb``).** Two sibling doors, one rule, one guarded:

* ``estimate_professor_pay`` opens with ``me = identity_label.strip()`` and refuses when it is
  empty — "this turn carries no identified professor" — and has since it was written;
* ``estimate_faculty_pay`` never read ``identity_label`` AT ALL. Its only guard was the role,
  so ``estimate_faculty_pay(period="2026-09", identity_label="", role="SUPERVISOR")`` came back
  with EVERY professor's remuneration. On this file's own fixture, three of them.

``_visible`` — the scoping every other door shares — had the same hole, one step wider: with a
blank label the non-oversight branch pins the read to ``""``, which is a substring of every
name, so an EMPLOYEE with no label got the whole master schedule too. Both branches end at the
widest answer the method has, and that is the one an unidentified caller must never get.

**The trap, and why the inverse twin below is not optional.** The owner's decision of
2026-09-23 is textual — «o supervisor pode ter acesso a todos os professores, pois ele é o
coordenador» — and nothing here touches it. The guard fires on the BLANK LABEL alone. A fix
that refused a supervisor who HAS a name would break, silently, a capability that was asked for
on purpose; so ``test_a_named_supervisor_still_reads_every_professor`` and
``test_no_door_refuses_a_caller_it_can_name`` are the half that stops this test passing by
forbidding everything, and they are enumerated from the same scan as the refusals.

**Reachable through the HOST, not through the model.** ``cogno_host``'s RBAC wrapper injects
``role`` when it has one and, when the identity has no name, simply SKIPS the ``identity_label``
injection instead of removing the parameter — so the tool's own ``""`` default stands while the
parameter is pruned from the schema, and not even a well-behaved model could fill it. The
dangerous pair is built by the caller. Latent on the served box (no identity carries a blank
label; ``SUPERVISOR`` 0/7), and one ``POST /identities`` with ``name=""`` away: the column is
``NOT NULL DEFAULT ''`` and the create schema declares ``name: str`` with no ``min_length``.

**The mechanism is the point, not the two assertions.** The doors are ENUMERATED off
``CoordinatorService`` — every public method that takes ``identity_label`` — and each is run
with an empty one. A door that arrives later without the guard is born red, which is the only
form of this rule that survives the next feature; it is
``tests/unit/test_protocol_probe_contract.py``'s convention in ``cogno-anima``, pointed at a
service. ``_EXTRA`` is pinned EXHAUSTIVE in both directions, so a new door needing an argument
this table has no entry for fails as a missing entry rather than being quietly skipped — a scan
that silently drops a door is the same false green as a scan that finds none.

**Measured, and one of the three did not go the way it was predicted to.** Removing the guard
this change adds to ``estimate_faculty_pay`` reds 2 node ids and nothing else; removing the
SHARED one in ``_visible`` reds 9 doors while the faculty door stays green — which is the
demonstration that matters, because it is the scan reaching doors nobody wrote a line for
today. Removing the SISTER's own guard (``estimate_professor_pay``) reds NOTHING, and that is
a finding rather than a gap: its own-pay branch delegates to ``get_professor_schedule``, so
``_visible`` now catches what the door used to catch itself. The two are defence in depth and
the sister's is no longer load-bearing alone — removing BOTH reds it, which is how this file
proves it sees that door and not only the one just written.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorAccessError,
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
)

# Two invented spreadsheet ids and three invented professors — no tenant, no person, no address.
S1, S2 = "A" * 24, "B" * 24
A, B, C = "Professor A", "Professor B", "Professor C"

#: A role in ``_OVERSIGHT_ROLES``. Every assertion below uses it deliberately: the role is the
#: half that was checked, so a scan run under a non-oversight role would be measuring the guard
#: that already worked.
SUPERVISION = "SUPERVISOR"

_RULES = f"""SPREADSHEETS:
Turma T1 = {S1}
Turma T2 = {S2}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:E110"
TAB_PROFESSORS: "Informacoes Adicionais"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
_SHEETS = {
    S1: [["01/09/2026", "Ter", A, "NoSQL and Distributed Databases", ""],
         ["03/09/2026", "Qui", A, "NoSQL and Distributed Databases", ""],
         ["08/09/2026", "Ter", B, "Python Programming for Data Engineers", ""],
         ["10/09/2026", "Qui", B, "Python Programming for Data Engineers", ""],
         ["15/09/2026", "Ter", B, "Python Programming for Data Engineers", ""]],
    S2: [["17/09/2026", "Qui", C, "Microservices Architecture", ""]],
}
#: What ``estimate_faculty_pay`` answers for September — the figures the leak handed out.
SEPTEMBER = {A: (8.0, 960.0), B: (12.0, 1440.0), C: (4.0, 480.0)}


def _svc() -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    for sid, rows in _SHEETS.items():
        store.put(sid, "Secretaria", [_HEADER] + rows)
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 9, 1))


# ── the scan ─────────────────────────────────────────────────────────────────────────────
#: The arguments a door needs BESIDES the two this file is about, so that the identity guard is
#: what the call measures and not a missing-argument refusal one line above it. Dates and names
#: come from the fixture, so the inverse twin reaches the same guard the refusal does.
_EXTRA: "dict[str, dict[str, object]]" = {
    "confirm_swap": dict(professor=A, original_date="01/09", new_date="03/09"),
    "record_class_response": dict(class_date="01/09", answer="ACCEPTED"),
    "preview_schedule_to_calendar": dict(sender=None),
    "send_schedule_to_calendar": dict(sender=None),
}


def _doors() -> "list[str]":
    """Every PUBLIC method of the service that takes ``identity_label``, off the class itself.

    Not a list written here: a door that arrives tomorrow is in this set the moment it declares
    the argument, and it arrives red until it reads it."""
    return sorted(
        name for name, fn in inspect.getmembers(CoordinatorService, inspect.isfunction)
        if not name.startswith("_") and "identity_label" in inspect.signature(fn).parameters
    )


def _call(svc: CoordinatorService, door: str, *, identity_label: str) -> object:
    kwargs = dict(_EXTRA.get(door, {}), identity_label=identity_label, role=SUPERVISION)
    result = getattr(svc, door)(**kwargs)
    return asyncio.run(result) if inspect.iscoroutine(result) else result


def test_the_scan_found_the_doors() -> None:
    """The instrument's own control: a scan that enumerates nothing passes by vacuum.

    The bound is deliberately the WEAK one the mechanism needs (the two pay doors are the pair
    this was written over), not today's count — a number here would fail on the next door for
    existing, which is the opposite of what this file is for. Measured today: 14."""
    doors = _doors()
    assert len(doors) >= 2, f"the scan enumerated {len(doors)} doors — it is measuring nothing"
    assert {"estimate_faculty_pay", "estimate_professor_pay"} <= set(doors)


def test_the_argument_table_names_every_door_that_needs_one() -> None:
    """``_EXTRA`` is exhaustive in BOTH directions, so no door is skipped and none is invented.

    A door with a required argument this table does not carry would raise ``TypeError`` inside
    the scan, and a scan that fails for a boring reason is a scan somebody deletes."""
    doors = set(_doors())
    assert set(_EXTRA) <= doors, f"_EXTRA names doors that do not exist: {set(_EXTRA) - doors}"
    needs = {
        door for door in doors
        if any(p.name not in ("self", "identity_label", "role")
               and p.default is inspect.Parameter.empty
               and p.kind is not inspect.Parameter.VAR_KEYWORD
               for p in inspect.signature(getattr(CoordinatorService, door)).parameters.values())
    }
    assert needs <= set(_EXTRA), f"doors with required arguments and no _EXTRA entry: {needs - set(_EXTRA)}"


# ── the rule ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("door", _doors())
def test_every_door_refuses_a_caller_without_identity(door: str) -> None:
    """``identity_label=""`` under an oversight role: every door refuses, none answers.

    Removing the guard from EITHER pay door turns this red — the scan sees both, which is what
    makes it a rule rather than a test of the line just written."""
    with pytest.raises(CoordinatorAccessError):
        _call(_svc(), door, identity_label="")


def test_the_faculty_pay_leak_is_closed() -> None:
    """The measured defect itself, as one call.

    On ``18deebb`` this returned three professors, 8/12/4 hours and R$ 960/1.440/480 — the whole
    faculty's remuneration to a caller with no name. The role was the only thing it looked at."""
    with pytest.raises(CoordinatorAccessError):
        _svc().estimate_faculty_pay(period="2026-09", identity_label="", role=SUPERVISION)


# ── the half that stops this passing by forbidding everything ────────────────────────────
def test_a_named_supervisor_still_reads_every_professor() -> None:
    """The owner's decision, pinned: «o supervisor pode ter acesso a todos os professores».

    The guard is about the BLANK label and nothing else. If this ever goes red, the fix above
    has broken a capability that was asked for on purpose — and a refusal is not visible from
    the outside as a defect, it reads like a rule."""
    faculty = _svc().estimate_faculty_pay(period="2026-09", identity_label=A, role=SUPERVISION)
    assert {e.professor for e in faculty.estimates} == set(SEPTEMBER)
    assert {e.professor: (e.hours, e.base) for e in faculty.estimates} == SEPTEMBER


@pytest.mark.parametrize("door", _doors())
def test_no_door_refuses_a_caller_it_can_name(door: str) -> None:
    """The inverse twin, enumerated off the SAME scan: a named supervisor is never refused.

    Every other failure is allowed through — a calendar with no sender, a swap with no free
    slot, a date that matches nothing — because those are the doors' own business and this is
    an access test. Only ``CoordinatorAccessError`` fails it, which is exactly the class of
    refusal an over-eager identity guard would produce."""
    try:
        _call(_svc(), door, identity_label=A)
    except CoordinatorAccessError as exc:      # pragma: no cover - the assertion IS the failure
        pytest.fail(f"{door} refused a supervisor it CAN name: {exc}")
    except Exception:
        pass                                   # the door's own business, not an access rule

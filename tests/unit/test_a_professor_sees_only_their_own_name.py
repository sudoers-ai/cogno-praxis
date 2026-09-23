"""A non-oversight caller sees the rows written with THEIR name — not every name that contains it.

The non-oversight branch of ``CoordinatorService._visible`` pinned the read to the identity label
by a folded SUBSTRING (``_norm(label) in _norm(cell)``), and so did ``get_professor_info``. A name
is not a substring of a person: «ana» is inside «mariana». Measured on the base tree, with an
EMPLOYEE labelled «Ana» on a sheet holding one class of hers and three of «Mariana Lopes»:

* ``get_professor_schedule`` → **4 rows** (hers and the other professor's three);
* ``estimate_professor_pay`` (the own-pay door, which reads through the same filter) →
  **16 h · R$ 1.600,00**, where her own is 4 h · R$ 400,00;
* ``get_professor_info`` → both records, and ``professor_email`` → **the other professor's
  address**, which is where a calendar export would have gone;
* the two WRITES behind the same filter — ``record_class_response`` recorded «Recusada» on the
  other professor's class and ``confirm_swap`` moved it onto a free slot.

Every value in this file is the FIXED world; each twin's docstring says what the base answered.
All names and addresses are invented.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
)
from cogno_praxis.coordinator.service import _name_tokens, _own_spellings

SID = "A" * 24
_RULES = f"""SPREADSHEETS:
Turma T1 = {SID}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:F110"
TAB_PROFESSORS: "Info"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
COLUMN_STATUS: "Status"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 100,00
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Status"]
_FACULTY_HEADER = ["Professor", "Disciplina", "E-mail"]


def _svc(professors: list[str], *, faculty: "list[list[str]] | None" = None,
         free: bool = False) -> tuple[CoordinatorService, InMemorySpreadsheetStore]:
    """One class a day in October 2026, one row per name in ``professors`` (in order)."""
    rows = [[f"{i + 1:02d}/10/2026", "", p, f"Disciplina {i}", "", ""]
            for i, p in enumerate(professors)]
    if free:
        rows.append(["20/10/2026", "", "", "Livre", "", ""])
    store = InMemorySpreadsheetStore()
    store.put(SID, "Secretaria", [_HEADER] + rows)
    if faculty is not None:
        store.put(SID, "Info", [_FACULTY_HEADER] + faculty)
    svc = CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 9, 23))
    return svc, store


def _employee(label: str) -> dict[str, str]:
    return {"role": "EMPLOYEE", "identity_label": label}


def _seen(svc: CoordinatorService, label: str) -> list[str]:
    return [e.professor for e in svc.get_professor_schedule(**_employee(label), month="2026-10")]


LEAK = ["Ana", "Mariana Lopes", "Mariana Lopes", "Mariana Lopes"]


# ── the leak, closed on every door that reads through the filter ────────────────────────

def test_ana_does_not_see_marianas_schedule():
    """Base: ``['Ana', 'Mariana Lopes', 'Mariana Lopes', 'Mariana Lopes']``."""
    svc, _ = _svc(LEAK)
    assert _seen(svc, "Ana") == ["Ana"]


def test_anas_own_pay_does_not_sum_marianas_classes():
    """Base: 16 h · R$ 1.600,00 — one class of hers and three of somebody else's."""
    svc, _ = _svc(LEAK)
    est = svc.estimate_professor_pay(**_employee("Ana"), period="2026-10")
    assert est.professor == "Ana"
    assert est.hours == 4
    assert est.base == pytest.approx(400.0)


def test_the_other_professor_still_gets_her_own_pay():
    """Control — the filter narrowed, it did not starve the person whose rows these are."""
    svc, _ = _svc(LEAK)
    est = svc.estimate_professor_pay(**_employee("Mariana Lopes"), period="2026-10")
    assert (est.hours, est.base) == (12, pytest.approx(1200.0))


def test_ana_gets_her_own_faculty_record_and_address():
    """Base: both records, and ``professor_email`` answered ``mariana@example.com``."""
    faculty = [["Mariana Lopes", "Calculo", "mariana@example.com"],
               ["Ana", "Estatistica", "ana@example.com"]]
    svc, _ = _svc(LEAK, faculty=faculty)
    assert [r["professor"] for r in svc.get_professor_info(**_employee("Ana"))] == ["Ana"]
    assert svc.professor_email(**_employee("Ana")) == "ana@example.com"


def test_ana_cannot_decline_or_move_marianas_class():
    """Base: the other professor's 02/10 class was marked «Recusada» and then moved to 20/10."""
    svc, store = _svc(LEAK, free=True)
    before = store.read_range(SID, "Secretaria", "A1:F110")
    with pytest.raises(CoordinatorError, match="No class found"):
        svc.record_class_response(class_date="02/10/2026", answer="DECLINED", **_employee("Ana"))
    with pytest.raises(CoordinatorError, match="No class found"):
        svc.confirm_swap(professor="", original_date="02/10/2026", new_date="20/10/2026",
                         **_employee("Ana"))
    assert store.read_range(SID, "Secretaria", "A1:F110") == before


def test_a_shared_family_name_is_not_the_same_person():
    """«Ana Lopes» is inside «Mariana Lopes» as a string. Base: 2 rows."""
    svc, _ = _svc(["Ana Lopes", "Mariana Lopes"])
    assert _seen(svc, "Ana Lopes") == ["Ana Lopes"]


# ── what must keep working ────────────────────────────────────────────────────────────────

def test_a_short_label_sees_the_sheets_fuller_spelling():
    """«Ana Lopes» ⊂ «Ana Maria Lopes», first and last name agreeing — hers. The base REFUSED
    this one (a two-word name is not a substring of the three-word one): a gain, not a regression."""
    svc, _ = _svc(["Ana Maria Lopes", "Mariana Lopes"])
    assert _seen(svc, "Ana Lopes") == ["Ana Maria Lopes"]


def test_accents_and_case_do_not_decide():
    svc, _ = _svc(["João Silva"])
    assert _seen(svc, "joao SILVA") == ["João Silva"]


def test_a_name_somebody_else_could_claim_is_dropped_but_the_exact_one_is_kept():
    """Labelled «Ana Lopes», on a sheet with «Ana Maria Lopes» AND «Ana Beatriz Lopes», both
    fuller spellings fit and they are two people: neither is shown, the exact spelling is.
    (The base answered the same here — a two-word name is not a substring of either — so this
    twin guards the SECOND condition of ``_own_spellings``, not the substring.)"""
    svc, _ = _svc(["Ana Lopes", "Ana Maria Lopes", "Ana Beatriz Lopes"])
    assert _seen(svc, "Ana Lopes") == ["Ana Lopes"]


def test_a_long_label_does_not_take_a_short_row_another_person_fits():
    svc, _ = _svc(["Ana Lopes", "Ana Beatriz Lopes"])
    assert _seen(svc, "Ana Maria Lopes") == []
    svc, _ = _svc(["Ana Lopes", "Mariana Lopes"])
    assert _seen(svc, "Ana Maria Lopes") == ["Ana Lopes"]


def test_oversight_is_untouched():
    """The by-name reach of an oversight role is a different rule and did not move."""
    svc, _ = _svc(LEAK)
    rows = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Ana",
                                      professor="Mariana", month="2026-10")
    assert [e.professor for e in rows] == ["Mariana Lopes"] * 3


# ── the whole table, pinned: what the rule accepts and what it refuses ─────────────────────
# (label, sheet spelling, other spellings on the sheet, the caller's own?)
_TABLE = [
    # somebody else's — refused
    ("Ana", "Mariana Lopes", ["Ana"], False),
    ("Ana Lopes", "Mariana Lopes", ["Ana Lopes"], False),
    ("Lopes", "Mariana Lopes", ["Ana Lopes"], False),
    ("Maria", "Ana Maria Lopes", ["Maria"], False),
    ("Rui Costa", "Rui Costanza", ["Rui Costa"], False),
    ("Ana", "Ana Silva", ["Ana"], False),
    ("Ana Lopes", "Ana Beatriz Lopes", ["Ana Lopes", "Ana Maria Lopes"], False),
    ("Ana Maria Lopes", "Ana Lopes", ["Ana Maria Lopes", "Ana Beatriz Lopes"], False),
    ("Ana Maria", "Ana Maria Costa", ["Ana Maria"], False),
    # ...and the same two with the caller's own spelling NOT on the sheet (a professor with no
    # class this term): nothing else on the sheet can veto, so the pairwise rule alone decides.
    ("Ana", "Ana Silva", [], False),
    ("Ana Maria", "Ana Maria Costa", [], False),
    # the caller's own — accepted
    ("Ana Lopes", "Ana Lopes", ["Mariana Lopes"], True),
    ("Joao Silva", "João Silva", [], True),
    (" ANA  lopes ", "Ana Lopes", [], True),
    ("Ana Lopes", "Ana Maria Lopes", ["Mariana Lopes"], True),
    ("Ana Maria Lopes", "Ana Lopes", ["Mariana Lopes"], True),
    ("Ana da Silva", "Ana Silva", [], True),
    ("Ana Lopes", "Ana Maria Lopes", ["Ana Lopes"], True),
]
# the caller's own — REFUSED, and counted: each is token for token the shape of a different
# person (the first two mirror the ``Ana Maria``/``Ana Maria Costa`` and ``Ana``/``Ana Silva``
# rows above), or needs a title list / an initial rule this filter deliberately does not have.
_REFUSED_OWN = [
    ("Ana Maria", "Ana Maria Lopes"),
    ("Ana", "Ana Lopes"),
    ("Ana Lopes", "Prof. Ana Lopes"),
    ("Ana M. Lopes", "Ana Maria Lopes"),
]


@pytest.mark.parametrize("label,spelling,others,own", _TABLE)
def test_the_table(label, spelling, others, own):
    assert (_name_tokens(spelling) in _own_spellings(label, [spelling, *others])) is own


@pytest.mark.parametrize("label,spelling", _REFUSED_OWN)
def test_the_refusals_that_cost_a_professor_are_counted(label, spelling):
    assert _own_spellings(label, [spelling]) == set()


def test_the_counts():
    assert (sum(1 for *_, own in _TABLE if not own), sum(1 for *_, own in _TABLE if own),
            len(_REFUSED_OWN)) == (11, 7, 4)

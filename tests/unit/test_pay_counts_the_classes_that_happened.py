"""Pay counts a class the day it was TAUGHT — not the day it was first scheduled, and not at
all when the professor said no.

Two defects, both measured on the owner's own tenant against the served code, both of them a
figure a human was already shown:

1. A class the sheet annotates «- Aula adiada» was PAID, and so was the make-up row that says
   which date it is making up for — the same class bought twice. Turn 105 answered R$ 1.440,00
   where the truth was R$ 960,00.
2. A class the professor DECLINED was paid. ``record_class_response`` writes the tenant's own
   word for "no" into ``COLUMN_STATUS``, the listing has shown it on every line since, and the
   pay never read the column at all.

**The rule is not our inference — it is written in the cells.** The postponed row carries a
date, and the make-up row that follows names THAT date: 14/09 «- Aula adiada» and, on 23/09,
«- reposição do dia 14/09». The pairing is the secretary's, and it is what makes "the postponed
row is not a class given" a reading of the data rather than a policy of ours. The make-up row
is where the class happened, so the make-up row is where it is paid.

The fixtures are SYNTHETIC — invented disciplines and invented people — carrying the tenant's
real FORM: the exception arrives as a suffix on the discipline name, in the spelling and the
casing the sheet actually uses.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
)

S1, S2 = "E" * 24, "F" * 24
P = "Professor Um"

_RULES = f"""SPREADSHEETS:
Turma DSA_33 = {S1}
Turma DE_09 = {S2}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:F110"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
COLUMN_STATUS: "Status"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Status"]

#: One discipline name, so every figure below is a count of classes and nothing else.
SPARK = "Integrated Data Platforms and Processing with Spark"


def _svc(sheets: "dict[str, list[list[str]]]", *, rules: str = _RULES,
         today: date = date(2026, 9, 30)) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    for sid, rows in sheets.items():
        store.put(sid, "Secretaria", [_HEADER] + rows)
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: today)


def _pay(sheets, **kw):
    return _svc(sheets, **kw).estimate_professor_pay(
        period="2026-09", professor=P, identity_label="Coordenação", role="SUPERVISOR")


def _row(day: str, subject: str, status: str = "") -> list[str]:
    return [f"{day}/09/2026", "Seg", P, subject, "", status]


# ── defect 1: the postponed class and its make-up are ONE class ───────────────────────
def test_a_postponed_class_and_its_make_up_are_ONE_class_paid_ONCE():
    """Turn 105's arithmetic, reproduced and corrected: three rows, one of them annotated as
    put off and one of them the make-up that names its date. Three rows paid R$ 1.440,00; two
    classes were taught and the truth is R$ 960,00.

    The twin also pins WHY the postponed row is the one that drops: the make-up row says «do
    dia 14/09», and 14/09 is the date of the row annotated «- Aula adiada». The two rows are a
    pair the secretary wrote down as a pair.

    The figure is the one ``cogno_praxis.coordinator.pay``'s own module docstring has stated
    since the workload defect was closed — *the rule pays 2 × 4 h × R$ 120,00 = R$ 960,00*.
    The documentation was describing the correct behaviour while the code did something else;
    from here it has a test defending it."""
    sheets = {S1: [_row("02", SPARK),
                   _row("14", f"{SPARK} - Aula adiada"),
                   _row("23", f"{SPARK} - reposição do dia 14/09")]}
    est = _pay(sheets)
    assert (est.hours, est.base) == (8, 960.0)            # two classes, not three
    assert est.base == 2 * est.hours_per_class * est.rate == 2 * 4 * 120.0

    # the pairing is in the data: the make-up names the postponed row's own date
    rows = _svc(sheets).aggregate()
    postponed = [e for e in rows if e.is_postponed]
    assert [e.date_str for e in postponed] == ["14/09/2026"]
    assert "14/09" in next(e.subject for e in rows if "reposição" in e.subject)
    # and the make-up row is a PAID class, because it is the day the class happened
    assert not next(e for e in rows if "reposição" in e.subject).is_postponed


def test_the_suffix_is_read_folded_so_casing_and_accents_do_not_decide_anybodys_pay():
    """The sheet writes «Aula adiada» and «Aula Adiada» on two different rows of the same
    September — both are the same annotation, and so is one shouted in capitals or written
    with the accent the tenant's other labels carry. The comparison is the module's own
    ``_norm`` fold, which is why this costs one line and not a table of spellings."""
    for spelling in ("Aula adiada", "Aula Adiada", "AULA ADIADA", "aula adiada", "Adiada"):
        est = _pay({S1: [_row("02", SPARK), _row("14", f"{SPARK} - {spelling}")]})
        assert (est.hours, est.base) == (4, 480.0), spelling
    # the fold is the same one the free-slot labels are read with: an accented «Reposição» and
    # a bare «Reposicao» are one label, and a whole cell holding only it is an OPEN slot
    for spelling in ("Reposição", "REPOSIÇÃO", "reposicao"):
        assert _pay({S1: [_row("02", SPARK), _row("14", spelling)]}).base == 480.0, spelling


def test_a_discipline_whose_NAME_contains_the_word_is_not_an_exception_and_is_paid():
    """The control that kills a substring fix. «Reposição» is a ``FREE_SLOT_LABEL`` and
    «adiada» is a postponed one, and a rule that looked for either ANYWHERE in the cell would
    have stopped paying a class whose subject merely contains the word — and, worse, would
    have read the annotated make-up row as an open slot, taking away the very class the
    postponed row was waiting for. Only the whole cell and its trailing annotation decide."""
    taught = [_row("02", "Reposição de Conteúdo em Bancos de Dados"),
              _row("09", "Aula Adiada e Recuperação — Estudo de Casos"),
              _row("16", "Fundamentos de Reposicao Muscular")]
    assert _pay({S1: taught}).base == 3 * 480.0
    # a dash INSIDE a word is not an annotation separator either
    assert _pay({S1: [_row("02", "Pós-Graduação em Dados")]}).base == 480.0


def test_the_postponed_class_STAYS_ON_THE_LISTING_it_is_only_the_pay_that_drops_it():
    """Not made into a skip row, deliberately. A professor reading their month has to see the
    day that did not happen — the sheet says so on the line, in the tenant's own words — and a
    row that vanishes from a listing is a class somebody turns up for."""
    svc = _svc({S1: [_row("02", SPARK), _row("14", f"{SPARK} - Aula adiada")]})
    listed = svc.get_professor_schedule(professor=P, month="2026-09", include_past=True,
                                        apply_horizon=False, identity_label="Coordenação",
                                        role="SUPERVISOR")
    assert len(listed) == 2
    assert [e.is_postponed for e in listed] == [False, True]
    assert "Aula adiada" in listed[1].subject


def test_MUTATION_comparing_the_whole_cell_again_brings_the_defect_back():
    """The mutation this file exists to kill, run as code: read the annotation the way every
    label comparison used to read it — the whole cell, nothing else — and the postponed class
    is paid again. The anchor is counted first, so the test cannot pass by finding nothing."""
    sheets = {S1: [_row("02", SPARK),
                   _row("14", f"{SPARK} - Aula adiada"),
                   _row("23", f"{SPARK} - reposição do dia 14/09")]}
    assert _pay(sheets).base == 960.0                     # the anchor: two classes

    svc = _svc(sheets)
    original = CoordinatorService._is_postponed
    try:
        CoordinatorService._is_postponed = lambda self, subject: any(  # type: ignore[assignment]
            subject.strip().lower() == lbl.strip().lower() for lbl in self.cfg.postponed_labels)
        est = svc.estimate_professor_pay(period="2026-09", professor=P,
                                         identity_label="Coordenação", role="SUPERVISOR")
        assert est.base == 1440.0                         # the defect, exactly as measured
    finally:
        CoordinatorService._is_postponed = original       # type: ignore[assignment]
    assert _pay(sheets).base == 960.0                     # and the fix is back


# ── defect 2: a class the professor DECLINED is not a class given ─────────────────────
def test_a_class_the_professor_DECLINED_is_not_paid():
    """The status column ``record_class_response`` writes into is now read by the pay. Two
    classes scheduled, one answered «Recusada» — one class taught."""
    est = _pay({S1: [_row("02", SPARK), _row("09", SPARK, "Recusada")]})
    assert (est.hours, est.base) == (4, 480.0)


@pytest.mark.parametrize("status", ["", "   ", "Confirmado", "Confirmada", "Aceita",
                                    "ver com a secretaria", "?"])
def test_ONLY_AN_EXPLICIT_DECLINE_STOPS_THE_MONEY_silence_is_not_a_refusal(status):
    """The control, and the asymmetry is the whole design. An answer is a fact; the ABSENCE of
    one is not the opposite fact. A blank cell, the tenant's routine label, an acceptance, and
    a note a secretary left that this system did not write and will not interpret — all of them
    PAY. Refusing to pay an unanswered class would invent a decline out of a silence and dock a
    professor who taught without replying to an e-mail."""
    assert _pay({S1: [_row("02", SPARK, status)]}).base == 480.0


def test_MUTATION_ignoring_the_status_column_brings_the_defect_back():
    """Ignore the column, as ``_payable`` did, and the declined class is paid again."""
    sheets = {S1: [_row("02", SPARK), _row("09", SPARK, "Recusada")]}
    assert _pay(sheets).base == 480.0                     # the anchor: one class

    svc = _svc(sheets)
    original = CoordinatorService.class_response
    try:
        CoordinatorService.class_response = lambda self, entry: "PENDING"  # type: ignore[assignment]
        est = svc.estimate_professor_pay(period="2026-09", professor=P,
                                         identity_label="Coordenação", role="SUPERVISOR")
        assert est.base == 960.0                          # both classes paid — the defect
    finally:
        CoordinatorService.class_response = original       # type: ignore[assignment]
    assert _pay(sheets).base == 480.0


def test_a_sheet_with_no_STATUS_COLUMN_is_unaffected_and_every_class_is_paid():
    """A schedule whose header carries no status column has nowhere to record an answer, so
    there is no answer to read: :meth:`class_response` says PENDING and the pay is what it
    always was. This is the shape most tenants are in, and the new read must cost them nothing.

    Note the rules text is NOT what decides it — ``COLUMN_STATUS`` defaults to "Status", so
    deleting the line changes no behaviour at all. What decides it is whether the SHEET has
    that header, which is :meth:`status_column_index`'s whole contract: by name, never by
    position."""
    store = InMemorySpreadsheetStore()
    store.put(S1, "Secretaria", [["Data", "Dia", "Professor", "Disciplina", "Sala"],
                                 ["02/09/2026", "Seg", P, SPARK, ""],
                                 ["09/09/2026", "Seg", P, SPARK, ""]])
    svc = CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 9, 30))
    assert svc.status_column_index(svc.aggregate()[0].header) is None
    est = svc.estimate_professor_pay(period="2026-09", professor=P,
                                     identity_label="Coordenação", role="SUPERVISOR")
    assert est.base == 960.0

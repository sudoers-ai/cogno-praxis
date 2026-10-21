"""A skip row is read by its BASE name — «Feriado - <nome do feriado>» is a holiday, not a class.

``CoordinatorService._is_skip`` compared the WHOLE subject cell with ``SKIP_LABELS``. A secretary
writes a holiday the way she writes every other exception: she appends the name to the label —
«Feriado - Independência do Brasil». The whole cell is not a label, so that row read as a class
named «Feriado - Independência do Brasil» and reached every place a class reaches:

* the professor's AGENDA (``get_professor_schedule``), as a class on the holiday;
* the discipline list of the «você quis dizer…?» footer (``ReadReport.known_disciplines``);
* the PAY estimate (``estimate_professor_pay``), as one class of its own (``PayLine.classes=1``);
* the swap refusal, which called the holiday «already has a class scheduled».

The skip now reads the cell's base name with the SAME reader the status notes of the discipline
list use (``service._discipline``, the text before the last spaced dash): the whole cell is a
label, or its base name is. Nothing new decides what a holiday is — the tenant's ``SKIP_LABELS``
still does:

* «Feriado» alone is skipped, as before (the control);
* «Laboratório - Redes» is a discipline with a suffix and stays a class (the case that stays);
* «Redes - Feriado» is a class of Redes annotated with a word, and stays a class: the base name
  decides, never a word anywhere in the cell;
* «Feriado Nacional - Tiradentes» has the base name «Feriado Nacional», which BEGINS with the
  label «Feriado» as a whole word. A tenant that declares only «Feriado» (the real one does) was
  paying that row as a class; it is skipped now, under that list and under the defaults. «Feriado
  Nacional», «Feriado-Ponte» and «Feriado: Tiradentes» begin with the label the same way;
* the word must be WHOLE and FIRST: «Feriados e Festas» (a longer word) and «Fisica» against a label
  «Fis» stay classes, and so does «Gestão de Férias» (the label is there, but not first);
* the widening never takes an OPEN slot: «Reservado para Reposição» with nobody in the professor
  column begins with the default label «Reservado» and carries the free-slot label «Reposição»; it
  stays the free slot the owner's rule made it (``_is_free_by_word``).

Holiday names are public; every other name, id and figure here is invented.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ReadReport,
)

_SID = "1QwErTy-UiOpAsDfGhJkLzXcVbNm45678"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
_COMMON = (f"SPREADSHEETS:\nTurma SMP_33 = {_SID}\n"
           'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
           'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
           'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre, Reposição"\n'
           'PAY_RATE_PER_HOUR: "100"\nHOURS_PER_CLASS: "2"\n')
#: The tenant declares only «Feriado» (the shape of the rules the consultant's probe used).
_RULES_FERIADO = _COMMON + 'SKIP_LABELS: "Feriado"\n'
#: No SKIP_LABELS line: the library's defaults (they include «Feriado Nacional» and «Reservado»).
_RULES_DEFAULT = _COMMON
#: A label that is the first letters of a discipline, «Fisica», with no word boundary after them.
_RULES_FIS = _COMMON + 'SKIP_LABELS: "Fis"\n'

_CLASSES = [["03/09/2026", "Qui", "Ana", "Deep Learning", "101"],
            ["17/09/2026", "Qui", "Ana", "Deep Learning", "101"]]


def _svc(cell: str, *, rules: str = _RULES_FERIADO, professor: str = "Ana") -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [[""] * 5, [""] * 5, [""] * 5, list(_HEADER)]
              + [list(r) for r in _CLASSES] + [["07/09/2026", "Seg", professor, cell, "101"]])
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: date(2026, 9, 1))


def _sites(svc: CoordinatorService, cell: str) -> dict[str, object]:
    """Where the row went, in the three places a class reaches."""
    agenda = [e.subject for e in svc.get_professor_schedule(identity_label="Ana", role="PROFESSOR")]
    report = ReadReport()
    # a discipline nobody teaches, so the read fills the footer's closed list
    svc.get_professor_schedule(identity_label="Ana", role="PROFESSOR", discipline="Química",
                               report=report)
    pay = svc.estimate_professor_pay(identity_label="Ana", role="PROFESSOR", period="09/2026")
    lines = {ln.subject: ln.classes for g in pay.groups for ln in g.lines}
    return {"agenda": cell in agenda, "footer": cell in report.known_disciplines,
            "pay": lines.get(cell, 0), "deep_learning": lines.get("Deep Learning", 0)}


_SKIPPED = {"agenda": False, "footer": False, "pay": 0, "deep_learning": 2}
_A_CLASS = {"agenda": True, "footer": True, "pay": 1, "deep_learning": 2}


@pytest.mark.parametrize("cell", ["Feriado - Independência do Brasil", "Feriado - Tiradentes",
                                  "feriado – Proclamação da República", "FERIADO — Natal"])
def test_a_holiday_written_with_its_name_is_skipped_in_all_three_places(cell):
    """The twin: on the base this row was in the agenda, in the footer and paid as one class."""
    assert _sites(_svc(cell), cell) == _SKIPPED


def test_the_bare_label_is_skipped_as_before():
    """The control: the whole cell is a label, which is what the comparison always read."""
    assert _sites(_svc("Feriado"), "Feriado") == _SKIPPED


@pytest.mark.parametrize("cell", ["Laboratório - Redes", "Redes - Feriado",
                                  "Feriados Escolares", "Feriados e Festas", "Redes"])
def test_a_discipline_whose_base_name_is_not_a_label_stays_a_class(cell):
    """The case that stays, and the adverse probe: a suffix that is not a label's base name, a
    label word AFTER the dash, and a base name that begins with the label's letters inside a
    LONGER word («Feriados») are classes."""
    assert _sites(_svc(cell), cell) == _A_CLASS


@pytest.mark.parametrize("cell", ["Feriado Nacional - Tiradentes", "Feriado Nacional",
                                  "Feriado-Ponte", "Feriado: Tiradentes"])
def test_a_base_name_that_begins_with_the_label_as_a_word_is_skipped(cell):
    """The twin, under the tenant's own list (only «Feriado»): on ``0fee415`` each of these rows
    was in the agenda, in the footer and paid as one class. The label begins the base name and
    is followed by a space, a dash, a colon or the end — a whole word."""
    assert "Feriado Nacional" not in CoordinatorConfig(_RULES_FERIADO).skip_labels
    assert _sites(_svc(cell), cell) == _SKIPPED


def test_feriado_nacional_is_skipped_under_either_label_list():
    """«Feriado Nacional - Tiradentes»: the defaults hold «Feriado Nacional» itself, a tenant that
    declares only «Feriado» holds the word it begins with. Skipped under both; no word is added
    to anybody's labels."""
    cell = "Feriado Nacional - Tiradentes"
    assert "Feriado Nacional" in CoordinatorConfig(_RULES_DEFAULT).skip_labels
    assert _sites(_svc(cell, rules=_RULES_DEFAULT), cell) == _SKIPPED
    assert _sites(_svc(cell, rules=_RULES_FERIADO), cell) == _SKIPPED


@pytest.mark.parametrize(("cell", "rules"), [("Fisica", _RULES_FIS),
                                             ("Gestão de Férias", _RULES_DEFAULT)],
                         ids=["Fisica-vs-label-Fis", "Gestao-de-Ferias-vs-defaults"])
def test_the_label_must_be_a_whole_word_and_first(cell, rules):
    """The controls of the widening: «Fisica» begins with the letters of a label «Fis» but not
    with the WORD; «Gestão de Férias» holds the default label «Férias» as a word but not FIRST.
    Both are classes, as they were."""
    assert _sites(_svc(cell, rules=rules), cell) == _A_CLASS


@pytest.mark.parametrize(("cell", "rules"), [("Reservado para Reposição", _RULES_DEFAULT),
                                             ("Feriado Nacional - Reposição", _RULES_FERIADO)],
                         ids=["Reservado-para-Reposicao-vs-defaults",
                              "Feriado-Nacional-Reposicao-vs-Feriado"])
def test_the_widening_never_takes_an_open_slot(cell, rules):
    """Each cell begins with a skip label as a word («Reservado» is a default, «Feriado» the
    tenant's) and carries the free-slot label «Reposição» with nobody in the professor column:
    the owner's rule reads it as an OPEN slot, and it stays one — listed, free, and offered by
    ``find_replacement_slot``. Without the guard it is skipped and the slot disappears."""
    svc = _svc(cell, rules=rules, professor="")
    row = [e for e in svc.aggregate() if e.subject == cell]
    assert [e.is_free_slot for e in row] == [True]
    slots = svc.find_replacement_slot(identity_label="Sofia", role="SUPERVISOR")
    assert [e.date_str for e in slots] == ["07/09/2026"]


def test_the_skip_row_is_still_read_when_a_caller_asks_for_skip_rows():
    """Skipping is a filter of the ordinary read, not a deletion: ``include_skip=True`` still
    returns the row, under the subject the secretary wrote."""
    cell = "Feriado - Independência do Brasil"
    svc = _svc(cell)
    assert cell not in [e.subject for e in svc.aggregate()]
    assert cell in [e.subject for e in svc.aggregate(include_skip=True)]


def test_a_swap_onto_a_named_holiday_is_refused_as_a_holiday():
    """The fourth reader of the skip: a destination marked «Feriado - Tiradentes» was refused as
    a date that «already has a class scheduled»; it is a holiday, and the refusal says so."""
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [[""] * 5, [""] * 5, [""] * 5, list(_HEADER),
                                   ["16/09/2026", "Qua", "Ana", "Deep Learning", "101"],
                                   ["21/09/2026", "Seg", "", "Feriado - Tiradentes", ""]])
    svc = CoordinatorService(store, CoordinatorConfig(_RULES_FERIADO), today=lambda: date(2026, 9, 1))
    with pytest.raises(CoordinatorError) as exc:
        svc.confirm_swap(professor="Ana", original_date="16/09/2026", new_date="21/09/2026",
                         role="SUPERVISOR", identity_label="Sofia")
    msg = " ".join(str(exc.value).split())
    assert 'is marked "Feriado - Tiradentes"' in msg and "no class can be moved onto it" in msg
    assert "already has a class" not in msg


def test_the_skip_reads_the_one_base_name_reader():
    """ONE definition: the skip's base name is ``_discipline``, the reader the discipline list's
    status notes already use — a second splitter could disagree with it about where a cell splits."""
    import inspect

    from cogno_praxis.coordinator.service import CoordinatorService as _S

    src = inspect.getsource(_S._is_skip)
    assert "_discipline(" in src
    assert "split(" not in src and "_ANNOTATION_SEP" not in src
    # and ONE definition of a whole word: the module's _has_phrase, never a regex of its own
    assert "_has_phrase(" in src
    assert "re.search(" not in src and "re.match(" not in src and "startswith(" not in src

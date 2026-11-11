"""Consultor twin, praxis #203: a grade cell with the FIRST NAME ALONE is not the person the
registry's full name designates — not in the read, and above all not in the swap.

``_professor_designates`` reads ``_is_abbreviation_of`` PAIRWISE, in both directions. Reversed
(cell shorter than the query), a one-word cell «Belmira» is an "abbreviation" of «Belmira
Quostral Vendrim»: same first word, every word of it inside. That one word is somebody else as
easily as her (``_same_professor``: «Ana» is not «Ana Silva», nothing in a pair of strings can
say so). ``confirm_swap`` takes ``src_matches[0]`` with no check of whose class it is, so when
that other Belmira teaches on the same date and her row comes first, the swap MOVES HER CLASS.
On the base the full name matched nothing and the swap refused («No class found») — safe.

GEMEO: the swap named by the full name never moves the first-name-only class; the read does not
list it. Invented names."""
from __future__ import annotations

from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
)

SID = "H" * 24
_RULES = f"""SPREADSHEETS:
Turma DSA_33 = {SID}

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
OVERSIGHT = {"identity_label": "Coordenação", "role": "SUPERVISOR"}
FULL = "Belmira Quostral Vendrim"
GRADE_SHORT = "Belmira Quostral"
FIRST_NAME_ONLY = "Belmira"      # ANOTHER professor, written by her first name alone


def _svc(rows):
    store = InMemorySpreadsheetStore()
    store.put(SID, "Secretaria", [_HEADER] + rows)
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 11, 10))


def _rows():
    return [["13/11/2026", "Sex", FIRST_NAME_ONLY, "Bancos de Dados", "102"],
            ["13/11/2026", "Sex", GRADE_SHORT, "Redes de Computadores", "101"],
            ["16/11/2026", "Seg", "", "Livre", "205"]]


def test_GEMEO_the_swap_by_the_full_name_never_moves_the_first_name_only_class():
    svc = _svc(_rows())
    try:
        src, _dst = svc.confirm_swap(professor=FULL, original_date="13/11", new_date="16/11",
                                     **OVERSIGHT)
    except CoordinatorError:
        return                                   # refusing is safe
    assert src.professor != FIRST_NAME_ONLY, "moved ANOTHER professor's class"


def test_GEMEO_the_read_by_the_full_name_does_not_list_the_first_name_only_class():
    svc = _svc(_rows())
    names = [e.professor for e in svc.get_professor_schedule(professor=FULL, **OVERSIGHT)]
    assert FIRST_NAME_ONLY not in names, names


def test_CONTROLO_the_bare_first_name_query_still_lists_every_belmira():
    """The substring the read always had: a one-word QUERY is the caller's own breadth."""
    svc = _svc(_rows())
    names = sorted(e.professor for e in svc.get_professor_schedule(professor="Belmira",
                                                                   **OVERSIGHT))
    assert names == sorted([FIRST_NAME_ONLY, GRADE_SHORT])

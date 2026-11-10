"""The coordinator resolves a professor named by the CADASTRO's full spelling against a grade
that keeps the class under a SHORTER one — and answers availability (and a swap) by that name.

The oversight read matched a ``professor=<name>`` as a folded SUBSTRING of the schedule cell. A
substring is contiguous and one-directional: a SHORTER query sits inside a fuller cell («Silva»
inside «Ana Silva»), but the registry's FULL name does not sit inside the grade's SHORTER one —
«Belmira Quostral Vendrim» is not inside «Belmira Quostral» — so the coordinator answered "no
class found" about a professor whose class was right there under a name one word shorter.

The fix reads the two as one name written in a different number of words (same first name, every
word of the shorter already in the fuller), in EITHER direction, folded for accent and case. It
is the token rule the rest of the module already names people by — no ``difflib``, no edit
distance, no threshold of resemblance.

Every name here is invented; the FORMS are the measured ones: a cadastro spelling one word
longer than the grade's, a query that drops a middle word, and an accent that the grade carries
and the query does not. The control is the one that keeps the widening honest: a DIFFERENT
person who merely shares a first name is never pulled in.
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

# The grade (schedule) keeps the SHORT spelling; the cadastro carries the FULL one.
GRADE_SHORT = "Belmira Quostral"
CADASTRO_FULL = "Belmira Quostral Vendrim"
# A second professor who merely shares the first name — never summed, never swapped by mistake.
OTHER_BELMIRA = "Belmira Astrade"
# A grade cell carrying accents the folded query will not.
GRADE_ACCENT = "Ismênia Fólbrant"


def _svc(rows: "list[list[str]]", *, today: date = date(2026, 11, 10)) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(SID, "Secretaria", [_HEADER] + rows)
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: today)


def _row(day: str, professor: str, subject: str = "Redes de Computadores") -> list[str]:
    return [f"{day}/11/2026", "Sex", professor, subject, "101"]


def _free(day: str) -> list[str]:
    return [f"{day}/11/2026", "Seg", "", "Livre", "205"]


def _names(svc: CoordinatorService, professor: str) -> list[str]:
    return [e.professor for e in svc.get_professor_schedule(professor=professor, **OVERSIGHT)]


# ── the twin: the full cadastro name finds the short grade class ───────────────────────
def test_the_full_registry_name_finds_the_class_the_grade_keeps_short():
    """FAILS on the substring rule (the full name is not inside the short cell), PASSES on the
    token rule. The one measured downstream: «troca a aula da professora Belmira Quostral
    Vendrim» must find the class the grade holds under «Belmira Quostral»."""
    svc = _svc([_row("13", GRADE_SHORT)])
    assert _names(svc, CADASTRO_FULL) == [GRADE_SHORT]


def test_a_swap_named_by_the_full_registry_name_moves_the_short_class():
    """availability and the WRITE read by the same predicate — the swap, named by the cadastro,
    locates the class the grade keeps short and exchanges it into the free slot."""
    svc = _svc([_row("13", GRADE_SHORT), _free("16")])
    src, dst = svc.confirm_swap(professor=CADASTRO_FULL, original_date="13/11",
                                new_date="16/11", **OVERSIGHT)
    assert src.professor == GRADE_SHORT
    assert (src.date_str, dst.date_str) == ("13/11/2026", "16/11/2026")


def test_a_query_that_drops_a_middle_word_resolves():
    """A partial spelling (first + family, the middle name dropped) reaches the full grade cell
    — the same token rule, the other way round."""
    svc = _svc([_row("13", "Ismênia Fólbrant Lira")])
    assert _names(svc, "Ismenia Lira") == ["Ismênia Fólbrant Lira"]


def test_the_name_resolves_accent_and_case_insensitively():
    """The grade carries accents the typed query does not; folding decides neither."""
    svc = _svc([_row("13", GRADE_ACCENT)])
    assert _names(svc, "ISMENIA FOLBRANT MACHADO") == [GRADE_ACCENT]


# ── the controls: the widening does not become a leak ─────────────────────────────────
def test_a_different_person_sharing_only_the_first_name_is_not_matched():
    """«Belmira Quostral Vendrim» must not pull in «Belmira Astrade» — a word of the query the
    other name does not carry stops it, in the read AND in the swap."""
    svc = _svc([_row("13", GRADE_SHORT), _row("14", OTHER_BELMIRA), _free("16")])
    assert _names(svc, CADASTRO_FULL) == [GRADE_SHORT]
    with pytest.raises(CoordinatorError):
        svc.confirm_swap(professor=CADASTRO_FULL, original_date="14/11",
                         new_date="16/11", **OVERSIGHT)


def test_the_substring_shapes_the_read_always_answered_still_resolve():
    """The rule that was there is kept byte for byte: a bare family name and a bare first name
    still find their rows (the first name, inherently, every professor who carries it)."""
    svc = _svc([_row("13", GRADE_SHORT), _row("14", OTHER_BELMIRA)])
    assert _names(svc, "Quostral") == [GRADE_SHORT]
    assert sorted(_names(svc, "Belmira")) == sorted([GRADE_SHORT, OTHER_BELMIRA])

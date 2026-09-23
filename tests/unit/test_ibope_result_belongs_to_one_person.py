"""The survey result attached to a professor's bonus is THEIRS — not whoever's name theirs is
a prefix of.

``_ibope_result`` matched the caller's name as a folded SUBSTRING of the tab's professor cell,
so «Ana» took «Ana Silva»'s result and «Silva» took every Silva's. The bonus is declared per
hour (R$ 30,00 or R$ 40,00 in the tenant this was written for), so a result landing on the
wrong person is a month's bonus paid on somebody else's survey — and the reverse, two rows
matching where one person was meant, quietly returns "not found" and withholds a bonus that
was really there.

The comparison here is deliberately the STRICT one: this is a pairwise question with nothing
to check the answer against, unlike the faculty grouping, which resolves against the people the
tenant declared and can therefore afford a looser rule with a uniqueness condition.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorAccessError,
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
)

SID = "G" * 24
_RULES = f"""SPREADSHEETS:
Turma DSA_33 = {SID}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:E110"
TAB_IBOPE: "Resultados IBOPE"
COLUMN_IBOPE: "Resultado"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
IBOPE_BONUS: 80-89=30; 90+=40
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]


def _svc(ibope: "list[list[str]]") -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(SID, "Secretaria", [_HEADER,
                                  ["02/09/2026", "Qua", "Ana Silva", "Estatística", ""]])
    store.put(SID, "Resultados IBOPE", ibope)
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 9, 30))


TAB = [["Professor", "Resultado"], ["Ana Silva", "85"], ["Mariana Costa", "92"]]


def test_a_shorter_name_does_NOT_pick_up_a_longer_ones_survey_result():
    """«Ana» is inside «Ana Silva» and inside «Mariana Costa». It is neither of them, and it
    takes neither of their results: the answer is NOT FOUND, which is the honest one — a bonus
    the tenant's data does not hold for this person is a bonus that cannot be stated."""
    svc = _svc(TAB)
    assert svc._ibope_result(identity_label="Ana", report=None) is None
    assert svc._ibope_result(identity_label="Silva", report=None) is None
    assert svc._ibope_result(identity_label="Costa", report=None) is None
    assert svc._ibope_result(identity_label="na Sil", report=None) is None


def test_the_control_each_professor_still_picks_up_their_OWN_result():
    """The half that must not move. A name that IS the row's name reads its result, accents
    and casing folded as everywhere else in the module."""
    svc = _svc(TAB)
    assert svc._ibope_result(identity_label="Ana Silva", report=None) == 85.0
    assert svc._ibope_result(identity_label="ANA SILVA", report=None) == 85.0
    assert svc._ibope_result(identity_label="Mariana Costa", report=None) == 92.0


def test_a_name_written_out_more_fully_is_still_the_same_person():
    """Both first AND last token have to agree, plus containment — so «Ana Silva» reads the row
    spelt «Ana Beatriz Silva», and «Ana Costa» reads neither row of a tab holding «Ana Beatriz
    Silva» and «Mariana Costa»."""
    tab = [["Professor", "Resultado"], ["Ana Beatriz Silva", "85"]]
    assert _svc(tab)._ibope_result(identity_label="Ana Silva", report=None) == 85.0
    assert _svc(tab)._ibope_result(identity_label="Ana Beatriz Silva", report=None) == 85.0
    assert _svc(tab)._ibope_result(identity_label="Beatriz Silva", report=None) is None


def test_two_rows_that_disagree_still_refuse_rather_than_pick():
    """Untouched by this change and re-pinned beside it: the same person on two rows with two
    figures produces NOTHING. Choosing between them is an invented bonus wearing a real
    number, and the professor cannot tell which it was."""
    tab = [["Professor", "Resultado"], ["Ana Silva", "85"], ["Ana Silva", "92"]]
    assert _svc(tab)._ibope_result(identity_label="Ana Silva", report=None) is None


def test_MUTATION_matching_by_substring_again_hands_one_persons_survey_to_another():
    """The defect, run as code, in BOTH the shapes it takes.

    One row in the tab and the substring rule hands «Ana» her colleague's 85 — a bonus of
    R$ 30,00 an hour on somebody else's survey. Add a second row whose name also contains
    "ana" and she gets nothing instead, because both match and the disagreement guard fires.
    Same rule, two different wrong answers, and which one a professor gets depends on how many
    colleagues happen to carry a fragment of their name.

    The anchors are counted first, so neither assertion can pass over an empty tab."""
    from cogno_praxis.coordinator import service as mod

    one = _svc([["Professor", "Resultado"], ["Ana Silva", "85"]])
    two = _svc(TAB)
    assert one._ibope_result(identity_label="Ana Silva", report=None) == 85.0   # the anchors
    assert two._ibope_result(identity_label="Ana Silva", report=None) == 85.0
    assert one._ibope_result(identity_label="Ana", report=None) is None
    assert two._ibope_result(identity_label="Ana", report=None) is None

    original = mod._same_professor
    try:
        mod._same_professor = lambda a, b: bool(a) and " ".join(a) in " ".join(b)  # type: ignore[assignment]
        assert one._ibope_result(identity_label="Ana", report=None) == 85.0   # somebody else's
        assert two._ibope_result(identity_label="Ana", report=None) is None   # or nobody's
    finally:
        mod._same_professor = original                                            # type: ignore[assignment]
    assert one._ibope_result(identity_label="Ana", report=None) is None
    assert two._ibope_result(identity_label="Ana Silva", report=None) == 85.0


def test_the_bonus_that_rides_on_it_moves_with_the_result_not_with_a_prefix():
    """The figure a human is shown, end to end: the professor whose row says 85 gets the
    80–89 band applied; a caller named by a prefix of that name gets neither her result nor
    her classes — the door refuses, saying the name could not be told apart."""
    svc = _svc(TAB)
    mine = svc.estimate_professor_pay(period="2026-09", identity_label="Ana Silva", role="EMPLOYEE")
    assert mine.ibope_found and mine.ibope_pct == 85.0
    assert mine.matched_tier is not None and mine.matched_tier.per_hour == 30.0
    # «Ana» resembles «Ana Silva» without provably being her, so the own-pay door no longer
    # answers at all — not with her classes (the old substring), and not with an empty estimate
    # that reads as "you taught nothing": it says the IDENTIFICATION failed (``_LABEL_UNRESOLVED``,
    # tests/unit/test_a_professor_sees_only_their_own_name.py). The survey result is not hers
    # either way, which is what this file pins.
    assert svc._ibope_result(identity_label="Ana", report=None) is None
    with pytest.raises(CoordinatorAccessError, match="does not match any professor"):
        svc.estimate_professor_pay(period="2026-09", identity_label="Ana", role="EMPLOYEE")

"""Three follow-ups to #142 — the own-name filter, on the three paths it had not reached yet.

* **F1 — a partial answer must say it is partial.** The filter resolved «Ana Lopes» to her own
  row and left out two rows written «Prof. Ana Lopes» (a title: token for token the shape of a
  different person, so they are not hers by this rule). Measured on ``6c07c7a``: the schedule
  listed one class and the own pay said 4 h · R$ 400,00, with NOTHING to say two classes were
  left out — before #142 the same sheet answered 12 h · R$ 1.200,00. The rule was right to
  refuse them; the answer was wrong to read as whole. The read record now carries a bit
  (``ReadReport.unconfirmed_similar``) and the footer says so, naming nobody and counting
  nothing — a count already says how many similar people the sheet holds.
* **F2 — an ambiguous label cannot WRITE.** ``confirm_swap`` and ``record_class_response`` refuse,
  and the sheet is compared byte for byte before and after — the absence of an exception is not
  evidence that nothing was written. Each twin carries its anchor: the same write, by a label
  that DOES resolve, changes the sheet, so "unchanged" is not a sheet nothing could change.
* **F3 — a survey result belongs to one person, and pairwise could not tell.** Measured on
  ``6c07c7a``: labelled «Ana Lopes», an IBOPE tab holding only «Ana Maria Lopes» (92 %) and a
  schedule that also carries «Ana Beatriz Lopes» — the caller's own estimate came back with
  Ana Maria's 92 % and the R$ 40,00/h band. The lookup now runs the same ``_own_spellings`` as
  the rows, with the schedule's names as the universe.

All names invented.
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
from cogno_praxis.coordinator.server import UNCONFIRMED_SIMILAR_LINE, build_server
from cogno_praxis.coordinator.types import ReadReport

SID = "A" * 24
_RULES = f"""SPREADSHEETS:
Turma T1 = {SID}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:F110"
TAB_PROFESSORS: "Info"
TAB_IBOPE: "Resultados IBOPE"
COLUMN_IBOPE: "Resultado"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
COLUMN_STATUS: "Status"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 100,00
IBOPE_BONUS: 80-89=30; 90+=40
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Status"]
TITLED = [("01/10/2026", "Ana Lopes"), ("02/10/2026", "Prof. Ana Lopes"),
          ("05/10/2026", "Prof. Ana Lopes")]


def _svc(rows: "list[tuple[str, str]]", *, ibope: "list[list[str]] | None" = None,
         free: bool = False) -> tuple[CoordinatorService, InMemorySpreadsheetStore]:
    body = [[d, "", p, "Estatistica", "", ""] for d, p in rows]
    if free:
        body.append(["20/10/2026", "", "", "Livre", "", ""])
    store = InMemorySpreadsheetStore()
    store.put(SID, "Secretaria", [_HEADER] + body)
    if ibope is not None:
        store.put(SID, "Resultados IBOPE", ibope)
    return (CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 9, 23)),
            store)


def _note_lines(out: str) -> list[str]:
    """Every line of a tool's OUTPUT that carries the note — asserted on as it leaves for the
    model, never on the constant alone: a count appended where the footer is RENDERED would
    leave the constant clean and still tell the reader how many similar people the sheet holds."""
    return [ln for ln in out.splitlines() if "similar to yours" in ln]


def _tool(svc: CoordinatorService, name: str):
    return build_server(svc)._tool_manager._tools[name].fn


EMP = {"role": "EMPLOYEE"}


def _sheet(store: InMemorySpreadsheetStore) -> list[list[str]]:
    return [list(r) for r in store.read_range(SID, "Secretaria", "A1:F110")]


# ── F1 — the rows left out are SAID to be left out ────────────────────────────────────────

def test_the_schedule_says_similar_rows_were_left_out_and_names_nobody():
    svc, _ = _svc(TITLED)
    out = _tool(svc, "get_professor_schedule")(identity_label="Ana Lopes", month="2026-10", **EMP)
    assert _note_lines(out) == [UNCONFIRMED_SIMILAR_LINE]          # the note, exactly, once
    assert not any(ch.isdigit() for ch in UNCONFIRMED_SIMILAR_LINE)  # and it counts nothing
    assert "01/10" in out and "02/10" not in out and "05/10" not in out    # still only hers
    assert "Prof" not in out.replace(UNCONFIRMED_SIMILAR_LINE, "")          # nobody named


def test_the_own_pay_says_it_too_and_still_counts_only_her_class():
    """Base (6c07c7a): the same 4 h · R$ 400,00 with no note at all."""
    svc, _ = _svc(TITLED)
    est = svc.estimate_professor_pay(identity_label="Ana Lopes", period="2026-10", **EMP)
    assert (est.hours, est.base) == (4, pytest.approx(400.0))
    out = _tool(svc, "estimate_professor_pay")(identity_label="Ana Lopes", period="2026-10", **EMP)
    assert _note_lines(out) == [UNCONFIRMED_SIMILAR_LINE] and "R$ 400,00" in out


def test_no_classes_of_her_own_in_the_period_still_carries_the_note():
    """Her row is in November; October holds only the rows that could not be confirmed. «No
    classes» alone would be the half of the truth that reads as the whole of it."""
    svc, _ = _svc([("03/11/2026", "Ana Lopes"), ("02/10/2026", "Prof. Ana Lopes")])
    out = _tool(svc, "estimate_professor_pay")(identity_label="Ana Lopes", period="2026-10", **EMP)
    assert "No classes found" in out and _note_lines(out) == [UNCONFIRMED_SIMILAR_LINE]


@pytest.mark.parametrize("rows,label", [
    ([("01/10/2026", "Ana Lopes"), ("02/10/2026", "Mariana Lopes")], "Ana Lopes"),
    ([("01/10/2026", "Bruno Reis"), ("02/10/2026", "Ana Lopes")], "Bruno Reis"),
    ([("01/10/2026", "Ana Lopes"), ("02/10/2026", "Ana Maria Lopes")], "Ana Lopes"),
])
def test_no_note_when_nothing_similar_was_left_out(rows, label):
    """Controls: a different person (shared family name), a name nothing resembles, and a
    fuller spelling that IS hers (accepted, so nothing was left out)."""
    svc, _ = _svc(rows)
    report = ReadReport()
    svc.get_professor_schedule(identity_label=label, month="2026-10", report=report, **EMP)
    assert report.unconfirmed_similar is False
    out = _tool(svc, "get_professor_schedule")(identity_label=label, month="2026-10", **EMP)
    assert _note_lines(out) == []


def test_the_faculty_record_says_it_too():
    """The faculty door reads through the same rule: her record, and the note that a record
    written «Prof. Ana Lopes» was left out — with that record's address nowhere in the output."""
    svc, store = _svc([("01/10/2026", "Ana Lopes")])
    store.put(SID, "Info", [["Professor", "E-mail"], ["Ana Lopes", "al@example.com"],
                            ["Prof. Ana Lopes", "titled@example.com"]])
    out = _tool(svc, "get_professor_info")(identity_label="Ana Lopes", **EMP)
    assert "al@example.com" in out and "titled@example.com" not in out
    assert _note_lines(out) == [UNCONFIRMED_SIMILAR_LINE]
    # control: the same door with nothing similar left out carries no note
    store.put(SID, "Info", [["Professor", "E-mail"], ["Ana Lopes", "al@example.com"]])
    assert _note_lines(_tool(svc, "get_professor_info")(identity_label="Ana Lopes", **EMP)) == []


# ── F2 — an ambiguous label refuses a WRITE, and the sheet is intact ────────────────────────

AMBIGUOUS = [("01/10/2026", "Ana Lopes"), ("02/10/2026", "Ana Maria Lopes")]


def test_an_ambiguous_label_cannot_answer_an_invitation():
    svc, store = _svc(AMBIGUOUS)
    before = _sheet(store)
    with pytest.raises(CoordinatorAccessError, match="does not match any professor"):
        svc.record_class_response(class_date="01/10/2026", answer="DECLINED",
                                  identity_label="Ana", **EMP)
    assert _sheet(store) == before
    # the anchor: the same write by a label that resolves DOES change this sheet
    svc.record_class_response(class_date="01/10/2026", answer="DECLINED",
                              identity_label="Ana Lopes", **EMP)
    assert _sheet(store) != before


def test_an_ambiguous_label_cannot_move_a_class():
    svc, store = _svc(AMBIGUOUS, free=True)
    before = _sheet(store)
    with pytest.raises(CoordinatorAccessError, match="does not match any professor"):
        svc.confirm_swap(professor="", original_date="01/10/2026", new_date="20/10/2026",
                         identity_label="Ana", **EMP)
    assert _sheet(store) == before
    svc.confirm_swap(professor="", original_date="01/10/2026", new_date="20/10/2026",
                     identity_label="Ana Lopes", **EMP)
    assert _sheet(store) != before


# ── F3 — the survey result is the caller's only if nobody else on the sheet could claim it ──

SURVEY = [["Professor", "Resultado"], ["Ana Maria Lopes", "92"]]


def test_a_survey_result_another_name_could_claim_is_not_handed_to_the_caller():
    """Base (6c07c7a): ``ibope_found=True``, 92 %, the R$ 40,00/h band — Ana Maria's."""
    svc, _ = _svc([("01/10/2026", "Ana Lopes"), ("02/10/2026", "Ana Beatriz Lopes")],
                  ibope=SURVEY)
    est = svc.estimate_professor_pay(identity_label="Ana Lopes", period="2026-10", **EMP)
    assert est.ibope_found is False and est.ibope_pct is None


def test_the_fuller_spelling_nobody_else_fits_is_still_hers():
    """Control: without «Ana Beatriz Lopes» on the schedule, «Ana Maria Lopes» is the fuller
    spelling of «Ana Lopes» and nothing contests it — the guard acts on a third name only."""
    svc, _ = _svc([("01/10/2026", "Ana Lopes")], ibope=SURVEY)
    est = svc.estimate_professor_pay(identity_label="Ana Lopes", period="2026-10", **EMP)
    assert est.ibope_found is True and est.ibope_pct == 92.0


def test_the_exact_spelling_always_finds_its_own_result():
    svc, _ = _svc([("01/10/2026", "Ana Maria Lopes"), ("02/10/2026", "Ana Beatriz Lopes")],
                  ibope=SURVEY)
    est = svc.estimate_professor_pay(identity_label="Ana Maria Lopes", period="2026-10", **EMP)
    assert est.ibope_pct == 92.0

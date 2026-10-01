"""A free slot written as a SENTENCE that carries the label is still a free slot.

The incident (an owner's coordinator persona): the contact asked to move a class and which days
were open, and ``find_replacement_slot`` answered «No open slots in the next 21 days». The
professor's sheet HAD them — written «Espaço Reservado para Reposição (se necessário)» — and
``_is_free`` compared the WHOLE cell against ``FREE_SLOT_LABELS``, so the cell never matched.

The owner's rule (nothing added to the tenant's configuration): a cell is free when (a) it carries
a label as a WHOLE word, folded, and (b) the row is not a class — nobody in the professor column,
no discipline the read knows, no configured class group. The controls are the turn-105 guard of
the pay estimate: the make-up of a class («<discipline> - Reposição») is a class and is paid, a
class annotated as put off stays postponed, a discipline whose name contains «reposição» is a
class.

Every name below is invented; the cell shapes are the tenant's.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ReadReport,
)
from cogno_praxis.coordinator.server import build_server

_SID = "Q" * 24
_RULES = f"""SPREADSHEETS:
Turma XYZ_01 = {_SID}
TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:F110"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
FIXED_COLUMNS: "Data, Dia"
FREE_SLOT_LABELS: "Livre, Reposição"
SKIP_LABELS: "Feriado"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 100,00
"""
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Status"]
PROF = "Professora Inventada Exemplo"
WHO = {"identity_label": "Coordenação Fictícia", "role": "SUPERVISOR"}
TODAY = date(2026, 10, 14)
DISC = "Redes Fictícias"           # a discipline the read knows (it has a class with a professor)

#: The tenant's cell, as written on the professor's sheet.
RESERVED = "Espaço Reservado para Reposição (se necessário)"


def _svc(rows: "list[list[str]]") -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [_HEADER] + rows)
    return CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: TODAY)


def _row(day: str, subject: str, prof: str = PROF) -> "list[str]":
    return [f"{day}/10/2026", "Qua", prof, subject, "101", ""]


def _free(subject: str, *, prof: str = "") -> bool:
    """Is ``subject`` free on a row with ``prof``, in a read that also holds a real class of
    ``DISC`` (so ``DISC`` is a known discipline)?"""
    rows = _svc([_row("20", DISC), _row("21", subject, prof=prof)]).aggregate()
    return next(e for e in rows if e.date_str == "21/10/2026").is_free_slot


# ── the twin ──────────────────────────────────────────────────────────────────────────
def test_TWIN_the_reserved_cell_is_an_open_slot_and_is_returned():
    """Broken world: ``[]`` — the measured «No open slots». Fixed: the slot on 23/10."""
    svc = _svc([_row("21", DISC), _row("23", RESERVED, prof="")])
    report = ReadReport()
    slots = svc.find_replacement_slot(report=report, **WHO)
    assert [e.date_str for e in slots] == ["23/10/2026"]
    assert slots[0].is_free_slot and slots[0].is_free_by_word
    assert report.free_by_word == 1


def test_TWIN_through_the_tool_the_slot_is_listed_and_the_count_is_in_the_output():
    """The output is what the trace records: the slot, and the line counting it."""
    svc = _svc([_row("21", DISC), _row("23", RESERVED, prof=""), _row("28", "Livre", prof="")])
    mcp = build_server(svc)

    async def run() -> str:
        res = await mcp.call_tool("find_replacement_slot", dict(WHO))
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")

    out = asyncio.run(run())
    assert "No open slots" not in out
    assert "23/10" in out and "28/10" in out
    # ONE by word — the bare «Livre» is a label on its own and is not counted
    assert "(1 of the open slots above are written on the sheet as a sentence" in out


@pytest.mark.parametrize("cell", [
    RESERVED,
    "ESPACO RESERVADO PARA REPOSICAO (SE NECESSARIO)",   # the module's fold: case + accents
    "Horário livre para remarcação",
    "Reposição, caso necessário",
])
def test_a_label_word_on_a_row_that_is_not_a_class_is_free(cell):
    assert _free(cell), cell


# ── the controls: what must STAY a class ──────────────────────────────────────────────
def test_CONTROL_the_make_up_of_a_class_is_a_class_with_a_professor():
    """«<discipline> - Reposição» with its professor: the turn-105 make-up row, paid."""
    assert not _free(f"{DISC} - Reposição", prof=PROF)


def test_CONTROL_a_professor_in_the_row_makes_it_a_class_on_its_own():
    """The professor half of (b), on its own. A row with a professor normally also makes its
    own name a known discipline, so the two halves overlap — except when that name is itself a
    label («Reposição - …»), which ``_known_class_names`` leaves out. Then only the professor
    column says this is somebody's class."""
    assert not _free("Reposição - Conteúdo Extra Fictício", prof=PROF)
    assert _free("Reposição - Conteúdo Extra Fictício")          # the same cell, nobody's


def test_CONTROL_the_make_up_of_a_known_discipline_is_a_class_even_without_a_professor():
    """The discipline half of (b), on its own: nobody in the professor column, but the cell
    names a discipline the read knows."""
    assert not _free(f"{DISC} - Reposição")


def test_CONTROL_a_class_group_in_the_cell_makes_it_a_class():
    assert not _free("Reposição XYZ_01")


@pytest.mark.parametrize("cell", [
    "Livreto de Exercícios Fictícios",       # «livre» inside a longer word is not the label
    "Reposicionamento Fictício de Carga",    # nor is «reposi…» — the fold of «Reposição» is «reposicao»
])
def test_CONTROL_a_label_INSIDE_a_longer_word_is_not_the_label(cell):
    assert not _free(cell), cell


def test_CONTROL_a_discipline_whose_NAME_contains_the_word_is_a_class():
    """Known because it has classes with a professor; its professor-less row is still a class."""
    name = "Reposição de Conteúdo Fictício"
    rows = _svc([_row("20", name), _row("21", name, prof="")]).aggregate()
    assert [e.is_free_slot for e in rows] == [False, False]


def test_CONTROL_the_postponed_class_its_make_up_and_the_reserved_slot_beside_them():
    """The turn-105 shape, unmoved: postponed + its make-up are ONE class paid once, and the
    reserved slot beside them is not paid at all."""
    svc = _svc([_row("01", f"{DISC} - Aula adiada"), _row("08", f"{DISC} - Reposição"),
                _row("15", RESERVED, prof="")])
    rows = svc.aggregate()
    assert [(e.is_postponed, e.is_free_slot) for e in rows] == [
        (True, False), (False, False), (False, True)]
    est = svc.estimate_professor_pay(period="2026-10", professor=PROF, **WHO)
    assert (est.hours, est.base) == (4, 400.0)


def test_a_whole_cell_label_is_free_with_a_professor_as_it_always_was():
    assert _free("Reposição", prof=PROF) and _free("LIVRE", prof=PROF)


def test_the_swap_can_move_a_class_INTO_the_reserved_slot():
    """``confirm_swap`` reads the same entries, so the slot the read offers is one the write
    accepts — otherwise the read would propose a date the swap then refuses."""
    svc = _svc([_row("21", DISC), _row("23", RESERVED, prof="")])
    src, dst = svc.confirm_swap(professor=PROF, original_date="21/10/2026",
                                new_date="23/10/2026", **WHO)
    assert dst.subject == RESERVED and src.subject == DISC


def test_no_line_when_nothing_was_read_by_word():
    svc = _svc([_row("23", "Livre", prof="")])
    report = ReadReport()
    assert len(svc.find_replacement_slot(report=report, **WHO)) == 1
    assert report.free_by_word == 0

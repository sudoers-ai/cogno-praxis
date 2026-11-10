"""Consultor twin, praxis #204: a class the schedule annotates as PUT OFF («- Aula adiada») is not
the discipline's last class — it is not going to happen on that date.

The listing's last-class mark groups annotated variants with their discipline (``by_discipline``),
and a postponed row is still a DATED row of that discipline: when it is the latest one, the line
the professor reads says «28/11 · Topologia Algébrica - Aula adiada · última aula da disciplina»
about a class that will not be given. GEMEO: the postponed row carries no mark, and the latest
class that IS held carries it. Invented names."""
from __future__ import annotations

from datetime import date

from cogno_praxis.coordinator import CoordinatorConfig, CoordinatorService, InMemorySpreadsheetStore

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
_PROF = "Belmira Quostral"


def test_GEMEO_a_postponed_class_is_not_the_disciplines_last():
    store = InMemorySpreadsheetStore()
    store.put(SID, "Secretaria", [_HEADER,
                                  ["14/11/2026", "Sáb", _PROF, "Topologia Algébrica", "101"],
                                  ["28/11/2026", "Sáb", _PROF, "Topologia Algébrica - Aula adiada",
                                   "101"]])
    svc = CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 11, 10))
    rows = {e.date_str: e for e in svc.get_professor_schedule(
        professor=_PROF, identity_label="Coordenação", role="SUPERVISOR")}
    assert rows["28/11/2026"].is_postponed and not rows["28/11/2026"].is_last_class
    assert rows["14/11/2026"].is_last_class

"""A title is a title in every reader of a person's name.

The coordinator's schedule query and the scheduler's host matcher each kept a list of titles,
and the lists differed: «Senhor <name>» found the person in neither or one, «Professor <name>»
found the schedule but not the agenda. They now share ``cogno_praxis.honorifics``; the same
title written before the same name resolves the same person everywhere.

Names invented.
"""
from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ReadReport,
)
from cogno_praxis.scheduler.service import SchedulerService
from cogno_praxis.scheduler.store import Host

_NAME = "Belmira Quostral Vendrim"
_SID = "D" * 24
_RULES = (f"SPREADSHEETS:\nTurma DE_01 = {_SID}\n\nTAB_SCHEDULE: \"Secretaria\"\n"
          'RANGE_SCHEDULE: "A1:F110"\nCOLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\n'
          'COLUMN_SUBJECT: "Disciplina"\nCOLUMN_TIME: "Hora"\nHOURS_PER_CLASS: 4\n'
          "PAY_RATE_PER_HOUR: 120,00\n")
_SHEET = [
    ["Data", "Dia", "Professor", "Disciplina", "Sala", "Hora"],
    ["03/11/2026", "Ter", _NAME, "Banco de Dados", "Azul", "19:00"],
    ["05/11/2026", "Qui", "Teodomiro Alvanel Prast", "Redes", "Verde", "19:00"],
]
#: Titles the old lists did not agree on, plus ones every list already knew (the controls).
_TITLES = ["Professor", "Professora", "Prof.", "Dr.", "Dra.", "Doutor", "Doutora",
           "Senhor", "Senhora", "Sr.", "Sra."]


def _schedule_read(professor: str) -> list[str]:
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [list(r) for r in _SHEET])
    svc = CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 10, 22))
    rows = svc.get_professor_schedule(professor=professor, role="SUPERVISOR",
                                      identity_label="Coordenação", month="novembro",
                                      report=ReadReport())
    return [e.date_str for e in rows]


def _agenda_candidates(text: str) -> list[str]:
    svc = SchedulerService.__new__(SchedulerService)

    class _Store:
        def list_hosts(self):
            return [Host(host_id="h1", name=f"Dra. {_NAME}"),
                    Host(host_id="h2", name="Teodomiro Alvanel Prast")]

    svc.store = _Store()
    return [h.host_id for h in svc._host_candidates(text)]


@pytest.mark.parametrize("title", _TITLES)
def test_the_schedule_query_reads_the_person_behind_any_title(title):
    assert _schedule_read(f"{title} {_NAME}") == _schedule_read(_NAME) == ["03/11/2026"]


@pytest.mark.parametrize("title", _TITLES)
def test_the_agenda_matcher_finds_the_same_person_behind_any_title(title):
    assert _agenda_candidates(f"{title} {_NAME}") == _agenda_candidates(_NAME) == ["h1"]


def test_a_name_that_merely_contains_a_title_is_not_stripped():
    # Control: a title is a WHOLE word. «Pedro» holds «dr» and «Donato» holds «don».
    assert _agenda_candidates("Pedro Donato") == []


def test_no_reader_keeps_a_list_of_its_own():
    from cogno_praxis.coordinator import service as coordinator
    from cogno_praxis.scheduler import service as scheduler
    assert not hasattr(coordinator, "_HONORIFICS")
    assert not hasattr(scheduler, "_HONORIFICS")

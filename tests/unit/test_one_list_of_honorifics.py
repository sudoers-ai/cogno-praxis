"""One table of honorifics; each reader strips exactly the subset it stripped before.

The coordinator's schedule query, the scheduler's host matcher and the host's routing kept a list
each. They now read ONE table (``cogno_praxis.honorifics``), each its own labelled subset, so every
reader behaves byte for byte as it did: consolidating is not widening. A word joins a reader's
subset only in a change of its own, with the real form that asks for it and a collision twin
(«seu» is also the Portuguese possessive).

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
#: Each reader's own titles, as it stripped them before the table (the controls of «byte-equal»).
_QUERY_TITLES = ["Professor", "Professora", "Prof.", "Profa.", "Dr.", "Dra.", "Doutor", "Doutora",
                 "Mestre", "Sr.", "Sra."]
_HOST_TITLES = ["Prof.", "Profa.", "Dr.", "Dra.", "Sr.", "Sra."]


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


@pytest.mark.parametrize("title", _QUERY_TITLES)
def test_the_schedule_query_reads_the_person_behind_its_titles(title):
    assert _schedule_read(f"{title} {_NAME}") == _schedule_read(_NAME) == ["03/11/2026"]


@pytest.mark.parametrize("title", _HOST_TITLES)
def test_the_agenda_matcher_finds_the_person_behind_its_titles(title):
    assert _agenda_candidates(f"{title} {_NAME}") == _agenda_candidates(_NAME) == ["h1"]


def test_a_name_that_merely_contains_a_title_is_not_stripped():
    # Control: a title is a WHOLE word. «Pedro» holds «dr» and «Donato» holds «don».
    assert _agenda_candidates("Pedro Donato") == []


def test_no_reader_keeps_a_list_of_its_own():
    from cogno_praxis.coordinator import service as coordinator
    from cogno_praxis.scheduler import service as scheduler
    assert not hasattr(coordinator, "_HONORIFICS")
    assert not hasattr(scheduler, "_HONORIFICS")


def test_each_reader_keeps_exactly_the_subset_it_had():
    from cogno_praxis import honorifics as h
    assert h.QUERY_NAME_TITLES == frozenset({
        "prof", "profa", "professor", "professora", "dr", "dra", "doutor", "doutora", "mestre",
        "sr", "sra"})
    assert h.HOST_NAME_TITLES == frozenset({"dr", "dra", "sr", "sra", "prof", "profa"})
    assert h.HONORIFICS == h.QUERY_NAME_TITLES | h.HOST_NAME_TITLES | h.ROUTING_ADDRESS


@pytest.mark.parametrize("word", ["seu", "dona", "don", "miss", "sir", "senhor", "senhora"])
def test_a_form_of_address_is_not_stripped_from_a_name(word):
    # Collision control: «seu» is the Portuguese possessive; «Don» can be a given name.
    from cogno_praxis.honorifics import is_host_name_title, is_query_name_title
    assert not is_query_name_title(word) and not is_host_name_title(word)

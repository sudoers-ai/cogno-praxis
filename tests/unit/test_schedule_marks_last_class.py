"""The discipline's LAST class is marked, over the WHOLE sheet.

A professor asking «quais aulas em novembro são a última aula da disciplina?» needs each line to
say when it is the last class of its discipline. The window must NOT decide it: a discipline
continuing into December is not "last" on its November lines just because December is out of the
asked month. The mark groups «per (turma+disciplina)» (an «- Aula adiada»/«- reposição» annotation
does not split a discipline) and a free slot is never a discipline's last class.

Invented names/sheet keys throughout — nobody's real schedule.
"""

from __future__ import annotations

import asyncio
from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
)

_SID = "1QxZ7bVendrim-UiOpAsDfGhJkLzXcVbNm01"
_RULES = (f"SPREADSHEETS:\nTurma QZX_77 = {_SID}\n"
          'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:F200"\n'
          'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
          'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Espaço Reservado para Reposição"\n'
          'SKIP_LABELS: "Feriado"\n')
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Status"]
_PROF = "Belmira Quostral Vendrim"
_TODAY = date(2026, 11, 1)
_MARK = " · última aula da disciplina"


def _svc(rows, *, today=_TODAY):
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    pad = [[""] * 5, [""] * 5, [""] * 5, list(_HEADER)]
    store.put(_SID, "Secretaria", pad + [list(r) for r in rows])
    return CoordinatorService(store, cfg, today=lambda: today, horizon_days=None)


def _listing(svc, **args) -> str:
    from cogno_praxis.coordinator.server import build_server
    mcp = build_server(svc)

    async def run():
        res = await mcp.call_tool(
            "get_professor_schedule",
            {"role": "SUPERVISOR", "identity_label": "Quéfren Zalábria",
             "mark_last_class": True, **args})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")

    return asyncio.run(run())


_CONTINUES = [
    ["05/11/2026", "Qui", _PROF, "Topologia Algébrica", "Confirmado"],
    ["12/11/2026", "Qui", _PROF, "Topologia Algébrica", "Confirmado"],
    ["03/12/2026", "Qua", _PROF, "Topologia Algébrica", "Confirmado"],   # continues into December
    ["10/11/2026", "Ter", _PROF, "Geometria Diferencial", "Confirmado"], # ends in November
]


def test_a_november_line_of_a_discipline_that_runs_into_december_is_not_marked_last():
    out = _listing(_svc(_CONTINUES), month="2026-11")
    lines = {ln.split(" · ")[0].split(" ", 1)[1]: ln for ln in out.splitlines()
             if ln.startswith("- ")}
    # Topologia continues to 03/12, so NEITHER November line is its last class
    assert not lines["05/11"].endswith(_MARK)
    assert not lines["12/11"].endswith(_MARK)
    # Geometria has no December class, so its single November class IS the last
    assert lines["10/11"].endswith(_MARK)


def test_the_december_class_is_the_last_of_its_discipline():
    out = _listing(_svc(_CONTINUES), month="2026-12")
    line = next(ln for ln in out.splitlines() if ln.startswith("- "))
    assert line == "- 03/12 · Turma QZX_77 · Topologia Algébrica" + _MARK


def test_an_annotation_does_not_split_a_discipline_into_two_each_marked_last():
    # «- Aula adiada» and «- reposição» are the SAME discipline: only the latest real date is last.
    rows = [
        ["14/11/2026", "Sáb", _PROF, "Topologia Algébrica - Aula adiada", "Confirmado"],
        ["21/11/2026", "Sáb", _PROF, "Topologia Algébrica - reposição do dia 14/11", "Confirmado"],
        ["28/11/2026", "Sáb", _PROF, "Topologia Algébrica", "Confirmado"],
    ]
    out = _listing(_svc(rows), month="2026-11")
    marked = [ln for ln in out.splitlines() if ln.endswith(_MARK)]
    assert len(marked) == 1 and marked[0].startswith("- 28/11")


def test_a_free_slot_is_never_a_disciplines_last_class():
    rows = [
        ["07/11/2026", "Sáb", _PROF, "Topologia Algébrica", "Confirmado"],
        ["28/11/2026", "Sáb", "", "Espaço Reservado para Reposição", ""],   # free slot, latest date
    ]
    out = _listing(_svc(rows), month="2026-11")
    topo = next(ln for ln in out.splitlines() if "Topologia" in ln)
    assert topo.endswith(_MARK)                      # the real class is the last, not the free slot
    assert not any("Reservado" in ln and ln.endswith(_MARK) for ln in out.splitlines())

"""A blank schedule row is nothing to list.

An aggregated sheet keeps rows with NO date AND NO content, and the undated branch of the listing
rendered each as its bare class-group label (``- Turma: <sheet_key>``) — an unfiltered read
answered with a wall of those and buried the real classes. A row with NO date but WITH content (an
undated note) is still worth showing and stays. The test is CONTENT, never the date alone.

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
            {"role": "SUPERVISOR", "identity_label": "Quéfren Zalábria", **args})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")

    return asyncio.run(run())


_EMPTY_ROWS = (
    [["05/11/2026", "Qui", _PROF, "Topologia Algébrica", "Confirmado"]]
    + [["", "", "", "", ""] for _ in range(7)]                       # NO date, NO content
    + [["", "", _PROF, "Reunião pedagógica", ""]])                   # NO date, WITH content


def test_blank_undated_rows_are_dropped_and_an_undated_note_survives():
    # The measured shape is an UNFILTERED read (no month): the month filter drops undated rows on
    # its own, so the blank-row defect only reaches the listing when nothing filters by date.
    out = _listing(_svc(_EMPTY_ROWS))
    # the seven blank rows rendered as this bare label on the base — none now
    assert "- Turma: Turma QZX_77\n" not in out and not out.endswith("- Turma: Turma QZX_77")
    assert "Reunião pedagógica" in out                               # the undated note stays
    assert "Topologia Algébrica" in out
    # exactly two listed lines: the dated class (within the 30-day window) and the undated note
    assert len([ln for ln in out.splitlines() if ln.startswith("- ")]) == 2

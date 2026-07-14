"""Coordinator FastMCP server — the 6 tools over a service, incl. RBAC + swap + durability."""

from __future__ import annotations

import asyncio
from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    build_server,
    is_perishable_edge,
)
from cogno_praxis.coordinator.server import build_server as _bs

_RULES = (
    "SPREADSHEETS:\nDSA=1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
    'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n'
)
_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]


def _server(rows, today=date(2026, 7, 13)):
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [[""] * 5] * 3 + [_HEADER] + rows)
    svc = CoordinatorService(store, cfg, today=lambda: today)
    return _bs(svc), store


def _text(res):
    return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")


def test_get_professor_schedule_tool_reads_real_data():
    mcp, _ = _server([["20/07/2026", "Seg", "Ana", "Redes", "101"]])

    async def run():
        out = _text(await mcp.call_tool("get_professor_schedule",
                                        {"role": "SUPERVISOR", "identity_label": "Sofia"}))
        assert "Redes" in out and "20/07/2026" in out
    asyncio.run(run())


def test_professor_role_cannot_see_others_via_tool():
    mcp, _ = _server([
        ["20/07/2026", "Seg", "Ana", "Redes", "101"],
        ["20/07/2026", "Ter", "Bruno", "Cálculo", "102"],
    ])

    async def run():
        out = _text(await mcp.call_tool("get_professor_schedule",
                                        {"professor": "Bruno", "role": "EMPLOYEE",
                                         "identity_label": "Ana"}))
        assert out.startswith("ERROR")           # refused — a professor can't query another
    asyncio.run(run())


def test_confirm_swap_tool_moves_class():
    mcp, store = _server([
        ["16/07/2026", "Ter", "Ana", "Redes", "101"],
        ["18/07/2026", "Qui", "", "Livre", "205"],
    ])

    async def run():
        out = _text(await mcp.call_tool("confirm_swap",
                                        {"professor": "Ana", "original_date": "16/07/2026",
                                         "new_date": "18/07/2026", "role": "SUPERVISOR",
                                         "identity_label": "Sofia"}))
        assert "Swapped" in out and "Redes" in out
        grid = store._sheets[(_SID, "Secretaria")]
        assert grid[5][2:5] == ["Ana", "Redes", "101"]   # class moved into the free slot's row
    asyncio.run(run())


def test_durability_flags_schedule_relations_only():
    assert is_perishable_edge("Ana", "16/07", "HAS_CLASS_ON")
    assert is_perishable_edge("Ana", "205", "SWAP")
    assert is_perishable_edge("Redes", "hoje", "DEADLINE")
    # durable academic relations pass
    assert not is_perishable_edge("Ana", "Redes", "TEACHES")
    assert not is_perishable_edge("Redes", "DSA", "BELONGS_TO")


def test_build_server_alias_exported():
    assert build_server is _bs

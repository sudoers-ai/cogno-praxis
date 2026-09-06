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
    """The refusal reaches the model as a LIMIT, not as a breakdown.

    The rule itself never changed and is not weakened here: a professor asking about a colleague
    is still refused. What changed is the WORD. The refusal used to arrive as
    ``ERROR: You can only view your own schedule.`` — and a model handed "ERROR" reports a
    malfunction, which is how "I could not access the schedule" was said to someone whose only
    problem was that they had asked about somebody else."""
    mcp, _ = _server([
        ["20/07/2026", "Seg", "Ana", "Redes", "101"],
        ["20/07/2026", "Ter", "Bruno", "Cálculo", "102"],
    ])

    async def run():
        out = _text(await mcp.call_tool("get_professor_schedule",
                                        {"professor": "Bruno", "role": "EMPLOYEE",
                                         "identity_label": "Ana"}))
        assert out.startswith("NOT PERMITTED")   # refused — a professor can't query another
        assert "not a failure" in out            # ... and told apart from one
        assert "ERROR" not in out
        assert "Cálculo" not in out              # the refusal leaks nothing
    asyncio.run(run())


def test_oversight_asking_for_another_professor_still_sees():
    """The other half of the twin. Narrowing the refusal's WORDING must not narrow the ACCESS:
    a supervisor/coordinator naming a colleague is the case the rule exists to allow."""
    mcp, _ = _server([
        ["20/07/2026", "Seg", "Ana", "Redes", "101"],
        ["20/07/2026", "Ter", "Bruno", "Cálculo", "102"],
    ])

    async def run():
        out = _text(await mcp.call_tool("get_professor_schedule",
                                        {"professor": "Bruno", "role": "SUPERVISOR",
                                         "identity_label": "Sofia"}))
        assert "Cálculo" in out and "Redes" not in out
        assert "NOT PERMITTED" not in out
    asyncio.run(run())


def test_a_real_domain_failure_is_still_called_an_error():
    """A refusal is a limit; a swap that cannot find the class is not. Keeping both under one
    label is what made the first indistinguishable from the second."""
    mcp, _ = _server([["16/07/2026", "Ter", "Ana", "Redes", "101"]])

    async def run():
        out = _text(await mcp.call_tool("confirm_swap",
                                        {"professor": "Ana", "original_date": "01/01/2026",
                                         "new_date": "18/07/2026", "role": "SUPERVISOR",
                                         "identity_label": "Sofia"}))
        assert out.startswith("ERROR") and "No class found" in out
    asyncio.run(run())


def test_a_professor_own_schedule_needs_no_name_and_no_asking():
    """``professor=""`` from an EMPLOYEE resolves to their own identity — the seam that makes
    "minhas aulas" answerable WITHOUT asking the contact who they are. Pinned here because the
    coordinator prompt now promises exactly this to the model."""
    mcp, _ = _server([
        ["20/07/2026", "Seg", "Ana", "Redes", "101"],
        ["20/07/2026", "Ter", "Bruno", "Cálculo", "102"],
    ])

    async def run():
        out = _text(await mcp.call_tool("get_professor_schedule",
                                        {"role": "EMPLOYEE", "identity_label": "Ana",
                                         "include_past": True}))
        assert "Redes" in out and "Cálculo" not in out
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


def test_schedule_tool_discipline_filter_typo_tolerant():
    mcp, _ = _server([
        ["20/07/2026", "Seg", "Ana", "Machine Learning", "101"],
        ["21/07/2026", "Ter", "Ana", "Redes", "101"],
    ])

    async def run():
        out = _text(await mcp.call_tool(
            "get_professor_schedule",
            {"role": "SUPERVISOR", "identity_label": "Sofia", "discipline": "machne learning"}))
        assert "Machine Learning" in out and "Redes" not in out
    asyncio.run(run())


def test_get_professor_info_tool_reads_professors_tab():
    mcp, store = _server([["20/07/2026", "Seg", "Ana", "Redes", "101"]])
    store.put(_SID, "Informações Adicionais",
              [["Disciplina", "CH", "Professor", "e-mail", "titulação"],
               ["Redes", "40", "Ana", "ana@x.edu", "Msc"]])

    async def run():
        out = _text(await mcp.call_tool("get_professor_info",
                                        {"role": "SUPERVISOR", "identity_label": "Sofia"}))
        assert "Ana" in out and "ana@x.edu" in out
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

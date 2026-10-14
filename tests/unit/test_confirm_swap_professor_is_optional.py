"""``confirm_swap``'s ``professor`` is OPTIONAL in its schema — an empty one is the caller.

The service has always accepted ``professor=""``: for a caller who is not the coordination it pins
the swap to the caller's own classes (``CoordinatorService._visible``), exactly as the schedule
reads do. The SIGNATURE said otherwise — ``professor: str`` with no default, so FastMCP published
it in ``required``. A host that reads ``required`` to decide whether a held write is a complete
proposal (the reference host does, since its "a held write missing a required argument is not a
proposal") would then ask a professor «which professor?» about their own class. The schema is
corrected at the source, not worked around in the host.

The other two arguments stay required: a swap with no class date or no destination is not a swap.
"""
from __future__ import annotations

import asyncio
from datetime import date

import pytest

from cogno_praxis.coordinator import CoordinatorConfig, CoordinatorService, InMemorySpreadsheetStore
from cogno_praxis.coordinator.server import build_server

_RULES = (
    "SPREADSHEETS:\nDSA=1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
    'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n'
)
_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]


def _schema() -> dict:
    tools = {t.name: t for t in asyncio.run(build_server().list_tools())}
    return tools["confirm_swap"].inputSchema


def test_professor_is_not_required_and_defaults_to_empty():
    schema = _schema()
    assert "professor" not in (schema.get("required") or [])
    assert schema["properties"]["professor"].get("default") == ""


def test_control_the_class_date_and_the_destination_stay_required():
    assert set(_schema().get("required") or []) == {"original_date", "new_date"}


def test_the_argument_order_did_not_move():
    """``professor`` stays the first property (the dates became keyword-only to keep it there),
    so a schema digest moves only by the ``required`` list and the default."""
    assert list(_schema()["properties"])[:3] == ["professor", "original_date", "new_date"]


def test_the_description_says_empty_is_the_caller():
    tools = {t.name: t for t in asyncio.run(build_server().list_tools())}
    text = " ".join((tools["confirm_swap"].description or "").split())
    assert "Leave ``professor`` empty for the caller's OWN class" in text


def _mcp():
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [[""] * 5] * 3 + [_HEADER] + [
        ["16/07/2026", "Ter", "Otávio Quelme", "Redes", "101"],
        ["16/07/2026", "Ter", "Ilda Varrow", "Bancos", "102"],
        ["18/07/2026", "Qui", "", "Livre", "205"],
    ])
    svc = CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 7, 13))
    return build_server(svc), store


def _call(mcp, args: dict) -> "tuple[str, str]":  # noqa: ANN001
    """(the tool's text, the error's text) — a refusal raises, so the second carries it."""
    async def run() -> str:
        res = await mcp.call_tool("confirm_swap", args)
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")
    try:
        return asyncio.run(run()), ""
    except Exception as exc:  # noqa: BLE001 — FastMCP raises the tool's refusal as ToolError
        return "", str(exc)


_GRID_BEFORE = [["Otávio Quelme", "Redes", "101"], ["Ilda Varrow", "Bancos", "102"],
                ["", "Livre", "205"]]


def _rows(store) -> list:  # noqa: ANN001
    return [r[2:5] for r in store._sheets[(_SID, "Secretaria")][4:7]]


@pytest.mark.parametrize("role", ["SUPERVISOR", "ADMIN", "OWNER"])
def test_the_coordination_with_no_professor_is_refused_and_nothing_moves(role):
    """For an oversight caller an empty professor is the WHOLE master schedule, and the swap used
    to take the first class on that date, whoever taught it. Refused, recoverably, and named."""
    mcp, store = _mcp()
    out, err = _call(mcp, {"original_date": "16/07/2026", "new_date": "18/07/2026",
                           "role": role, "identity_label": "Wenda Corisk"})
    assert out == "" and "Which professor's class?" in err and "Nothing was swapped" in err
    assert _rows(store) == _GRID_BEFORE, "a refused swap moved a row"


def test_the_coordination_naming_the_professor_swaps_that_class():
    mcp, store = _mcp()
    out, err = _call(mcp, {"professor": "Ilda Varrow", "original_date": "16/07/2026",
                           "new_date": "18/07/2026", "role": "SUPERVISOR",
                           "identity_label": "Wenda Corisk"})
    assert err == "" and "Swapped" in out and "Bancos" in out
    rows = _rows(store)
    assert rows[2] == ["Ilda Varrow", "Bancos", "102"] and rows[0] == _GRID_BEFORE[0]


def test_an_omitted_professor_swaps_the_callers_own_class():
    """The service's half, through the tool: a professor (not the coordination) who names nobody
    moves THEIR class — and only theirs."""
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [[""] * 5] * 3 + [_HEADER] + [
        ["16/07/2026", "Ter", "Otávio Quelme", "Redes", "101"],
        ["16/07/2026", "Ter", "Ilda Varrow", "Bancos", "102"],
        ["18/07/2026", "Qui", "", "Livre", "205"],
    ])
    svc = CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 7, 13))
    mcp = build_server(svc)

    async def run() -> str:
        res = await mcp.call_tool("confirm_swap", {"original_date": "16/07/2026",
                                                   "new_date": "18/07/2026", "role": "EMPLOYEE",
                                                   "identity_label": "Otávio Quelme"})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")

    out = asyncio.run(run())
    assert "Swapped" in out and "Redes" in out
    grid = store._sheets[(_SID, "Secretaria")]
    assert grid[6][2:5] == ["Otávio Quelme", "Redes", "101"]
    assert grid[5][2:5] == ["Ilda Varrow", "Bancos", "102"], "another professor's class moved"

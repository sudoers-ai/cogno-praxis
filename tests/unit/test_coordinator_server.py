"""Coordinator FastMCP server — the 6 tools over a service, incl. RBAC + swap + durability."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

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


# ── the calendar export, at the TOOL surface ─────────────────────────────────────────

def _calendar_server(rows, *, sender, today=date(2026, 7, 13), profs=None, tz="America/Sao_Paulo"):
    from cogno_praxis.coordinator import CoordinatorService, InMemorySpreadsheetStore
    cfg = CoordinatorConfig(_RULES + 'TAB_PROFESSORS: "Info"\nRANGE_PROFESSORS: "A1:C50"\n')
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [[""] * 5] * 3 + [_HEADER] + rows)
    store.put(_SID, "Info", profs if profs is not None else
              [["Professor", "e-mail"], ["Ana", "ana@escola.test"]])
    svc = CoordinatorService(store, cfg, today=lambda: today)
    return _bs(svc, sender=sender, tz_name=tz)


def test_the_calendar_tool_answers_with_SENT_only_when_the_mail_left():
    """The single line every downstream promise is read off. Its shape is load-bearing: the
    prompt, the judge and the voicer are all told that "SENT:" is the ONLY evidence an e-mail
    happened, so this pins that the tool actually produces it."""
    from cogno_praxis.coordinator import RecordingCalendarSender

    sender = RecordingCalendarSender()
    mcp = _calendar_server([["20/07/2026", "Seg", "Ana", "Redes", "101"],
                            ["27/07/2026", "Seg", "Ana", "Redes", "101"]], sender=sender)

    async def run():
        out = _text(await mcp.call_tool("send_schedule_to_calendar",
                                        {"role": "EMPLOYEE", "identity_label": "Ana"}))
        assert out.startswith("SENT: 2 class(es) e-mailed to ana@escola.test")
        assert len(sender.sent) == 1
        # the DESCRIPTION reuses the very line the model reads — one formatter, not two
        assert "Turma: DSA" in sender.sent[0]["ics"]
    asyncio.run(run())


def test_the_calendar_tool_RAISES_when_nothing_was_sent():
    """A returned sentence is a SUCCESSFUL tool call, and the MCP bridge stamps a successful
    call on a non-read-only tool as a write. So every no-send path raises instead — otherwise a
    polite refusal would be recorded as an e-mail that went out."""
    from mcp.server.fastmcp.exceptions import ToolError

    mcp = _calendar_server([["20/07/2026", "Seg", "Ana", "Redes", "101"]], sender=None)

    async def run():
        with pytest.raises(ToolError, match="No e-mail is configured"):
            await mcp.call_tool("send_schedule_to_calendar",
                                {"role": "EMPLOYEE", "identity_label": "Ana"})
    asyncio.run(run())


def test_a_refused_calendar_send_is_worded_as_a_limit_and_still_raises():
    """Both halves at once, and they pull in opposite directions: raising is what keeps the turn
    from being recorded as a write, and the WORDING is what keeps the model from reporting a
    breakdown to a professor whose only problem is that they asked about a colleague."""
    from mcp.server.fastmcp.exceptions import ToolError

    from cogno_praxis.coordinator import RecordingCalendarSender

    sender = RecordingCalendarSender()
    mcp = _calendar_server([["20/07/2026", "Seg", "Bruno", "Cálculo", "104"]], sender=sender)

    async def run():
        with pytest.raises(ToolError) as exc:
            await mcp.call_tool("send_schedule_to_calendar",
                                {"role": "EMPLOYEE", "identity_label": "Ana",
                                 "professor": "Bruno"})
        assert "NOT PERMITTED — nothing was sent" in str(exc.value)
        assert "access rule working as intended" in str(exc.value)
        assert sender.sent == []
    asyncio.run(run())


def test_an_unreadable_spreadsheet_is_named_under_the_SENT_line():
    """The partial-read footer travels on the send path too: a professor whose calendar is
    missing one course's classes has to be told which course."""
    from cogno_praxis.coordinator import CoordinatorService, RecordingCalendarSender

    class _HalfBroken:
        def __init__(self, inner):
            self._inner = inner

        def read_range(self, sheet_id, tab, a1_range):
            if sheet_id == "1PoIuYtReWqLkJhGfDsAmNbVcXz0123456789AbCdEfG":
                raise RuntimeError("HTTP 404")
            return self._inner.read_range(sheet_id, tab, a1_range)

        def swap_rows(self, *a, **k):                      # pragma: no cover - unused here
            raise NotImplementedError

    from cogno_praxis.coordinator import InMemorySpreadsheetStore
    rules = (_RULES.replace("SPREADSHEETS:\n", "SPREADSHEETS:\nOUTRA = "
                            "1PoIuYtReWqLkJhGfDsAmNbVcXz0123456789AbCdEfG\n")
             + 'TAB_PROFESSORS: "Info"\nRANGE_PROFESSORS: "A1:C50"\n')
    inner = InMemorySpreadsheetStore()
    inner.put(_SID, "Secretaria",
              [[""] * 5] * 3 + [_HEADER] + [["20/07/2026", "Seg", "Ana", "Redes", "101"]])
    inner.put(_SID, "Info", [["Professor", "e-mail"], ["Ana", "ana@escola.test"]])
    svc = CoordinatorService(_HalfBroken(inner), CoordinatorConfig(rules),
                             today=lambda: date(2026, 7, 13))
    sender = RecordingCalendarSender()
    mcp = _bs(svc, sender=sender)

    async def run():
        out = _text(await mcp.call_tool("send_schedule_to_calendar",
                                        {"role": "EMPLOYEE", "identity_label": "Ana"}))
        assert out.startswith("SENT: 1 class(es)")
        assert "PARTIAL RESULT" in out and "OUTRA" in out
    asyncio.run(run())

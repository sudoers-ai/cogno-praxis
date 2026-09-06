"""The tenant's rules have a SHAPE the parser did not read — and a bad read cost a whole answer.

Measured 2026-09-06 on a live COORDINATOR conversation. The tenant's ``custom_rules`` declare a
``SPREADSHEETS:`` section whose keys contain SPACES ("Turma DSA_33 = <id>"), which the old section
regex (``\\S+\\s*=``) could not match. The section went unrecognised, the parser fell through to
its *no-header* fallback — a scan of the WHOLE document for long id-looking tokens — and swept up
the 31-character slug of a course URL sitting a few lines above it. That fake id sorted FIRST,
its Drive read 404'd, the exception took the entire ``get_professor_schedule`` call with it, and
the professor was told the assistant could not access the schedule. Four real spreadsheets were
readable the whole time.

**The fixture is ANONYMISED and that is not cosmetic.** This repository is public and a Google
Drive id is a capability: anyone holding one can try the file. What the fixture reproduces is the
tenant's rules' SHAPE — keys with spaces (one with a doubled space), four ids with the real
morphology (33 and 44 characters, mixed case, ``-`` and ``_``), a course URL whose slug is long
enough for the scan to mistake it for an id, and the same trailing block of ``KEY: "value"``
config lines. Every id and slug below is invented. Verified against the live rules before and
after the fix: the same 5-entry wrong parse before, the same 4-entry right one after.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ReadReport,
)
from cogno_praxis.coordinator.server import build_server

# ── the anonymised, structurally-equivalent tenant rules ──────────────────────────────
_SLUG = "sample-course-advanced-analytic"          # 31 chars, the scan's minimum is 30
_ID_A = "1QwErTy-UiOpAsDfGhJkLzXcVbNm45678"                    # 33
_ID_B = "1PoIuYtReWqLkJhGfDsAmNbVcXz0123456789AbCdEfG"         # 44
_ID_C = "1ZxCvBnM_AsDfGhJkLqWeRtYuIo78901Q"                    # 33
_ID_D = "1MnBvCxZlKjHgFdSaPoIuYtReWq9876543210ZyXwVuT"         # 44

TENANT_SHAPED_RULES = f"""
# MBA Sample Engineering
- Opening Workshop (4h)
- Fundamentals of Sample Engineering (16h)
- Capstone Project (12h)

# MBA Sample Course & Advanced Analytics
- Opening Workshop (4h)
- Fundamentals of Sample Science (16h)

Syllabus:
 Sample Engineering: https://example.test/mbas/data-engineering/
 Sample Analytics: https://example.test/mbas/{_SLUG}/

# Base spreadsheets (current classes)
SPREADSHEETS:
Turma SMP_33 = {_ID_A}
Turma  SMP_34 = {_ID_B}
Turma  SME_09 = {_ID_C}
Turma SME_10 = {_ID_D}

# Spreadsheet layout
TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A4:E110"
RANGE_METADATA: "A1:E3"

TAB_PROFESSORS: "Informacoes Adicionais"
RANGE_PROFESSORS: "A1:E50"

COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"

FIXED_COLUMNS: "Mes, Dia, Data"
FREE_SLOT_LABELS: "Livre, Reposicao"
SKIP_LABELS: "Reposicao, Recesso, Feriado, Emenda, Livre"
"""

_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]


def _grid(rows):
    """RANGE_SCHEDULE is A4:… → the header sits on sheet row 4 (grid index 3)."""
    return [[""] * 5, [""] * 5, [""] * 5, list(_HEADER)] + rows


# ── (a) keys with spaces ──────────────────────────────────────────────────────────────
def test_a_key_with_spaces_is_a_key():
    cfg = CoordinatorConfig(TENANT_SHAPED_RULES)
    assert cfg.spreadsheets == {
        "Turma SMP_33": _ID_A, "Turma SMP_34": _ID_B,
        "Turma SME_09": _ID_C, "Turma SME_10": _ID_D,
    }
    # The doubled space in "Turma  SMP_34" collapses: the key is a LABEL a human reads back in
    # "Turma SMP_34: HTTP 404", and it must not depend on how many spaces the tenant typed.
    assert "Turma  SMP_34" not in cfg.spreadsheets


# ── (b) a declared header is never overruled by the whole-text guess ──────────────────
def test_the_url_slug_never_becomes_a_spreadsheet():
    cfg = CoordinatorConfig(TENANT_SHAPED_RULES)
    assert len(cfg.spreadsheets) == 4                     # exactly the four declared
    assert _SLUG not in cfg.spreadsheets.values()         # the URL slug is not an id
    assert not any(k.startswith("SHEET_") for k in cfg.spreadsheets)   # the scan never ran


def test_a_header_with_nothing_usable_is_unconfigured_rather_than_guessed():
    # (b) taken to its limit: the header is there, the pairs are not. "No spreadsheet" is a
    # truthful answer the service already handles; a guessed id is a 404 with someone's name on
    # it. So the fallback must stay UNREACHABLE once the header exists.
    rules = f"SPREADSHEETS:\nnothing here\n\nSee https://example.test/mbas/{_SLUG}/\n"
    assert CoordinatorConfig(rules).spreadsheets == {}
    assert not CoordinatorConfig(rules).configured


def test_a_pair_whose_value_is_not_an_id_is_skipped_not_fatal():
    rules = f"SPREADSHEETS:\nTurma A = short\nTurma B = {_ID_A}\n"
    assert CoordinatorConfig(rules).spreadsheets == {"Turma B": _ID_A}


def test_without_a_header_the_scan_behaves_exactly_as_before():
    # The twin that pins the OTHER path: loosely-formatted rules with no header at all still get
    # the parent's whole-text guess, ids in document order, SHEET_n keys. Unchanged on purpose —
    # a shape rule on this path was considered and dropped (see the PR: it has no measured
    # beneficiary and would risk rejecting a legitimate id).
    rules = f"Turma A {_ID_A}\nqualquer texto\nTurma B {_ID_B}\n"
    assert CoordinatorConfig(rules).spreadsheets == {"SHEET_1": _ID_A, "SHEET_2": _ID_B}


def test_the_documented_no_space_format_still_parses():
    assert CoordinatorConfig(f"SPREADSHEETS:\nDSA_33={_ID_A}\nDE_09={_ID_B}\n").spreadsheets == {
        "DSA_33": _ID_A, "DE_09": _ID_B}


# ── (c) one unreadable spreadsheet does not take the others with it ───────────────────
class _Boom(Exception):
    """An adapter failure carrying an HTTP status, the shape ``GoogleSheetsStore`` raises."""

    def __init__(self, status: int) -> None:
        super().__init__(f"Client error '{status}'")
        self.response = type("R", (), {"status_code": status})()


class _FlakyStore(InMemorySpreadsheetStore):
    """An in-memory store where ONE sheet id always fails to read."""

    def __init__(self, broken: str, status: int = 404) -> None:
        super().__init__()
        self._broken, self._status = broken, status

    def read_range(self, sheet_id, tab, a1_range):
        if sheet_id == self._broken:
            raise _Boom(self._status)
        return super().read_range(sheet_id, tab, a1_range)


def _flaky_service(*, broken: str = _ID_A, today=date(2026, 9, 6)):
    cfg = CoordinatorConfig(TENANT_SHAPED_RULES)
    store = _FlakyStore(broken)
    store.put(_ID_B, "Secretaria", _grid([["10/09/2026", "Qui", "Ana", "Redes", "101"]]))
    store.put(_ID_C, "Secretaria", _grid([["11/09/2026", "Sex", "Ana", "Calculo", "102"]]))
    store.put(_ID_D, "Secretaria", _grid([["12/09/2026", "Sab", "Bruno", "Spark", "103"]]))
    return CoordinatorService(store, cfg, today=lambda: today), store


def test_one_404_leaves_the_other_three_readable():
    svc, _ = _flaky_service()
    report = ReadReport()
    got = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia", report=report)
    assert [e.subject for e in got] == ["Redes", "Calculo", "Spark"]
    assert [(e.sheet_key, e.message) for e in report.errors] == [("Turma SMP_33", "HTTP 404")]


def test_every_spreadsheet_readable_reports_nothing():
    # The mutation twin for the footer: the note must be earned, not permanent.
    svc, _ = _flaky_service(broken="no-such-sheet")
    report = ReadReport()
    svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia", report=report)
    assert report.errors == []


def test_the_tool_returns_what_it_read_and_names_what_it_could_not():
    svc, _ = _flaky_service()
    mcp = build_server(svc)

    async def run():
        res = await mcp.call_tool("get_professor_schedule",
                                  {"role": "SUPERVISOR", "identity_label": "Sofia"})
        out = "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")
        assert "Redes" in out and "Calculo" in out and "Spark" in out   # what it COULD read
        assert "PARTIAL RESULT" in out and "Turma SMP_33: HTTP 404" in out
        assert not out.startswith("ERROR")            # not a dead turn — the model can speak
        return out
    import asyncio
    asyncio.run(run())


def test_a_write_refuses_a_half_loaded_schedule():
    # Reads degrade; a WRITE must not. A missing row and an unread sheet look identical from
    # here, and acting on the second one moves a class nobody asked to move.
    svc, _ = _flaky_service()
    with pytest.raises(CoordinatorError, match="could not be read"):
        svc.confirm_swap(professor="Ana", original_date="10/09/2026", new_date="11/09/2026",
                         role="SUPERVISOR", identity_label="Sofia")


def test_the_professors_tab_degrades_the_same_way():
    svc, store = _flaky_service()
    store.put(_ID_B, "Informacoes Adicionais",
              [["Disciplina", "CH", "Professor", "e-mail"], ["Redes", "40", "Ana", "ana@x.edu"]])
    report = ReadReport()
    rows = svc.get_professor_info(role="SUPERVISOR", identity_label="Sofia", report=report)
    assert [r["professor"] for r in rows] == ["Ana"]
    assert [e.sheet_key for e in report.errors] == ["Turma SMP_33"]

"""Coordinator vertical — domain over the in-memory SpreadsheetStore (no infra)."""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
)

_RULES = """
SPREADSHEETS:
DSA=1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8
TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A4:E200"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
FIXED_COLUMNS: "Data, Dia"
FREE_SLOT_LABELS: "Livre"
SKIP_LABELS: "Feriado, Recesso"
"""

_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]


def _svc(rows, *, today=date(2026, 7, 13)):
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    # grid row 0 = sheet row 1; schedule range starts at A4 → put header at row 4 (index 3)
    grid = [[""] * 5, [""] * 5, [""] * 5] + [_HEADER] + rows
    store.put(_SID, "Secretaria", grid)
    return CoordinatorService(store, cfg, today=lambda: today), store


def test_config_parses_custom_rules():
    cfg = CoordinatorConfig(_RULES)
    assert cfg.configured
    assert cfg.spreadsheets == {"DSA": _SID}
    assert cfg.tab_schedule == "Secretaria" and cfg.range_schedule == "A4:E200"
    assert cfg.column_professor == "Professor"
    assert "Livre" in cfg.free_slot_labels and "Feriado" in cfg.skip_labels


def test_empty_rules_is_unconfigured():
    assert not CoordinatorConfig("").configured
    assert CoordinatorConfig("").spreadsheets == {}


def test_aggregate_sorts_chrono_and_drops_skip():
    svc, _ = _svc([
        ["20/07/2026", "Seg", "Ana", "Redes", "101"],
        ["06/07/2026", "Seg", "Ana", "Feriado", "101"],   # skip label → dropped
        ["13/07/2026", "Seg", "Bruno", "Cálculo", "102"],
    ])
    got = svc.aggregate()
    assert [e.subject for e in got] == ["Cálculo", "Redes"]      # skip gone, chrono order
    assert got[0].date_str == "13/07/2026"


def test_rbac_professor_sees_only_own():
    svc, _ = _svc([
        ["20/07/2026", "Seg", "Ana", "Redes", "101"],
        ["20/07/2026", "Ter", "Bruno", "Cálculo", "102"],
    ])
    mine = svc.get_professor_schedule(role="EMPLOYEE", identity_label="Ana")
    assert {e.professor for e in mine} == {"Ana"}
    # a professor asking for someone else → refused
    with pytest.raises(CoordinatorError):
        svc.get_professor_schedule(professor="Bruno", role="EMPLOYEE", identity_label="Ana")


def test_supervisor_sees_all_or_filters():
    svc, _ = _svc([
        ["20/07/2026", "Seg", "Ana", "Redes", "101"],
        ["20/07/2026", "Ter", "Bruno", "Cálculo", "102"],
    ])
    allc = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia")
    assert len(allc) == 2
    only = svc.get_professor_schedule(professor="Bruno", role="SUPERVISOR", identity_label="Sofia")
    assert {e.professor for e in only} == {"Bruno"}


def test_deadlines_flags_last_class_within_14d():
    # Ana's last Redes class was 07/07 (6 days ago, within 14) → due; Bruno's is future → not.
    svc, _ = _svc([
        ["01/07/2026", "Seg", "Ana", "Redes", "101"],
        ["07/07/2026", "Seg", "Ana", "Redes", "101"],     # last, 6 days ago
        ["20/07/2026", "Seg", "Bruno", "Cálculo", "102"],
    ], today=date(2026, 7, 13))
    due = svc.check_deadlines(role="SUPERVISOR", identity_label="Sofia")
    assert [(e.professor, e.date_str) for e in due] == [("Ana", "07/07/2026")]


def test_weekly_briefing_next_7_days():
    svc, _ = _svc([
        ["13/07/2026", "Seg", "Ana", "Redes", "101"],     # today → in
        ["19/07/2026", "Dom", "Ana", "Redes", "101"],     # +6 → in
        ["25/07/2026", "Sex", "Ana", "Redes", "101"],     # +12 → out
    ], today=date(2026, 7, 13))
    wk = svc.weekly_briefing(role="SUPERVISOR", identity_label="Sofia")
    assert [e.date_str for e in wk] == ["13/07/2026", "19/07/2026"]


def test_ibope_status_last_class_today():
    svc, _ = _svc([
        ["01/07/2026", "Seg", "Ana", "Redes", "101"],
        ["13/07/2026", "Seg", "Ana", "Redes", "101"],     # last class, is today → IBOPE
        ["13/07/2026", "Seg", "Bruno", "Cálculo", "102"], # today but NOT last (has 20/07) → no
        ["20/07/2026", "Seg", "Bruno", "Cálculo", "102"],
    ], today=date(2026, 7, 13))
    ib = svc.ibope_status(role="SUPERVISOR", identity_label="Sofia")
    assert [(e.professor, e.subject) for e in ib] == [("Ana", "Redes")]


def test_find_replacement_slot_free_within_21d():
    svc, _ = _svc([
        ["15/07/2026", "Seg", "", "Livre", "101"],        # free, +2 → in
        ["10/08/2026", "Seg", "", "Livre", "101"],        # free, +28 → out
        ["16/07/2026", "Ter", "Ana", "Redes", "101"],     # not free
    ], today=date(2026, 7, 13))
    slots = svc.find_replacement_slot(role="SUPERVISOR", identity_label="Sofia")
    assert [e.date_str for e in slots] == ["15/07/2026"]


def test_confirm_swap_exchanges_content_keeps_dates():
    svc, store = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101"],     # source (Ana's class)
        ["18/07/2026", "Qui", "", "Livre", "205"],        # dest (free slot)
    ], today=date(2026, 7, 13))
    src, dst = svc.confirm_swap(professor="Ana", original_date="16/07/2026",
                                new_date="18/07/2026", role="SUPERVISOR", identity_label="Sofia")
    grid = store._sheets[(_SID, "Secretaria")]
    # after swap: content (Professor/Disciplina/Sala) moved; Data/Dia stayed put
    row_src, row_dst = grid[src.row_idx + 3], grid[dst.row_idx + 3]   # +3: metadata offset
    assert row_src[0] == "16/07/2026" and row_dst[0] == "18/07/2026"  # dates fixed
    assert row_src[2:5] == ["", "Livre", "205"]                        # source now holds the free
    assert row_dst[2:5] == ["Ana", "Redes", "101"]                     # dest now holds Ana's class

"""A swap must carry every cell of the row, including the ones no header names.

Measured on the live corpus, 2026-09-07. The tenant's schedule tab carries columns AFTER the
last named one, and their header cells are BLANK. Read back out of the persisted traces, a row
looks like this (names removed):

    … | Professor: <nome> | : 16.0 | : Confirmado | : Proposta enviada
    … | Professor: <nome> | : 4.0

One of those unnamed columns is an hour total — ``4.0`` against the four-hour workshop, ``16.0``
against the sixteen-hour disciplines — and at least one is an approval state that moves from
``Proposta enviada`` to ``Confirmado``. They reach the model at all only because
``GoogleSheetsStore.read_range`` honours an A1 range as a ROW OFFSET and returns every column.

``confirm_swap`` could not write them. ``_resolve_columns`` bounded the content columns at the
last NON-EMPTY header, so with blank headers the boundary fell on ``Professor`` and the content
set was ``[3, 4]``: a swap exchanged the discipline and the professor and left everything past
the header where it was. The class moved to its new date; its hour total and its "Confirmado"
stayed with the old one. **Both rows are still full afterwards** — each simply describes the
other's class now — so nothing looks broken to anyone reading the sheet.

**These tests never name those columns, and that is the point.** To keep a cell you have to
carry it, not understand it. The fixture's trailing columns are exercised purely by position,
so the day somebody opens the sheet and writes the headers in, none of this has to change —
``test_a_NAMED_column_can_still_be_pinned_down_by_the_tenant`` is the twin that proves the
escape hatch still works once they are named.

The fixture rows are PADDED to a common width because that is what production does: openpyxl's
``iter_rows(values_only=True)`` on a read-only workbook yields every row at the sheet's full
width, ``None``-filled (measured). A ragged row is a shape only the in-memory fake can produce,
and the store's own bounds guard skips what it cannot address there — unchanged by this file.
"""

from __future__ import annotations

from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
)

_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"

_RULES = f"""
SPREADSHEETS:
DSA={_SID}
TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A4:E200"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
FIXED_COLUMNS: "Data, Dia"
FREE_SLOT_LABELS: "Livre"
SKIP_LABELS: "Feriado, Recesso"
"""

# Five named columns and three the header leaves BLANK — the live shape. Nothing below ever
# says what columns 5, 6 and 7 mean; they are only ever addressed by position.
_HEADER_WITH_BLANKS = ["Data", "Dia", "Professor", "Disciplina", "Sala", "", "", ""]
_HEADER_PLAIN = ["Data", "Dia", "Professor", "Disciplina", "Sala"]


def _svc(rows, *, header, today=date(2026, 7, 13), rules=_RULES):
    cfg = CoordinatorConfig(rules)
    store = InMemorySpreadsheetStore()
    width = len(header)
    pad = [""] * width
    grid = [list(pad), list(pad), list(pad)] + [list(header)] + [list(r) for r in rows]
    store.put(_SID, "Secretaria", grid)
    return CoordinatorService(store, cfg, today=lambda: today), store


def _rows(store):
    """The two data rows of the schedule range, absolute (the range starts at sheet row 4)."""
    grid = store._sheets[(_SID, "Secretaria")]
    return grid[4], grid[5]


# ── twin 1: what the header does not reach still travels ─────────────────────────────
def test_cells_past_the_last_named_header_travel_with_the_class():
    """The defect, stated as the property it broke: the class moved and its trailing cells did
    not, so the hour total and the approval state came to describe a class that is no longer
    on that row."""
    svc, store = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "Confirmado", "Proposta enviada"],
        ["18/07/2026", "Qui", "", "Livre", "205", "", "", ""],
    ], header=_HEADER_WITH_BLANKS)

    svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                     role="SUPERVISOR", identity_label="Sofia")
    src, dst = _rows(store)

    # the three unnamed cells went WITH the class, to the row the class is on now
    assert dst[5:8] == ["16.0", "Confirmado", "Proposta enviada"]
    assert src[5:8] == ["", "", ""]
    # and nothing was invented or lost on the way: the multiset of trailing cells is conserved
    assert sorted(src[5:8] + dst[5:8]) == sorted(["16.0", "Confirmado", "Proposta enviada",
                                                  "", "", ""])


def test_the_trailing_cells_land_on_the_SAME_row_as_the_class_they_describe():
    """The sharper statement of the same property, and the one a reader of the sheet cares
    about: after the swap the hour total sits beside the discipline it is the hour total OF.
    Both rows stay full either way — that is why the defect is invisible — so the assertion has
    to tie the cells to the discipline, not merely count them."""
    svc, store = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "Confirmado", ""],
        ["18/07/2026", "Qui", "", "Livre", "205", "", "", ""],
    ], header=_HEADER_WITH_BLANKS)

    svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                     role="SUPERVISOR", identity_label="Sofia")
    src, dst = _rows(store)

    row_of_redes = dst if dst[3] == "Redes" else src
    assert row_of_redes[3] == "Redes"
    assert row_of_redes[5] == "16.0", "the hour total must be on the row the discipline is on"
    assert row_of_redes[6] == "Confirmado"


def test_a_swap_between_two_rows_that_BOTH_carry_trailing_cells_exchanges_them():
    """Not just "the empty one receives": a free slot that already carries state must not have
    it overwritten by a one-way copy. A swap is an exchange, on every column it touches."""
    svc, store = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "Confirmado", ""],
        ["18/07/2026", "Qui", "", "Livre", "205", "4.0", "Proposta enviada", ""],
    ], header=_HEADER_WITH_BLANKS)

    svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                     role="SUPERVISOR", identity_label="Sofia")
    src, dst = _rows(store)

    assert src[5:7] == ["4.0", "Proposta enviada"]
    assert dst[5:7] == ["16.0", "Confirmado"]


# ── twin 2 (the negative twin): the swap still swaps what it MUST ────────────────────
def test_the_swap_still_moves_the_class_and_still_leaves_the_dates_put():
    """Obligatory. Widening what travels is only correct if nothing that already travelled
    stopped, and nothing that was pinned came loose. ``Data``/``Dia`` are FIXED_COLUMNS and
    stay; the professor, the discipline and the room move."""
    svc, store = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "Confirmado", ""],
        ["18/07/2026", "Qui", "", "Livre", "205", "", "", ""],
    ], header=_HEADER_WITH_BLANKS)

    svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                     role="SUPERVISOR", identity_label="Sofia")
    src, dst = _rows(store)

    assert src[0:2] == ["16/07/2026", "Ter"]        # the dates did NOT move
    assert dst[0:2] == ["18/07/2026", "Qui"]
    assert src[2:5] == ["", "Livre", "205"]         # the free slot is where the class was
    assert dst[2:5] == ["Ana", "Redes", "101"]      # and the class is where the slot was


# ── twin 3: a sheet with no extra columns is byte-identical to before ────────────────
def test_a_sheet_whose_header_reaches_every_column_behaves_exactly_as_before():
    """The tenant whose sheet has no unnamed columns must see no change at all — this is a
    widening, not a redefinition."""
    svc, store = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101"],
        ["18/07/2026", "Qui", "", "Livre", "205"],
    ], header=_HEADER_PLAIN)

    svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                     role="SUPERVISOR", identity_label="Sofia")
    src, dst = _rows(store)

    assert src == ["16/07/2026", "Ter", "", "Livre", "205"]
    assert dst == ["18/07/2026", "Qui", "Ana", "Redes", "101"]


def test_the_content_columns_of_a_fully_named_header_are_unchanged():
    """The same claim one layer down, where a byte-for-byte comparison is actually possible:
    with no unnamed column the resolved content set is what it always was."""
    svc, _ = _svc([], header=_HEADER_PLAIN)
    assert svc._resolve_columns(_HEADER_PLAIN).content_indices == [2, 3, 4]
    # and a READ resolves the same set it resolved before, because reads pass no width at all
    assert svc._resolve_columns(_HEADER_WITH_BLANKS).content_indices == [2, 3, 4]


def test_only_the_WRITE_path_widens_and_it_widens_by_the_row_not_the_header():
    """Where the two facts meet: the header says the row ends at ``Sala``; the row says
    otherwise, and the row is what gets written."""
    svc, _ = _svc([], header=_HEADER_WITH_BLANKS)
    assert svc._resolve_columns(_HEADER_WITH_BLANKS, width=8).content_indices == [2, 3, 4, 5, 6, 7]
    # a width NARROWER than the header never shrinks the set below the header's own columns
    assert svc._resolve_columns(_HEADER_WITH_BLANKS, width=2).content_indices == [2, 3, 4]


# ── the escape hatch: naming a column is still how a tenant pins it down ─────────────
def test_a_NAMED_column_can_still_be_pinned_down_by_the_tenant():
    """The claim that this fix survives somebody naming the columns, measured rather than
    promised. An unnamed cell travels because nothing can exempt it — ``FIXED_COLUMNS`` matches
    header NAMES. Give the column a name and put that name in ``FIXED_COLUMNS`` and it stops
    travelling, exactly like ``Data`` does. Nothing here has to be rewritten on that day."""
    named = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Carga", "Semana", ""]
    rules = _RULES.replace('FIXED_COLUMNS: "Data, Dia"', 'FIXED_COLUMNS: "Data, Dia, Semana"')
    svc, store = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "S29", "Confirmado"],
        ["18/07/2026", "Qui", "", "Livre", "205", "", "S30", ""],
    ], header=named, rules=rules)

    svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                     role="SUPERVISOR", identity_label="Sofia")
    src, dst = _rows(store)

    assert src[6] == "S29" and dst[6] == "S30"      # the NAMED fixed column stayed put
    assert dst[5] == "16.0"                          # the named content column travelled
    assert dst[7] == "Confirmado"                    # and so did the still-unnamed one


# ── the read path is untouched ───────────────────────────────────────────────────────
def test_reading_a_sheet_with_unnamed_columns_is_unaffected():
    """The width argument defaults to 0, so every read resolves what it resolved yesterday.
    The unnamed cells are still carried on the entry and still shown by the formatter — this
    change is about the WRITE."""
    svc, _ = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "Confirmado", ""],
    ], header=_HEADER_WITH_BLANKS)
    entries = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                         include_past=True, apply_horizon=False)
    assert len(entries) == 1
    assert entries[0].cells[5:8] == ["16.0", "Confirmado", ""]
    assert entries[0].subject == "Redes" and entries[0].professor == "Ana"


# ── the destination rule: only an open slot, and a refusal that SAYS SO ──────────────
#
# The owner's rule is "the destination can only be an empty slot or a «Reposição» slot", and
# that is already what the code enforces — through the tenant's own ``FREE_SLOT_LABELS``, which
# for the live tenant reads "Livre, Reposição": "Livre" IS the empty slot, spelled. What was
# missing is the REASON. One sentence covered four different worlds, and a contact who is told
# only "no free slot found" tries another date, and then another.
#
# Measured before widening anything: of the 13 distinct live schedule lines that provably were
# not cut before the discipline field (the persisted tool result is capped at 240 characters, so
# most lines cannot answer this at all), 0 carry an EMPTY discipline cell. There is therefore no
# evidence of an empty-subject row distinct from the "Livre" label, and this file does not widen
# what counts as a destination on the strength of 13 lines. It only names the refusal.

def _occupied_dest():
    return _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "Confirmado", ""],
        ["18/07/2026", "Qui", "Bruno", "Estatistica", "205", "20.0", "Confirmado", ""],
    ], header=_HEADER_WITH_BLANKS)


def test_a_destination_that_already_has_a_class_is_refused_WITH_THE_REASON():
    from cogno_praxis.coordinator import CoordinatorError
    import pytest as _pytest
    svc, _ = _occupied_dest()
    with _pytest.raises(CoordinatorError) as exc:
        svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                         role="SUPERVISOR", identity_label="Sofia")
    msg = str(exc.value)
    assert "already has a class scheduled" in msg
    assert "Livre" in msg, "the reader cannot guess the tenant's own label for an open slot"
    # ...and it names the obstacle, never the person behind it: whose class occupies that date
    # is somebody else's schedule, and the access rule does not stop inside an error message.
    assert "Bruno" not in msg and "Estatistica" not in msg


def test_a_refusal_leaves_NOTHING_written():
    """The obligatory negative twin. A refusal that has already touched the sheet is worse than
    the defect it refused: the class is half-moved and nobody was told. Measured by comparing
    the whole grid, not one row — a partial write anywhere is a failure here."""
    from cogno_praxis.coordinator import CoordinatorError
    import copy
    import pytest as _pytest
    svc, store = _occupied_dest()
    before = copy.deepcopy(store._sheets[(_SID, "Secretaria")])
    with _pytest.raises(CoordinatorError):
        svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                         role="SUPERVISOR", identity_label="Sofia")
    assert store._sheets[(_SID, "Secretaria")] == before, "a refused swap wrote to the sheet"


def test_a_date_that_is_not_in_the_schedule_says_that_and_not_something_else():
    from cogno_praxis.coordinator import CoordinatorError
    import pytest as _pytest
    svc, _ = _occupied_dest()
    with _pytest.raises(CoordinatorError) as exc:
        svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="25/12/2026",
                         role="SUPERVISOR", identity_label="Sofia")
    assert "not a date in this schedule" in str(exc.value)


def test_a_holiday_is_refused_as_a_HOLIDAY_and_not_as_a_missing_date():
    """A skip-label row is dropped from the ordinary aggregate, so before this it looked exactly
    like a date that does not exist. They want different next moves."""
    from cogno_praxis.coordinator import CoordinatorError
    import pytest as _pytest
    svc, _ = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "Confirmado", ""],
        ["18/07/2026", "Qui", "", "Feriado", "", "", "", ""],
    ], header=_HEADER_WITH_BLANKS)
    with _pytest.raises(CoordinatorError) as exc:
        svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                         role="SUPERVISOR", identity_label="Sofia")
    msg = " ".join(str(exc.value).split())      # flattened: pin the sentence, not the wrapping
    assert "Feriado" in msg
    assert "no class can be moved onto it" in msg


def test_a_Reposicao_slot_is_STILL_a_valid_destination():
    """The twin that keeps the refusal from swallowing the rule it is supposed to police: the
    two labels the tenant declares must still work, trailing cells and all."""
    svc, store = _svc([
        ["16/07/2026", "Ter", "Ana", "Redes", "101", "16.0", "Confirmado", ""],
        ["18/07/2026", "Qui", "", "Reposicao", "", "", "", ""],
    ], header=_HEADER_WITH_BLANKS,
        rules=_RULES.replace('FREE_SLOT_LABELS: "Livre"',
                             'FREE_SLOT_LABELS: "Livre, Reposicao"'))
    svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                     role="SUPERVISOR", identity_label="Sofia")
    src, dst = _rows(store)
    assert dst[3] == "Redes" and dst[5] == "16.0"
    assert src[3] == "Reposicao"


def test_the_diagnosis_cannot_turn_a_clean_refusal_into_a_crash():
    """``_why_not_a_destination`` re-reads the sheet to say WHY. It runs on the failure path, so
    a store that has started throwing must still produce the refusal — a diagnostic that raises
    replaces a sentence the contact can act on with a stack trace nobody sees. ``aggregate``
    already swallows a per-sheet failure into its report, and this pins that the refusal inherits
    that and does not grow a second, louder failure mode."""
    from cogno_praxis.coordinator import CoordinatorError
    import pytest as _pytest
    svc, store = _occupied_dest()

    calls = {"n": 0}
    real = store.read_range

    def flaky(sheet_id, tab, a1_range):
        calls["n"] += 1
        if calls["n"] > 1:                       # the first read (the swap's own) succeeds
            raise RuntimeError("the sheet went away between the read and the diagnosis")
        return real(sheet_id, tab, a1_range)

    store.read_range = flaky                      # type: ignore[method-assign]
    with _pytest.raises(CoordinatorError) as exc:
        svc.confirm_swap(professor="Ana", original_date="16/07/2026", new_date="18/07/2026",
                         role="SUPERVISOR", identity_label="Sofia")
    assert "RuntimeError" not in str(exc.value)
    assert "Livre" in str(exc.value)              # still a usable sentence

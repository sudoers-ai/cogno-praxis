"""``daily_checks`` — one question ("o que tenho hoje?"), answered from the predicates that
already existed.

Three things a professor otherwise asks one tool at a time: the classes happening TODAY, the
grade/attendance deadlines still inside their window, and the discipline whose LAST class is
today and therefore needs the survey (IBOPE) nudge. This file pins the composition, and it pins
what the composition is NOT allowed to become.

**The deadline split is "closes today" vs "has days left", and that is the only split the data
supports.** ``check_deadlines`` keeps ``last_class < today <= last_class + GRADE_GRACE_DAYS``,
so a deadline that has genuinely EXPIRED never reaches this method — there is no overdue set to
distinguish, and ``test_a_genuinely_overdue_deadline_is_invisible_to_this_vertical`` states that
as a measured fact rather than leaving the next reader to discover it. Widening the source
window would change a shipped tool's meaning for every caller it already has.

**What is deliberately absent is the confirmation column.** The tenant's schedule tab carries an
approval state ("Confirmado" / "Proposta enviada") in columns whose HEADER CELL IS BLANK —
measured on the live corpus 2026-09-07, pinned by
``test_a_swap_does_not_drop_what_it_cannot_name.py``. Every reader in this vertical resolves a
column by NAME, so that state is unreachable, and reaching for it by POSITION would be guessing
at a STATE field: one inserted column and the reader reports the wrong approval, silently.
Carrying a cell you cannot name is safe; INTERPRETING one is not. A block built on the existing
``_entry_status`` would have been structurally empty in production and green here — so it was
not built. It lands the day somebody writes those headers in, with no code change.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import date, timedelta

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    build_server,
)
from cogno_praxis.coordinator.server import (
    _DAILY_SECTIONS,
    _daily_checks_text,
    _status_args,
)
from cogno_praxis.coordinator.service import GRADE_GRACE_DAYS

_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
_RULES = (
    f"SPREADSHEETS:\nDSA={_SID}\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
    'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n'
)

_TODAY = date(2026, 9, 8)
_SUPERVISOR = {"role": "SUPERVISOR", "identity_label": "Sofia"}


def _d(offset: int) -> str:
    """``offset`` days from the fixture's today, as the sheet writes a date."""
    return (_TODAY + timedelta(days=offset)).strftime("%d/%m/%Y")


#: The day this file is about, laid out so every branch has a witness AND a near-miss beside it.
#:
#: * ``Redes`` runs today AND next week → a class today that is NOT its discipline's last, so it
#:   must reach ``classes_today`` and must NOT reach the survey trigger;
#: * ``NoSQL`` runs today and nowhere else → today's class AND the survey trigger;
#: * ``ETL`` ended exactly ``GRADE_GRACE_DAYS`` ago → the window closes TODAY;
#: * ``Python`` ended yesterday → inside the window with days to spare;
#: * ``Estatistica`` ended five weeks ago → OUTSIDE the window, and therefore invisible.
_ROWS = [
    [_d(0), "Ter", "Ana", "Redes", "101"],
    [_d(7), "Ter", "Ana", "Redes", "101"],
    [_d(0), "Ter", "Ana", "NoSQL", "102"],
    [_d(-GRADE_GRACE_DAYS), "Ter", "Ana", "ETL", "103"],
    [_d(-1), "Seg", "Ana", "Python", "104"],
    [_d(-38), "Sab", "Ana", "Estatistica", "105"],
]


class _RefusingStore(InMemorySpreadsheetStore):
    """A store that reads normally and SHOUTS on any write.

    The negative twin needs a witness that fails loudly rather than a comparison that happens to
    come out equal: a write that raises names itself in the traceback, while a silent one only
    shows up as a diff somebody has to notice."""

    def swap_rows(self, *a, **kw):                      # noqa: ANN002, ANN003 — a tripwire
        raise AssertionError("daily_checks is a READ — nothing in it may write to a sheet")


def _svc(rows=None, *, today=_TODAY, store=None):
    cfg = CoordinatorConfig(_RULES)
    st = store if store is not None else InMemorySpreadsheetStore()
    grid = [[""] * 5] * 3 + [list(_HEADER)] + [list(r) for r in (_ROWS if rows is None else rows)]
    st.put(_SID, "Secretaria", grid)
    return CoordinatorService(st, cfg, today=lambda: today), st


def _text(res):
    return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")


def _rendered(svc, **kw):
    dc = svc.daily_checks(role="SUPERVISOR", identity_label="Sofia", **kw)
    return _daily_checks_text(dc, **_status_args(svc))


# ── twin 1: today's classes, and the survey trigger that is NOT the same set ──────────
def test_todays_classes_and_the_survey_trigger_are_both_there_and_are_not_the_same_list():
    """Both blocks land, and the near-miss discriminates them.

    ``Redes`` runs today and again next week, so it is a class today and NOT a last class;
    ``NoSQL`` is both. A composition that confused the two would still show "two classes today"
    and would nudge the professor to run a survey on a discipline that has six more weeks."""
    svc, _ = _svc()
    dc = svc.daily_checks(**_SUPERVISOR)

    assert sorted(e.subject for e in dc.classes_today) == ["NoSQL", "Redes"]
    assert [e.subject for e in dc.ibope_today] == ["NoSQL"]
    assert not dc.empty


# ── twin 2: a window closing today is not a window with days left ────────────────────
def test_a_deadline_closing_today_and_one_with_days_left_are_told_apart():
    """The split the day actually turns on. ``days_left`` is derived from the grace constant
    here so the reader never has to hold it, and ``0`` means "cannot wait a day"."""
    svc, _ = _svc()
    dc = svc.daily_checks(**_SUPERVISOR)

    assert [d.entry.subject for d in dc.due_today] == ["ETL"]
    assert [d.entry.subject for d in dc.due_ahead] == ["Python"]
    assert [d.days_left for d in dc.due_today] == [0]
    assert [d.days_left for d in dc.due_ahead] == [GRADE_GRACE_DAYS - 1]
    # and the two never overlap, whatever the fixture grows into
    assert len(dc.due_today) + len(dc.due_ahead) == len(dc.deadlines)


def test_the_two_deadline_groups_reach_the_reader_under_DIFFERENT_headings():
    """The distinction has to survive into the bytes a model reads, or it was never made.

    A single "deadlines" block containing both would be a listing the reader has to re-derive
    the urgency from — and the urgency is the whole reason the split exists.

    Asserted against ``_DAILY_SECTIONS`` rather than against the wording, deliberately: this
    file pins that the two groups arrive SEPARATED and in urgency order, not that a particular
    English sentence introduces them. A channel-aware renderer may reword every one of these
    labels without touching a property anybody agreed to."""
    out = _rendered(_svc()[0])
    closing, later = _DAILY_SECTIONS["due_today"], _DAILY_SECTIONS["due_ahead"]

    assert closing in out and later in out
    assert closing != later
    assert out.index(closing) < out.index(later), "what closes today comes first"
    # and each group's own discipline sits under its own heading, not merged into one list
    assert "ETL" in out[out.index(closing):out.index(later)]
    assert "Python" in out[out.index(later):]


# ── twin 3: a day with nothing in it says so ONCE ────────────────────────────────────
def test_a_day_with_nothing_in_it_is_ONE_sentence_and_never_an_empty_block():
    """Two claims, and the second is the one that matters to a model.

    An empty day must READ as an answer — a header with a void under it is the shape a model
    fills in from memory. So: no section headings at all, and a sentence that says the emptiness
    is complete."""
    svc, _ = _svc([[_d(200), "Ter", "Ana", "Redes", "101"]])
    dc = svc.daily_checks(**_SUPERVISOR)
    assert dc.empty

    out = _daily_checks_text(dc, **_status_args(svc))
    assert "Nothing today" in out
    for heading in _DAILY_SECTIONS.values():
        assert heading not in out, "an empty day must not be rendered as empty sections"


def test_a_PARTLY_empty_day_still_gets_a_sentence_where_the_list_would_be():
    """The other half of the same rule, and the one an ``if dc.empty`` alone would miss: a day
    with a deadline but no class must say "no classes today", not print a bare heading."""
    svc, _ = _svc([[_d(-1), "Seg", "Ana", "Python", "104"]])
    out = _daily_checks_text(svc.daily_checks(**_SUPERVISOR), **_status_args(svc))

    assert _DAILY_SECTIONS["classes"] + "\nNo classes today." in out
    assert _DAILY_SECTIONS["ibope"] + "\nNo discipline has its last class today" in out
    assert "Python" in out


# ── twin 4 (the negative twin): it is a READ ─────────────────────────────────────────
def test_daily_checks_writes_nothing_anywhere():
    """The property that keeps this tool safe, stated as a property and not as an intention.

    Two witnesses, because either alone is weak: the store REFUSES a write (so an attempt names
    itself), and the whole grid is compared byte for byte before and after (so a write that
    reached the grid by some other door is caught even if it never called ``swap_rows``)."""
    svc, store = _svc(store=_RefusingStore())
    before = copy.deepcopy(store._sheets)

    svc.daily_checks(**_SUPERVISOR)

    assert store._sheets == before, "a read must leave the sheet byte-for-byte as it found it"


def test_the_daily_checks_TOOL_writes_nothing_either_and_is_annotated_read_only():
    """The same property one layer up, where the host's gates actually read it: the annotation
    is what keeps a confirmation gate from ever needing to hold this call."""
    svc, store = _svc(store=_RefusingStore())
    mcp = build_server(svc)
    before = copy.deepcopy(store._sheets)

    async def run():
        out = _text(await mcp.call_tool("daily_checks", dict(_SUPERVISOR)))
        assert "NoSQL" in out and "ETL" in out
        tool = next(t for t in await mcp.list_tools() if t.name == "daily_checks")
        assert tool.annotations is not None and tool.annotations.readOnlyHint is True
    asyncio.run(run())

    assert store._sheets == before


# ── the composition is a composition: it re-defines nothing ──────────────────────────
def test_a_genuinely_overdue_deadline_is_invisible_to_this_vertical():
    """MEASURED, and written down because somebody will need it.

    ``check_deadlines`` filters ``last_class < today <= last_class + GRADE_GRACE_DAYS``
    (``service.py``), so a discipline whose last class was more than fourteen days ago is
    dropped at the source. It is not late here — it is ABSENT, and no composition on top can
    invent it. ``Estatistica`` ended five weeks before this fixture's today and appears in
    neither list."""
    svc, _ = _svc()
    dc = svc.daily_checks(**_SUPERVISOR)

    assert "Estatistica" not in [d.entry.subject for d in dc.deadlines]
    assert all(d.days_left >= 0 for d in dc.deadlines), "there is no overdue set to be negative"
    assert "Estatistica" not in _daily_checks_text(dc, **_status_args(svc))


def test_each_field_matches_the_predicate_that_owns_it():
    """Composition, stated as an equality rather than as a claim in a docstring: if any of the
    three ever drifts from its source, this fails instead of the next reader discovering it."""
    svc, _ = _svc()
    dc = svc.daily_checks(**_SUPERVISOR)

    week = svc.weekly_briefing(**_SUPERVISOR)
    assert dc.classes_today == [e for e in week if e.when == _TODAY]
    assert [d.entry for d in dc.deadlines] == svc.check_deadlines(**_SUPERVISOR)
    assert dc.ibope_today == svc.ibope_status(**_SUPERVISOR)


def test_one_unreadable_spreadsheet_is_reported_ONCE_not_three_times():
    """The arithmetic the composition had to get right.

    All three predicates aggregate the SAME spreadsheets, so handing the report to each of them
    would record one stale id three times and the footer would announce "3 spreadsheet(s) could
    not be read" over a single failure — a number a professor would reasonably read as three
    course spreadsheets being down."""
    from cogno_praxis.coordinator.types import ReadReport

    class _Broken(InMemorySpreadsheetStore):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.reads = 0

        def read_range(self, sheet_id, tab, a1_range):
            self.reads += 1
            raise RuntimeError("HTTP 404")

    svc, store = _svc(store=_Broken())
    report = ReadReport()
    svc.daily_checks(role="SUPERVISOR", identity_label="Sofia", report=report)

    # the three predicates really did all run — otherwise "reported once" would be trivially
    # true because only one of them ever looked
    assert store.reads == 3
    assert len(report.errors) == 1
    assert report.errors[0].sheet_key == "DSA"


# ── access is the same rule it is everywhere else ────────────────────────────────────
def test_a_professor_asking_about_a_colleague_is_refused_as_a_RULE():
    """No new access surface: the refusal comes from the first composed predicate and reaches
    the model as a limit, not as a breakdown."""
    svc, _ = _svc()
    mcp = build_server(svc)

    async def run():
        out = _text(await mcp.call_tool(
            "daily_checks", {"professor": "Ana", "role": "PROFESSOR", "identity_label": "Bruno"}))
        assert out.startswith("NOT PERMITTED:")
        assert "ERROR" not in out
    asyncio.run(run())


def test_a_professor_gets_their_OWN_day_with_professor_left_empty():
    svc, _ = _svc()
    dc = svc.daily_checks(role="PROFESSOR", identity_label="Ana")
    assert sorted(e.subject for e in dc.classes_today) == ["NoSQL", "Redes"]

"""What a professor asks for is what is COMING — and the month has to filter for that to work.

Two defects from the same live turn (2026-09-06, a conversation held on the 6th of September):

* the executor reads the NOUMENO's canonical-ENGLISH rewrite, so "aulas de setembro" reached the
  tool as ``month="September"``. ``_resolve_month`` knew only Portuguese, returned ``None``, and
  ``None`` means *no filter at all* — so the tool answered with the whole academic year. The
  judge rejected the answer for not showing September and the retry, which guessed ``"2026-09"``,
  passed: one full EGO+judge round trip bought by a missing dictionary row.
* even filtered, the year contains the PAST. An April opening workshop came back on a September
  conversation, because the tool returned everything and left the choice to the model. The
  default window is now ``[today, ∞)``; the past is a thing you ASK for.

Where "today" comes from is part of the fix and is asserted here too: the host's anchor, not the
process clock — see ``test_the_server_takes_today_from_the_host_anchor``.
"""

from __future__ import annotations

import asyncio
from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    ReadReport,
)
from cogno_praxis.coordinator.server import build_server
from cogno_praxis.coordinator.service import _resolve_month

_SID = "1QwErTy-UiOpAsDfGhJkLzXcVbNm45678"
_RULES = (f"SPREADSHEETS:\nTurma SMP_33 = {_SID}\n"
          'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
          'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
          'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n')
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]

# The year as the live sheet holds it: an April opening workshop, August classes already given,
# and September split across the 6th (today).
_YEAR = [
    ["14/04/2026", "Ter", "Ana", "Workshop de Abertura", "101"],
    ["20/08/2026", "Qui", "Ana", "Applied Statistics", "101"],
    ["27/08/2026", "Qui", "Ana", "Applied Statistics", "101"],
    ["03/09/2026", "Qui", "Ana", "Deep Learning", "101"],       # earlier this month
    ["06/09/2026", "Dom", "Ana", "Deep Learning", "101"],       # TODAY
    ["17/09/2026", "Qui", "Ana", "Deep Learning", "101"],
    ["08/10/2026", "Qui", "Ana", "Data Visualization", "101"],
]


def _svc(rows=None, *, today=date(2026, 9, 6)):
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria",
              [[""] * 5, [""] * 5, [""] * 5, list(_HEADER)] + [list(r) for r in (rows or _YEAR)])
    return CoordinatorService(store, cfg, today=lambda: today)


def _dates(entries):
    return [e.date_str for e in entries]


# ── the month, in either language ─────────────────────────────────────────────────────
def test_september_and_setembro_are_the_same_month():
    assert (_resolve_month("September") == _resolve_month("Sep") == _resolve_month("Sept")
            == _resolve_month("setembro") == _resolve_month("set") == _resolve_month("09")
            == _resolve_month("9") == (9, 0))
    assert _resolve_month("2026-09") == (9, 2026)


def test_every_english_month_resolves():
    names = ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]
    assert [_resolve_month(n) for n in names] == [(i, 0) for i in range(1, 13)]
    # abbreviations too — the rewrite is not guaranteed to spell it out
    assert [_resolve_month(a) for a in ("Jan", "Feb", "Mar", "Apr", "Aug", "Oct", "Dec")] == [
        (1, 0), (2, 0), (3, 0), (4, 0), (8, 0), (10, 0), (12, 0)]


def test_an_unknown_month_still_means_no_filter():
    # unchanged: the caller reads None as "skip month filtering", not as an error
    assert _resolve_month("nonsense") is None and _resolve_month("13") is None
    assert _resolve_month("") is None


def test_the_english_month_actually_filters_the_read():
    # The measured call, replayed: month="September" used to return the whole year.
    got = _svc().get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                        month="September")
    assert _dates(got) == ["06/09/2026", "17/09/2026"]
    assert "14/04/2026" not in _dates(got)          # the April workshop the owner was shown


# ── the window: today onward, unless asked ────────────────────────────────────────────
def test_nothing_before_today_by_default():
    got = _svc().get_professor_schedule(role="SUPERVISOR", identity_label="Sofia")
    assert _dates(got) == ["06/09/2026", "17/09/2026", "08/10/2026"]


def test_a_class_earlier_today_is_still_today():
    # Granularity is the DAY, deliberately: "what do I have today", asked at 3pm, must not
    # answer an empty list because the 8am class is behind us.
    got = _svc().get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                        month="September")
    assert "06/09/2026" in _dates(got)


def test_the_month_in_progress_starts_at_today_and_says_so():
    report = ReadReport()
    got = _svc().get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                        month="September", report=report)
    assert "03/09/2026" not in _dates(got)         # earlier this month, cut
    assert report.hidden_past == 1                 # and COUNTED, so the reply can say so


def test_a_month_already_over_is_itself_the_request():
    # "minhas aulas de agosto" on the 6th of September: naming a month that has ENDED is asking
    # for the past. No flag needed, and nothing was hidden — so nothing to announce.
    report = ReadReport()
    got = _svc().get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                        month="agosto", report=report)
    assert _dates(got) == ["20/08/2026", "27/08/2026"]
    assert report.hidden_past == 0


def test_include_past_shows_the_whole_year():
    got = _svc().get_professor_schedule(role="SUPERVISOR", identity_label="Sofia",
                                        include_past=True)
    assert len(got) == len(_YEAR) and "14/04/2026" in _dates(got)


def test_the_note_appears_only_when_something_was_actually_cut():
    # The twin for the conditional footer. A permanent "showing from today onward" teaches the
    # reader that things are always being withheld, including on the turns where nothing was.
    mcp = build_server(_svc())

    async def run(args):
        res = await mcp.call_tool("get_professor_schedule",
                                  {"role": "SUPERVISOR", "identity_label": "Sofia", **args})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")

    cut = asyncio.run(run({"month": "September"}))
    assert "Showing from today onward" in cut and "1 earlier class" in cut
    nothing_cut = asyncio.run(run({"month": "October"}))
    assert "Showing from today onward" not in nothing_cut
    asked_for = asyncio.run(run({"include_past": True}))
    assert "Showing from today onward" not in asked_for and "14/04/2026" in asked_for


def test_an_undated_row_is_never_hidden_by_the_window():
    # The filter refuses to hide what it cannot date: an unparseable date is not "the past".
    svc = _svc([["", "", "Ana", "Redes", "101"],
                ["14/04/2026", "Ter", "Ana", "Workshop", "101"]])
    got = svc.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia")
    assert [e.subject for e in got] == ["Redes"]


def test_the_weekly_briefing_needs_no_cut_of_its_own():
    # Already [today, today+7] by construction — asserted so nobody stacks a second cut on it.
    got = _svc().weekly_briefing(role="SUPERVISOR", identity_label="Sofia")
    assert _dates(got) == ["06/09/2026"]


# ── where "today" comes from ──────────────────────────────────────────────────────────
def test_the_server_takes_today_from_the_host_anchor(monkeypatch):
    # NOT the process clock. This server runs as a stdio subprocess of a host whose container
    # boots in UTC, so between 21:00 and midnight in São Paulo the process already believes it
    # is tomorrow — and a class happening TODAY would silently vanish from a list now cut at
    # "today onward". The host has been stamping COGNO_COORDINATOR_TODAY since the vertical
    # shipped (the same date it renders as [HOJE]); this server was the only one not reading it.
    from cogno_praxis.coordinator import server as srv

    monkeypatch.setenv("COGNO_COORDINATOR_RULES", _RULES)
    monkeypatch.setenv("COGNO_COORDINATOR_TODAY", "2026-09-06")
    assert srv._demo_service()._today() == date(2026, 9, 6)

    monkeypatch.delenv("COGNO_COORDINATOR_TODAY")
    assert srv._demo_service()._today() == date.today()      # unset → the real date, as before

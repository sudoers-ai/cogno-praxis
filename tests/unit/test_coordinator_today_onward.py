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
    # THE PROPERTY THIS TEST OWNS: nothing before today. April and August are the rows that used
    # to come back on a September conversation, and they are the assertion.
    assert not [d for d in _dates(got) if d.endswith("/04/2026") or d.endswith("/08/2026")]
    assert _dates(got)[0] == "06/09/2026"             # a class TODAY still counts as today
    # The far end belongs to a different default and to a different file
    # (``test_coordinator_listing.py``): with no period named the read now stops ~30 days out,
    # which is why 08/10/2026 is no longer here. Asserted, not merely tolerated — a window with
    # one end pinned and the other left loose is how the loose end drifts unnoticed.
    assert _dates(got) == ["06/09/2026", "17/09/2026"]


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
    assert "covers today onward" in cut
    nothing_cut = asyncio.run(run({"month": "October"}))
    assert "covers today onward" not in nothing_cut
    asked_for = asyncio.run(run({"include_past": True}))
    # the April workshop, in the listing's own shape now
    assert "covers today onward" not in asked_for
    assert "**Abril de 2026**" in asked_for and "- 14/04 ·" in asked_for


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


# ── the footer has ONE string and TWO readers ────────────────────────────────────────
# `ToolResult.output` is a single field, and the SUPEREGO judge is handed the same bytes the
# executor gets. So a note written to offer the executor a next step is also evidence in a
# completeness grading. Measured live on 2026-09-06: the old wording counted what the window had
# excluded ("N earlier class(es) ... were not listed"), and three of the four occurrences of one
# ordinary follow-up question were rejected by the judge quoting exactly that — one critique in
# so many words, "included a note about omitted earlier classes ... which could be seen as
# incomplete". Every rejection cost a correction round, and the loop then dragged the executor
# into answering about the past instead of the question asked.
#
# The rule these tests pin: the WINDOW line carries one BIT and an argument name; the PARTIAL
# RESULT line, which reports a genuine incompleteness, keeps its COUNT. A rule that flattened
# both would buy this fix by blinding the reader to a spreadsheet that failed to load.


def _past_rows(n: int) -> list[list[str]]:
    """``n`` classes already given (August, before the 6th) plus one still to come."""
    given = [[f"{d:02d}/08/2026", "Qui", "Ana", "Applied Statistics", "101"]
             for d in range(1, n + 1)]
    return given + [["17/09/2026", "Qui", "Ana", "Deep Learning", "101"]]


def _footer(out: str) -> str:
    """Whatever ``_fmt_report`` appended after the listing (``""`` when it stayed silent)."""
    return out.split("\n\n", 1)[1] if "\n\n" in out else ""


def _read(svc, **args) -> str:
    mcp = build_server(svc)

    async def run() -> str:
        res = await mcp.call_tool("get_professor_schedule",
                                  {"role": "SUPERVISOR", "identity_label": "Sofia", **args})
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")
    return asyncio.run(run())


def test_the_window_note_carries_a_bit_not_a_measurement():
    """THE property. One class outside the window and sixteen produce the SAME footer.

    A count is only actionable as a deficit, and the reader that acts on a deficit is the one
    grading completeness. Restoring the number is the mutation, and it kills this test."""
    one, sixteen = _svc(_past_rows(1)), _svc(_past_rows(16))

    # Not vacuous: the two reads really do cut different amounts.
    r1, r16 = ReadReport(), ReadReport()
    one.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia", report=r1)
    sixteen.get_professor_schedule(role="SUPERVISOR", identity_label="Sofia", report=r16)
    assert (r1.hidden_past, r16.hidden_past) == (1, 16)

    foot_one, foot_sixteen = _footer(_read(one)), _footer(_read(sixteen))
    assert foot_one, "the note must still be there — silence would hide the window, not the count"
    assert foot_one == foot_sixteen


def test_the_note_still_hands_the_executor_its_next_step():
    """The offer survives the loss of the count: the line names the ARGUMENT that widens the
    window. That is what only the executor can act on — the judge has no tools."""
    foot = _footer(_read(_svc(_past_rows(3))))
    assert "include_past=true" in foot


def test_a_real_incompleteness_still_counts_and_the_count_still_moves():
    """The over-tightening probe. The window line stopped quantifying; the PARTIAL RESULT line
    must NOT, because a spreadsheet that failed to load really does leave the answer short and
    the reader has to know how much. Two broken sheets must not read like one."""
    one_broken = _footer(_read(_flaky(broken=(_SID_B,))))
    two_broken = _footer(_read(_flaky(broken=(_SID_B, _SID_C))))
    assert "1 spreadsheet(s) could not be read" in one_broken
    assert "2 spreadsheet(s) could not be read" in two_broken
    assert one_broken != two_broken


def test_the_window_line_does_not_change_when_a_spreadsheet_fails():
    """The two lines stay separate facts. The window line never absorbs the read failure — it
    makes no claim about completeness at all, precisely so it cannot contradict the line below
    it when both are earned by the same read."""
    clean = _window_line(_footer(_read(_flaky(broken=()))))
    broken = _window_line(_footer(_read(_flaky(broken=(_SID_B,)))))
    assert clean and clean == broken
    assert "PARTIAL RESULT" in _footer(_read(_flaky(broken=(_SID_B,))))


def _window_line(footer: str) -> str:
    return next((ln for ln in footer.splitlines() if "covers today onward" in ln), "")


_SID_B = "1AbCdEfGhIjKlMnOpQrStUvWxYz01234567"
_SID_C = "1ZyXwVuTsRqPoNmLkJiHgFeDcBa98765432"


class _Boom(RuntimeError):
    pass


def _flaky(*, broken: tuple[str, ...], today=date(2026, 9, 6)):
    """Two spreadsheets, each with one past and one future class; ``broken`` ids raise on read.

    The past rows guarantee the WINDOW line is earned in every variant, so the two footer lines
    are always compared with both of them present."""
    rules = (f"SPREADSHEETS:\nTurma A_01 = {_SID_B}\nTurma B_02 = {_SID_C}\n"
             'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
             'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
             'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n')

    class _FlakyStore(InMemorySpreadsheetStore):
        def read_range(self, sheet_id, tab, a1_range):
            if sheet_id in broken:
                raise _Boom("HTTP 404")
            return super().read_range(sheet_id, tab, a1_range)

    store = _FlakyStore()
    rows = [["03/08/2026", "Seg", "Ana", "Applied Statistics", "101"],
            ["17/09/2026", "Qui", "Ana", "Deep Learning", "101"]]
    for sid in (_SID_B, _SID_C):
        store.put(sid, "Secretaria",
                  [[""] * 5, [""] * 5, [""] * 5, list(_HEADER)] + [list(r) for r in rows])
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: today)


def test_the_prompts_ask_for_the_window_and_not_for_a_shortfall():
    """The prompt half, pinned by PRESENCE — and this test does not pretend that is obedience.

    It is worth pinning anyway, and the live measurement says why. The judge prompt of the
    2026-09-06 runs already carried, verbatim, "A reply that shows no past classes is CORRECT,
    not incomplete" — and the judge rejected the turn three times over anyway, quoting the tool's
    own note back. The prose lost to the data, which is why the fix above is in the DATA. What
    these lines buy is narrower: the voice is no longer TOLD to copy a shortfall into the reply,
    where the grader reads it a second time.

    The twin is in the same assertions: the unreadable-spreadsheet instruction, which reports a
    REAL incompleteness, must survive untouched."""
    from pathlib import Path
    prompts = Path(__import__("cogno_praxis").__file__).resolve().parent / "coordinator" / "prompts"
    voice = (prompts / "voice.txt").read_text(encoding="utf-8")
    system = (prompts / "system.txt").read_text(encoding="utf-8")

    # the window is said, the deficit is not
    assert "Say the WINDOW, never a deficit" in voice
    assert 'were "not listed"' in voice
    assert "OFFER the past; do not report a shortfall" in system
    # the offer survives in both
    assert "quer ver as anteriores?" in voice
    assert "include_past=true` ONLY when the user explicitly asks" in system
    # the twin: a real incompleteness is still announced, and still named
    assert "could not read, give the classes it DID read and name the" in voice
    # The judge is told the same thing, and now about BOTH ends of the window. The sentence
    # changed wording when the forward end arrived; what it may never do is call either end an
    # incompleteness, which is what these two halves pin.
    limits = (prompts / "limits.txt").read_text(encoding="utf-8")
    assert "A reply carrying no past classes is CORRECT" in limits
    assert "Claiming the list is partial, or counting what lies outside the window, is not." in limits

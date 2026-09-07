"""The calendar proposal: a question grounded in the read, and a window that is the month asked for.

Two defects, measured on the same live conversation on 2026-09-06, and only ONE of them lives here.

**The proposal.** A professor asked for their September classes to be mailed to them, said yes,
and was answered *"Confirmo: esta ação — 2026-09. Posso seguir?"* — a machine argument printed at
a person. It reads like that because the send is HELD before it runs: the confirmation gate stops
the call by NAME, so the skill never reads, and a skill that never read has nothing to say. A gate
cannot ask the skill's question for it. A READ can, because nothing holds a read — which is what
``preview_schedule_to_calendar`` is, and what these tests are about: every number in its sentence
came out of the read, and a number it does not have never appears at all.

**The window.** The same turn was answered with OCTOBER classes for a September request, and the
window is NOT where that happened — it is pinned here so the next reader does not have to
re-measure it. The trace of that turn shows the executor called
``get_professor_schedule(month="2026-09")`` and the tool returned exactly the one September class
there was; the month changed later, in the voicer, over a conversation history full of October.
Nothing in this file can fix that, and nothing in this file pretends to. What it can do is make
"the window returned the wrong month" a hypothesis somebody has to disprove rather than assume:
the three positions below are the ones that separate a correct boundary from one that only works
mid-month.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
    RecordingCalendarSender,
    month_label,
)
from cogno_praxis.coordinator.server import _calendar_proposal_text, build_server
from cogno_praxis.coordinator.types import ReadReport

_RULES = (
    "SPREADSHEETS:\nDE_09=1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A1:E200"\n'
    'TAB_PROFESSORS: "Info"\nRANGE_PROFESSORS: "A1:C50"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
    'FIXED_COLUMNS: "Data, Dia"\n'
)
_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
_PROFS = [["Professor", "e-mail"], ["Ana", "ana@escola.test"]]

# One class in the month asked for and several in the NEXT one — the live shape, because that is
# the shape in which naming the wrong month is invisible: both lists are true, only one is the
# answer.
_ROWS = [
    ["25/08/2026", "Ter", "Ana", "Bancos de Dados", "101"],
    ["01/09/2026", "Ter", "Ana", "NoSQL", "101"],
    ["08/09/2026", "Ter", "Ana", "NoSQL", "101"],
    ["29/09/2026", "Ter", "Ana", "NoSQL", "101"],
    ["05/10/2026", "Seg", "Ana", "Machine Learning", "102"],
    ["14/10/2026", "Qua", "Ana", "Machine Learning", "102"],
    ["07/09/2027", "Ter", "Ana", "NoSQL", "101"],
]


def _service(rows=None, *, today=date(2026, 8, 31), profs=None):
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [list(_HEADER)] + [list(r) for r in (rows or _ROWS)])
    store.put(_SID, "Info", [list(r) for r in (profs if profs is not None else _PROFS)])
    return CoordinatorService(store, cfg, today=lambda: today)


def _proposal(svc, sender=None, **kw):
    kw.setdefault("identity_label", "Ana")
    kw.setdefault("role", "EMPLOYEE")
    return svc.preview_schedule_to_calendar(
        sender=sender if sender is not None else RecordingCalendarSender(), **kw)


def _text(res):
    return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")


def _proposal_line(text: str) -> str:
    """The ONE line that carries the three facts — the atom the voicer is asked to copy whole.

    Read by marker, not by position: a line that has to be found by counting is a line the next
    edit moves. ``PROPOSAL:`` is to this call what ``SENT:`` is to the send.
    """
    hits = [ln for ln in text.splitlines() if ln.startswith("PROPOSAL:")]
    assert len(hits) == 1, f"expected exactly one PROPOSAL: line, got {len(hits)}"
    return hits[0]


def _server(rows=None, *, today=date(2026, 8, 31), sender=None, profs=None):
    return build_server(_service(rows, today=today, profs=profs),
                        sender=sender if sender is not None else RecordingCalendarSender(),
                        tz_name="America/Sao_Paulo")


# ── the proposal says what the skill READ ────────────────────────────────────────────

def test_the_proposal_names_the_count_the_period_and_the_destination():
    """The three facts the machine sentence had none of, each read off the proposal object.

    Asserted as three separate presences rather than one whole string on purpose: a renderer
    that drops the count keeps the sentence grammatical, and a whole-string comparison would go
    red for a reworded connective while a missing number slipped through under it.
    """
    svc = _service()
    p = _proposal(svc, month="2026-09")
    assert p.count == 3 and p.recipient == "ana@escola.test" and p.period == "September 2026"

    text = _calendar_proposal_text(p)
    assert "3 class(es)" in text                     # the COUNT, from the events actually built
    assert "of September 2026" in text               # the PERIOD the filter actually applied
    assert "ana@escola.test" in text                 # the DESTINATION the send would resolve
    # and the marker every downstream layer reads as proof an e-mail left is NOT there
    assert not text.startswith("SENT:") and "SENT:" not in text
    assert text.startswith("NOT SENT")


def test_the_three_facts_live_on_ONE_line_adjacent():
    """The anti-deformation property, and it is the one this text most needs.

    Nothing here reaches the contact directly — a voicer rewrites it first, and that rewrite is
    exactly where the month was lost on 2026-09-06: the executor's own draft said "1 aula de
    setembro / 08/09/2026" and the reply that went out announced OCTOBER, taken from a listing
    six turns earlier. A count in one sentence and a period in another are two things to
    re-attach, and a re-attachment can go to the wrong list; glued into one short line they are
    one thing to copy.

    So the assertion is ADJACENCY, not mere presence: all three on the same line, in order, with
    the period touching the count it belongs to.
    """
    line = _proposal_line(_calendar_proposal_text(_proposal(_service(), month="2026-09")))
    assert line == "PROPOSAL: 3 class(es) of September 2026 → ana@escola.test"
    # the count and its period are one token run, not two facts a rewrite has to pair up again
    assert "3 class(es) of September 2026" in line


def test_the_proposal_lists_the_very_classes_that_would_go():
    """A count a person cannot check is a count they have to trust. The lines are the check."""
    text = _calendar_proposal_text(_proposal(_service(), month="2026-09"))
    for day in ("01/09/2026", "08/09/2026", "29/09/2026"):
        assert day in text
    assert "05/10/2026" not in text and "25/08/2026" not in text


def test_the_proposal_claims_no_period_when_the_read_filtered_by_none():
    """The half that must NOT be filled in.

    A request with no month filtered by no month, so there is no period to name and the sentence
    says none — it still says how many and where. The alternative is echoing the caller's own
    string back as though it were a fact about the read, which is exactly how a listing that
    covers several months gets proposed as one of them.
    """
    p = _proposal(_service(), month="")
    assert p.period == ""
    # the count runs straight into the destination: there is no period between them to claim
    assert _proposal_line(_calendar_proposal_text(p)) == "PROPOSAL: 6 class(es) → ana@escola.test"


def test_a_month_the_resolver_could_not_read_is_not_repeated_back_as_one():
    """«as aulas DE outubro» — the word the turma filter already learned to leave alone.

    ``de`` is a preposition, the month resolver cannot read it, and NO month filter was applied.
    A proposal that echoed it would name a period the read never used; this one names none. The
    count is therefore the unfiltered count, which is the truth of what would be sent.
    """
    p = _proposal(_service(), month="de")
    assert p.period == "" and p.count == 6           # everything from 31/08 onward, unfiltered
    line = _proposal_line(_calendar_proposal_text(p))
    assert line == "PROPOSAL: 6 class(es) → ana@escola.test" and " of " not in line


def test_a_month_named_without_a_year_is_not_given_one():
    """"setembro" filtered September of ANY year, so the words say September and no year.

    Stating 2026 there would be a fact the read did not establish — the filter matched a 2027
    class too, and the count says so.
    """
    p = _proposal(_service(), month="setembro")
    assert p.period == "September" and p.count == 4  # three in 2026 + the one in 2027
    text = _calendar_proposal_text(p)
    assert _proposal_line(text) == "PROPOSAL: 4 class(es) of September → ana@escola.test"
    assert "September 2026" not in text              # a year the read never established
    assert "07/09/2027" in text


@pytest.mark.parametrize("raw,expected", [
    ("2026-09", "September 2026"), ("2026-1", ""), ("09", "September"), ("9", "September"),
    ("setembro", "September"), ("SETEMBRO", "September"), ("September", "September"),
    ("", ""), ("de", ""), ("13", ""), ("outubro", "October"),
])
def test_the_label_is_the_filter_that_ran_never_the_string_that_arrived(raw, expected):
    assert month_label(raw) == expected


def test_the_proposal_counts_the_events_that_would_be_created_not_the_rows_read():
    """A row this system cannot date produces no calendar entry, so it is not in the count —
    it is named separately. Announcing four and mailing three is the same defect as announcing
    a send that did not happen."""
    rows = list(_ROWS) + [["sem data", "Ter", "Ana", "NoSQL", "101"]]
    p = _proposal(_service(rows), month="")
    assert p.count == 6 and p.dropped == 1
    text = _calendar_proposal_text(p)
    assert "6 class(es)" in text
    assert "1 class(es) carry a date this system could not read" in text


# ── the proposal PROPOSES: nothing leaves ────────────────────────────────────────────

def test_the_preview_sends_nothing():
    """The promise the whole two-step rests on, performed rather than believed."""
    sender = RecordingCalendarSender()
    svc = _service()
    _proposal(svc, sender=sender, month="2026-09")
    assert sender.sent == []


def test_the_preview_refuses_exactly_where_the_send_refuses():
    """One read behind both, so the sentence a professor agrees to describes the send that
    would actually happen. Each of these is a path on which no e-mail can leave, and a preview
    that proposed one anyway would be a promise nobody can keep."""
    sender = RecordingCalendarSender()

    # no classes in the window
    with pytest.raises(CoordinatorError, match="nothing to put in a calendar"):
        _proposal(_service(), sender=sender, month="2026-01")
    # no address on file
    with pytest.raises(CoordinatorError, match="no e-mail address on file"):
        _proposal(_service(profs=[["Professor", "e-mail"]]), sender=sender, month="2026-09")
    # this deployment has no mail server at all
    with pytest.raises(CoordinatorError, match="No e-mail is configured"):
        _service().preview_schedule_to_calendar(sender=None, identity_label="Ana",
                                                role="EMPLOYEE", month="2026-09")
    # a professor asking about a colleague is refused by the same scoping the send obeys
    from cogno_praxis.coordinator import CoordinatorAccessError
    rows = list(_ROWS) + [["08/09/2026", "Ter", "Bruno", "Cálculo", "104"]]
    with pytest.raises(CoordinatorAccessError):
        _proposal(_service(rows), sender=sender, professor="Bruno", month="2026-09")
    assert sender.sent == []


def test_the_preview_and_the_send_agree_on_the_count_and_the_address():
    """The pair, on the same service and the same arguments. If these can drift apart, the
    proposal is a second opinion rather than a description."""
    sender = RecordingCalendarSender()
    svc = _service()
    p = _proposal(svc, sender=sender, month="2026-09")
    count, to, dropped = asyncio.run(svc.send_schedule_to_calendar(
        sender=sender, identity_label="Ana", role="EMPLOYEE", month="2026-09"))
    assert (count, to, dropped) == (p.count, p.recipient, p.dropped)


# ── at the tool surface ──────────────────────────────────────────────────────────────

def test_the_preview_tool_is_read_only_so_no_gate_holds_it_before_it_reads():
    """The annotation IS the mechanism here, not metadata about it.

    ``send_schedule_to_calendar`` is stopped by NAME before it runs — by its own
    ``destructiveHint`` and, on a host that gates every write, regardless of it — so it can
    never be the thing that reads and asks. A read is held by nobody. If this ever flips to
    ``readOnlyHint=False`` the proposal stops being reachable and the contact is back to being
    shown an argument.
    """
    async def run():
        tools = {t.name: t.annotations for t in await _server().list_tools()}
        assert "preview_schedule_to_calendar" in tools
        assert tools["preview_schedule_to_calendar"].readOnlyHint is True
        assert getattr(tools["preview_schedule_to_calendar"], "destructiveHint", None) is not True
        # and its counterpart is still held: this adds a read, it does not open a write
        assert tools["send_schedule_to_calendar"].readOnlyHint is False
        assert tools["send_schedule_to_calendar"].destructiveHint is True
    asyncio.run(run())


def test_the_preview_tool_answers_with_the_grounded_sentence():
    sender = RecordingCalendarSender()

    async def run():
        out = _text(await _server(sender=sender).call_tool(
            "preview_schedule_to_calendar",
            {"role": "EMPLOYEE", "identity_label": "Ana", "month": "2026-09"}))
        assert out.startswith("NOT SENT")
        assert _proposal_line(out) == "PROPOSAL: 3 class(es) of September 2026 → ana@escola.test"
        assert "08/09/2026" in out
        assert sender.sent == []
    asyncio.run(run())


def test_a_refused_preview_reaches_the_model_as_a_LIMIT_not_a_breakdown():
    """A read returns its refusal as text (it is read-only, so nothing can be mis-stamped as a
    write) — and the WORD matters: a model handed "ERROR" reports a malfunction to a professor
    whose only problem is that they asked about a colleague."""
    rows = list(_ROWS) + [["08/09/2026", "Ter", "Bruno", "Cálculo", "104"]]

    async def run():
        out = _text(await _server(rows).call_tool(
            "preview_schedule_to_calendar",
            {"role": "EMPLOYEE", "identity_label": "Ana", "professor": "Bruno"}))
        assert out.startswith("NOT PERMITTED")
        assert "access rule working as intended" in out
    asyncio.run(run())


def test_the_partial_read_footer_travels_on_the_proposal_too():
    """A professor being asked to agree to "3 classes" has to be told that a course spreadsheet
    did not load — otherwise they agree to a calendar with a hole in it."""
    rows = [["01/09/2026", "Ter", "Ana", "NoSQL", "101"]]
    cfg = CoordinatorConfig(_RULES.replace(
        "SPREADSHEETS:\n",
        "SPREADSHEETS:\nOUTRA = 1PoIuYtReWqLkJhGfDsAmNbVcXz0123456789AbCdEfG\n"))
    inner = InMemorySpreadsheetStore()
    inner.put(_SID, "Secretaria", [list(_HEADER)] + rows)
    inner.put(_SID, "Info", [list(r) for r in _PROFS])

    class _HalfBroken:
        def read_range(self, sheet_id, tab, a1_range):
            if sheet_id.startswith("1PoIuYt"):
                raise RuntimeError("HTTP 404")
            return inner.read_range(sheet_id, tab, a1_range)

        def swap_rows(self, *a, **k):                  # pragma: no cover - unused here
            raise NotImplementedError

    svc = CoordinatorService(_HalfBroken(), cfg, today=lambda: date(2026, 8, 31))
    report = ReadReport()
    p = svc.preview_schedule_to_calendar(sender=RecordingCalendarSender(), identity_label="Ana",
                                         role="EMPLOYEE", month="2026-09", report=report)
    text = _calendar_proposal_text(p, report)
    assert "PARTIAL RESULT" in text and "OUTRA" in text


# ── the window: September is September in all three positions ────────────────────────

@pytest.mark.parametrize("today,expected", [
    # the day before the month opens — nothing may be cut, the whole month is ahead
    (date(2026, 8, 31), ["01/09/2026", "08/09/2026", "29/09/2026"]),
    # mid-month — the today-onward default cuts what is already past, and ONLY that
    (date(2026, 9, 15), ["29/09/2026"]),
    # the day after it closed — naming a month that has ENDED is the request for the past, so
    # the cut steps aside and the whole month comes back
    (date(2026, 10, 1), ["01/09/2026", "08/09/2026", "29/09/2026"]),
])
def test_the_september_window_is_september_from_either_side_of_it(today, expected):
    """The three positions that separate a correct boundary from one that only works mid-month.

    August is out of all three and so is October — which is the assertion that matters, because
    the live turn this was measured against answered a September request with October classes.
    It did not happen here: the trace shows the tool was called with ``month="2026-09"`` and
    returned exactly the September rows. The month changed downstream of the read.
    """
    report = ReadReport()
    got = _service(today=today).get_professor_schedule(
        identity_label="Ana", role="EMPLOYEE", month="2026-09", report=report)
    assert [e.date_str for e in got] == expected
    assert all(e.when.month == 9 and e.when.year == 2026 for e in got)


def test_the_window_reports_what_it_cut_only_when_it_cut_something():
    """``hidden_past`` is the difference between "you have one class left in September" and
    "you have one class in September" — a professor mid-month needs to know which."""
    for today, hidden in ((date(2026, 8, 31), 0), (date(2026, 9, 15), 2), (date(2026, 10, 1), 0)):
        report = ReadReport()
        _service(today=today).get_professor_schedule(
            identity_label="Ana", role="EMPLOYEE", month="2026-09", report=report)
        assert report.hidden_past == hidden, today


# ── the bound the two readings of "is this a month" did not share ────────────────────

@pytest.mark.parametrize("raw", ["2026-13", "2026-00", "2026-99"])
def test_a_YYYY_MM_outside_1_to_12_is_not_a_month_either(raw):
    """One predicate, two branches, and only one of them had the bound.

    ``"13"`` has always answered "not a month" and applied no filter. ``"2026-13"`` answered
    ``(13, 2026)``, matched no class, and then handed month 13 to ``calendar.monthrange`` —
    which raises ``IllegalMonthError``, not a ``CoordinatorError``, so it left this vertical as
    a crash instead of as an answer. Measured on ``origin/main`` (6d887ec) for ``"2026-13"`` and
    ``"2026-00"`` alike. The two branches now read the same range, and the proposal that sits on
    top of them claims no period for either.
    """
    assert month_label(raw) == ""
    report = ReadReport()
    got = _service().get_professor_schedule(identity_label="Ana", role="EMPLOYEE",
                                            month=raw, report=report)
    # No filter ran, so the answer is the read's own no-period window — an answer, not an
    # exception. That window now has a forward end as well as a back one, and asserting it here
    # is the point rather than a concession: "2026-13" must behave EXACTLY like month="", and a
    # test that pinned the old unbounded tail would have gone on passing while the two drifted
    # apart. The equality below says the same thing without naming a horizon it does not own.
    assert [e.date_str for e in got] == [
        e.date_str for e in _service().get_professor_schedule(identity_label="Ana",
                                                              role="EMPLOYEE", month="")]
    assert [e.date_str for e in got] == ["01/09/2026", "08/09/2026", "29/09/2026"]
    assert " of " not in _proposal_line(_calendar_proposal_text(_proposal(_service(), month=raw)))

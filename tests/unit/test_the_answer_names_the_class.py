"""The return leg of a class invitation — and the two ways it is allowed to record nothing.

The invitation half already shipped: ``RSVP=TRUE`` on the exported calendar, so a professor's
client offers accept and decline (``test_the_invitation_asks_for_an_answer.py``). What that file
said was missing is what this one builds: *"there is no ... column anywhere recording an
acceptance. The professor can now decline every class and the schedule will not move."*

**What links an answer to a class here is the DATE the answer names, and that is a decision, not
a convenience.** There is no message id to hang it on. The invitation leaves as a calendar
e-mail and the answer arrives as a chat turn; the vertical is a fresh subprocess every turn, so
it cannot remember what it asked; and neither WhatsApp adapter carries a quoted-message
reference as far as the pipeline. So the link is the one ``confirm_swap`` has always used to
write on this data — ``(professor, date)`` resolved against the sheet, with the ambiguity checks
that come with it — and it arrives as a TYPED TOOL ARGUMENT rather than as a sentence somebody
parsed. A caller with no date has nothing to record, and says so.

**The two refusals below are the feature, not its edges.** A bare "sim" and a date matching two
classes both leave the invitation PENDING, because the cost of the other answer is a professor
recorded as attending a class they never agreed to, and a room that is empty — or a room that is
not — because of it. Pending is a real answer; guessing is not.

**And a repeated answer is one state.** Two "sim" to the same invitation write once; the second
call reports that nothing changed, in the words the SUPEREGO's NOTHING-TO-DO clause already
knows how to read, so a correction loop does not go hunting for a change to make. Changing an
earlier answer IS allowed and is written — a professor who accepted and then cannot come has to
be able to say so — but a value this system did not write is never overwritten, because a note
somebody left in their own spreadsheet is not this feature's to destroy.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    RSVP_ACCEPTED,
    RSVP_DECLINED,
    RSVP_PENDING,
    VALID_RSVP,
    CoordinatorAccessError,
    CoordinatorConfig,
    CoordinatorConfigError,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
    build_server,
    label_for,
    parse_answer,
    state_of,
)

_SID = "1QwErTy-UiOpAsDfGhJkLzXcVbNm45678"
_SID2 = "1ZxCvBn-MlKjHgFdSaPoIuYtReWq98765"
_RULES = (f"SPREADSHEETS:\nTurma DE_09 = {_SID}\nTurma DSA_33 = {_SID2}\n"
          'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
          'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
          'COLUMN_STATUS: "Status"\n'
          'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n')
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Status"]
_TODAY = date(2026, 9, 6)
_STATUS = 4                       # where "Status" sits in _HEADER — asserted, never assumed


class _CountingStore(InMemorySpreadsheetStore):
    """The store, plus a count of what it was actually asked to WRITE.

    The count is the discriminating half of the idempotency twin: a second answer that produces
    the same cell VALUE is indistinguishable, by reading the grid, from a second answer that
    wrote the same word again — and "one state, not two" is a claim about the write, not about
    the word that happens to be sitting there afterwards."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.writes: list[tuple[str, str, int, int, str]] = []

    def write_cell(self, sheet_id, tab, a1_range, row, col, value):  # type: ignore[override]
        self.writes.append((sheet_id, tab, row, col, value))
        super().write_cell(sheet_id, tab, a1_range, row, col, value)


def _grid(rows: list[list[str]], header: list[str] = _HEADER) -> list[list[str]]:
    """The sheet as the tenant keeps it: three metadata rows, then the header, then the classes
    — which is what ``RANGE_SCHEDULE: A4:...`` is skipping past."""
    return [[""] * len(header)] * 3 + [list(header)] + [list(r) for r in rows]


def _svc(rows=None, *, rules=_RULES, header=_HEADER, second=None):
    cfg = CoordinatorConfig(rules)
    store = _CountingStore()
    store.put(_SID, "Secretaria", _grid(rows if rows is not None else _ONE, header))
    if second is not None:
        store.put(_SID2, "Secretaria", _grid(second, header))
    return CoordinatorService(store, cfg, today=lambda: _TODAY), store


#: One class, unanswered — the ordinary starting state of an invitation.
_ONE = [["10/09/2026", "Qui", "Ana", "Redes", ""]]

#: The same date, twice, in two different class groups. A professor really does teach two
#: groups on one day, and this is the row pair that makes "aceita a aula de 10/09" ambiguous.
_TWO_SAME_DAY = [["10/09/2026", "Qui", "Ana", "Redes", ""]]
_TWO_SAME_DAY_OTHER = [["10/09/2026", "Qui", "Ana", "Bancos NoSQL", ""]]

#: The same day and month in two academic years — what a bare "10/09" cannot choose between.
_TWO_YEARS = [["10/09/2026", "Qui", "Ana", "Redes", ""],
              ["10/09/2027", "Sex", "Ana", "Redes", ""]]


# ── the vocabulary: three states, and only two of them can ever be written ───────────
def test_pending_is_the_absence_of_an_answer_and_is_never_written():
    """``PENDING`` has no label, because it is not a value anybody stores.

    That is what makes it impossible to fabricate: a class reads pending when the cell is empty
    or holds the tenant's own ordinary status, and there is no path that writes the word. Every
    refusal in this file therefore lands on a state nothing had to produce."""
    assert VALID_RSVP == (RSVP_PENDING, RSVP_ACCEPTED, RSVP_DECLINED)
    assert state_of("", accepted="Aceita", declined="Recusada") == RSVP_PENDING
    assert state_of("Confirmado", accepted="Aceita", declined="Recusada",
                    ordinary=("Confirmado",)) == RSVP_PENDING
    assert state_of("Aceita", accepted="Aceita", declined="Recusada") == RSVP_ACCEPTED
    # A word this system did not write is NOT pending and NOT an answer: it is unreadable, and
    # the Optional is what a caller reads to stop instead of overwriting somebody's note.
    assert state_of("Proposta enviada", accepted="Aceita", declined="Recusada") is None
    # ...and the other direction: PENDING has no word to write, which is the whole reason it
    # cannot be forged. An empty cell IS the state.
    assert label_for(RSVP_PENDING, accepted="Aceita", declined="Recusada") == ""
    assert label_for(RSVP_ACCEPTED, accepted="Aceita", declined="Recusada") == "Aceita"
    assert label_for(RSVP_DECLINED, accepted="Aceita", declined="Recusada") == "Recusada"


def test_the_answer_field_is_closed_and_a_bare_yes_is_not_in_it():
    """``parse_answer`` maps exactly two tokens and refuses the rest with ``""``.

    No fuzzy match, no Portuguese alias, no "starts with s". This is the one field where being
    approximately right becomes a commitment, and the only safe way to be unsure is to say so —
    which is also why the language detector never gets a vote: this house has measured ``"sim"``
    read as Finnish and ``"ok"`` as Slovak, and a state that hung off that would be born wrong."""
    assert parse_answer("ACCEPTED") == RSVP_ACCEPTED
    assert parse_answer("declined") == RSVP_DECLINED
    for not_an_answer in ("sim", "yes", "não", "nao", "ok", "accept", "", "  ", "ACCEPTED?"):
        assert parse_answer(not_an_answer) == "", not_an_answer


# ── twin 1: an ambiguous answer records NOTHING ──────────────────────────────────────
def test_an_answer_with_no_date_records_nothing_and_leaves_it_pending():
    """A bare "sim" names no class, so there is nothing to record — and the tool RAISES.

    The refusal is the point and so is its shape: it says the invitation is still open, so the
    turn above can ask again instead of reporting a breakdown. Nothing reached the store."""
    svc, store = _svc()

    with pytest.raises(CoordinatorError) as exc:
        svc.record_class_response(class_date="", answer=RSVP_ACCEPTED,
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert "which class" in str(exc.value).lower()
    assert store.writes == []
    assert svc.class_response(svc.aggregate()[0]) == RSVP_PENDING


def test_an_answer_that_is_not_one_of_the_two_records_nothing():
    """"sim" is not the field's alphabet. The refusal NAMES both valid values, so the caller's
    next attempt is a correction rather than another guess."""
    svc, store = _svc()

    with pytest.raises(CoordinatorError) as exc:
        svc.record_class_response(class_date="10/09/2026", answer="sim",
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert "ACCEPTED" in str(exc.value) and "DECLINED" in str(exc.value)
    assert store.writes == []
    assert svc.class_response(svc.aggregate()[0]) == RSVP_PENDING


def test_a_date_matching_two_classes_records_nothing_and_names_them():
    """Two class groups on one day: the answer cannot be assigned, so it is not.

    The refusal lists both so the professor can answer again with the group — a refusal that
    leaves no way forward is a dead end wearing a sentence."""
    svc, store = _svc(_TWO_SAME_DAY, second=_TWO_SAME_DAY_OTHER)

    with pytest.raises(CoordinatorError) as exc:
        svc.record_class_response(class_date="10/09", answer=RSVP_ACCEPTED,
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    msg = str(exc.value)
    assert "DE_09" in msg and "DSA_33" in msg
    assert store.writes == []
    assert all(svc.class_response(e) == RSVP_PENDING for e in svc.aggregate())


def test_the_same_date_in_two_years_records_nothing():
    """A bare ``dd/mm`` over a multi-year sheet is the coordinator's own wrong-year bug, and the
    check that catches it is the one ``confirm_swap`` already carries — reused, not re-derived."""
    svc, store = _svc(_TWO_YEARS)

    with pytest.raises(CoordinatorError) as exc:
        svc.record_class_response(class_date="10/09", answer=RSVP_ACCEPTED,
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert "2026" in str(exc.value) and "2027" in str(exc.value)
    assert store.writes == []


def test_a_group_that_disambiguates_lets_the_same_answer_through():
    """The way OUT of the ambiguity, pinned beside it: name the group and the answer lands.

    Without this the refusal above would be the whole feature — and a professor who teaches two
    groups on a Thursday could never answer at all."""
    svc, store = _svc(_TWO_SAME_DAY, second=_TWO_SAME_DAY_OTHER)

    entry, state, changed = svc.record_class_response(
        class_date="10/09", answer=RSVP_ACCEPTED, turma="DE_09",
        professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert (state, changed) == (RSVP_ACCEPTED, True)
    assert entry.sheet_key == "Turma DE_09"
    assert [(w[0], w[3], w[4]) for w in store.writes] == [(_SID, _STATUS, "Aceita")]


def test_a_date_that_matches_no_class_records_nothing():
    """Nothing to answer means nothing to record. Said as "there is no invitation to answer", so
    the turn above reports a missing class rather than a system that failed."""
    svc, store = _svc()

    with pytest.raises(CoordinatorError) as exc:
        svc.record_class_response(class_date="31/12/2026", answer=RSVP_ACCEPTED,
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert "no invitation to answer" in str(exc.value)
    assert store.writes == []


def test_a_group_that_designates_nothing_refuses_and_names_the_ones_that_exist():
    """A ``turma`` filter that matches no configured group must not quietly become "no filter" —
    that answers a question nobody asked, and here it would record against whichever class the
    date happened to hit. The refusal lists the real names so the next try can succeed."""
    svc, store = _svc()

    with pytest.raises(CoordinatorError) as exc:
        svc.record_class_response(class_date="10/09/2026", answer=RSVP_ACCEPTED, turma="XX_99",
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert "DE_09" in str(exc.value)
    assert store.writes == []


def test_reading_a_sheet_with_no_status_column_answers_PENDING_rather_than_raising():
    """The READ half degrades where the write refuses, and the asymmetry is deliberate: a
    listing that cannot find the column has simply never been told an answer, while a WRITE that
    cannot find it has nowhere to put one. Same missing header, two correct behaviours."""
    svc, _store = _svc([["10/09/2026", "Qui", "Ana", "Redes", ""]],
                       header=["Data", "Dia", "Professor", "Disciplina", ""])

    assert svc.class_response(svc.aggregate()[0]) == RSVP_PENDING


def test_the_in_memory_store_refuses_a_cell_outside_the_grid():
    """The test double holds the same bound the Google adapter does, so a coordinate bug fails
    in the fast suite instead of only against the real API."""
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", _grid(_ONE))

    with pytest.raises(IndexError):
        store.write_cell(_SID, "Secretaria", "A4:E200", 99, _STATUS, "Aceita")
    with pytest.raises(IndexError):
        store.write_cell(_SID, "Secretaria", "A4:E200", 1, 99, "Aceita")


# ── twin 2: a repeated answer is ONE state ───────────────────────────────────────────
def test_the_second_identical_answer_writes_nothing_and_says_so():
    """Two "sim" to one invitation are one state.

    Asserted on the WRITE COUNT, not on the cell: the grid looks the same either way, and the
    claim being made is that the second call did not act. ``changed=False`` is what the tool
    turns into "was ALREADY recorded — no change was made", the sentence the judge's NOTHING TO
    DO clause reads as a correct outcome instead of an unfinished one."""
    svc, store = _svc()
    kw = dict(class_date="10/09/2026", answer=RSVP_ACCEPTED,
              professor="Ana", identity_label="Ana", role="PROFESSOR")

    first = svc.record_class_response(**kw)
    second = svc.record_class_response(**kw)

    assert (first[1], first[2]) == (RSVP_ACCEPTED, True)
    assert (second[1], second[2]) == (RSVP_ACCEPTED, False)
    assert len(store.writes) == 1, "the second answer must not write a second time"
    assert svc.class_response(svc.aggregate()[0]) == RSVP_ACCEPTED


def test_changing_an_earlier_answer_is_allowed_and_is_recorded():
    """Accepted, then cannot come — the professor has to be able to say so.

    The decision written down: a re-answer CHANGES the state. Freezing the first one would
    leave the sheet describing a class that is not going to happen, and the professor with no
    way to correct it but a phone call. It goes through the same confirmation gate as the first."""
    svc, store = _svc()
    kw = dict(class_date="10/09/2026", professor="Ana", identity_label="Ana", role="PROFESSOR")

    svc.record_class_response(answer=RSVP_ACCEPTED, **kw)
    entry, state, changed = svc.record_class_response(answer=RSVP_DECLINED, **kw)

    assert (state, changed) == (RSVP_DECLINED, True)
    assert entry.date_str == "10/09/2026"
    # Re-READ, never the returned entry: like ``confirm_swap``, this hands back the rows AS THEY
    # WERE LOCATED, so asking the stale copy what the sheet now says would answer about the past.
    assert svc.class_response(svc.aggregate()[0]) == RSVP_DECLINED
    assert [w[4] for w in store.writes] == ["Aceita", "Recusada"]


def test_a_value_this_system_did_not_write_is_never_overwritten():
    """The tenant's secretary wrote something in that cell. It stays.

    This feature is entitled to its own two words in that column and to the ordinary status it
    replaces — not to the column. Overwriting a human's note with a machine label destroys
    information nobody can get back, so the refusal reports what is there instead."""
    svc, store = _svc([["10/09/2026", "Qui", "Ana", "Redes", "Proposta enviada"]])

    with pytest.raises(CoordinatorError) as exc:
        svc.record_class_response(class_date="10/09/2026", answer=RSVP_ACCEPTED,
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert "Proposta enviada" in str(exc.value)
    assert store.writes == []


def test_the_ordinary_status_is_replaced_because_it_is_not_an_answer():
    """"Confirmado" is the routine state of a scheduled class, not a professor's reply — so it
    reads as PENDING and an answer is allowed to land on top of it. The twin of the test above:
    the same branch, the other verdict, and the pair is what makes the rule a rule."""
    svc, store = _svc([["10/09/2026", "Qui", "Ana", "Redes", "Confirmado"]])

    entry, state, changed = svc.record_class_response(
        class_date="10/09/2026", answer=RSVP_DECLINED,
        professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert (state, changed) == (RSVP_DECLINED, True)
    assert entry.subject == "Redes"
    assert svc.class_response(svc.aggregate()[0]) == RSVP_DECLINED     # re-read, not the copy
    assert len(store.writes) == 1


# ── where the state lands, and who may put it there ──────────────────────────────────
def test_the_answer_lands_in_the_named_column_of_that_class_row():
    """The coordinates, asserted rather than assumed: the tenant's ``COLUMN_STATUS`` resolved by
    NAME, and the row the class was READ from — the same coordinate system ``swap_rows`` uses.

    Resolving a STATE column by position is how an inserted column starts silently rewriting the
    wrong one; ``types.DailyChecks`` refuses to even READ that column for the same reason."""
    svc, store = _svc([["08/09/2026", "Ter", "Ana", "Algoritmos", ""],
                       ["10/09/2026", "Qui", "Ana", "Redes", ""]])

    svc.record_class_response(class_date="10/09/2026", answer=RSVP_ACCEPTED,
                              professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert store.writes == [(_SID, "Secretaria", 2, _STATUS, "Aceita")]
    grid = store.read_range(_SID, "Secretaria", "A4:E200")
    assert grid[1][_STATUS] == "" and grid[2][_STATUS] == "Aceita"


def test_a_sheet_with_no_status_column_refuses_as_CONFIGURATION_and_writes_nothing():
    """The live corpus's schedule tab carries an approval cell whose HEADER IS BLANK, so the
    column this writes to genuinely may not resolve. That is a tenant declaration somebody can
    go and add — a ``CoordinatorConfigError``, which the MCP wrapper renders NOT CONFIGURED, and
    never an ERROR the model relays to a professor as a breakdown."""
    svc, store = _svc([["10/09/2026", "Qui", "Ana", "Redes", ""]],
                      header=["Data", "Dia", "Professor", "Disciplina", ""])

    with pytest.raises(CoordinatorConfigError) as exc:
        svc.record_class_response(class_date="10/09/2026", answer=RSVP_ACCEPTED,
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert "Status" in str(exc.value)
    assert store.writes == []


def test_a_professor_cannot_answer_for_a_colleague():
    """The write is scoped by the SAME ``_visible`` every read uses — one definition, so the
    write cannot be laxer than the read that showed it."""
    svc, store = _svc()

    with pytest.raises(CoordinatorAccessError):
        svc.record_class_response(class_date="10/09/2026", answer=RSVP_ACCEPTED,
                                  professor="Bruno", identity_label="Ana", role="PROFESSOR")

    assert store.writes == []


def test_an_unreadable_spreadsheet_refuses_the_write_outright():
    """A half-loaded schedule cannot tell "no such class" from "the sheet holding it did not
    load", and the second one, acted on, records an answer against the wrong row — or reports
    none where one exists. Same refusal ``confirm_swap`` makes, for the same reason."""
    svc, store = _svc()

    def _boom(sheet_id, tab, a1_range):
        raise TimeoutError("nope")

    store.read_range = _boom  # type: ignore[method-assign]

    with pytest.raises(CoordinatorError) as exc:
        svc.record_class_response(class_date="10/09/2026", answer=RSVP_ACCEPTED,
                                  professor="Ana", identity_label="Ana", role="PROFESSOR")

    assert "partly loaded" in str(exc.value)
    assert store.writes == []


# ── the tool surface: a refusal must not be stamped as a write ───────────────────────
def test_the_tool_is_declared_MUTATING_so_the_host_gate_holds_it():
    """``readOnlyHint=False`` is what makes the house's own rule apply without a line of host
    code: ``WriteConfirmingDispatcher`` falls through to ``is_mutating``, so this call is HELD
    and only the contact's own affirmative releases it. That is "nothing is committed that was
    not re-proposed to the contact", enforced by the gate rather than promised by a prompt —
    which matters here because the whole feature is about not turning a stray "sim" into a
    commitment. ``destructiveHint`` is declared too, so the tool does not depend on that wrapper
    being present to be gated."""
    svc, _store = _svc()
    tools = build_server(svc)._tool_manager._tools

    ann = tools["record_class_response"].annotations
    assert ann is not None
    assert ann.readOnlyHint is False
    assert ann.destructiveHint is True


def test_a_refused_answer_RAISES_rather_than_returning_a_sentence():
    """A FastMCP tool that RETURNS a sentence is a successful call, and a successful call on a
    non-read-only tool is stamped ``side_effect=True`` by the bridge — a refused answer entering
    the house's commit accounting as a change that never happened. Raising lands as ``isError``
    → ``ok=False`` → ``side_effect=False``. Same contract, same reason, as
    ``send_schedule_to_calendar`` and ``confirm_swap``."""
    svc, store = _svc()
    mcp = build_server(svc)

    async def run():
        with pytest.raises(Exception) as exc:
            await mcp.call_tool("record_class_response",
                                dict(class_date="", answer=RSVP_ACCEPTED, professor="Ana",
                                     identity_label="Ana", role="PROFESSOR"))
        assert "which class" in str(exc.value).lower()
    asyncio.run(run())

    assert store.writes == []


def test_an_access_refusal_reaches_the_model_as_NOT_PERMITTED_and_still_raises():
    """Two things at once, and both were measured elsewhere in this house.

    It RAISES, because a returned sentence on a mutating tool is a successful call the bridge
    stamps as a write. And it is worded NOT PERMITTED, because "ERROR" is what a model relays to
    a professor as "não consegui acessar" — a rule working as intended must not be reported as a
    breakdown. Same pair ``confirm_swap`` carries."""
    svc, store = _svc()
    tool = build_server(svc)._tool_manager._tools["record_class_response"]

    with pytest.raises(CoordinatorError) as exc:
        tool.fn(class_date="10/09/2026", answer=RSVP_ACCEPTED, professor="Bruno",
                identity_label="Ana", role="PROFESSOR")

    assert str(exc.value).startswith("NOT PERMITTED")
    assert "nothing was recorded" in str(exc.value)
    assert not isinstance(exc.value, CoordinatorAccessError), (
        "the wrapper must hand the model a CoordinatorError — the ACCESS type is what the "
        "read tools' _guard renders, and this path cannot return a sentence at all")
    assert store.writes == []


def test_the_tool_says_no_change_was_made_on_a_repeat():
    """The words matter: the SUPEREGO's judge reads "ALREADY ... no change was made" as a
    correct outcome. Phrased as a failure, the same turn burns the correction budget looking for
    a change to make — measured on the bookkeeper, which is where this sentence comes from."""
    svc, _store = _svc()
    tool = build_server(svc)._tool_manager._tools["record_class_response"]
    kw = dict(class_date="10/09/2026", answer=RSVP_ACCEPTED,
              professor="Ana", identity_label="Ana", role="PROFESSOR")

    first = tool.fn(**kw)
    again = tool.fn(**kw)

    assert first.startswith("Recorded ACCEPTED")
    assert "ALREADY" in again and "no change was made" in again

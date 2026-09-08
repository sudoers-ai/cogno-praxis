"""``RSVP=TRUE`` on the class calendar — and the refusal that has to come with it.

Two changes, and the second exists only because of the first.

**The invitation now asks.** The events carried ``RSVP=FALSE``, so a professor's calendar
imported them and offered nothing; they now carry ``RSVP=TRUE``, so the client shows accept and
decline. ``PARTSTAT`` deliberately stays ``ACCEPTED`` beside it. That pair is self-contradictory
— "you are down as attending, but tell me if that changes" — and it is the cheaper of the two
available wrongs: this file is THIRTY classes imported in one action, so ``NEEDS-ACTION`` would
put thirty unanswered invitations in somebody's calendar to close an incoherence nobody sees.

**Nothing reads the reply, and that is not a gap this file closes.** There is no IMAP/POP path
in, no ``METHOD:REPLY`` parser, no ``PARTSTAT`` reader, no column anywhere recording an
acceptance. The professor can now decline every class and the schedule will not move. It is
written down in the module docstring, at the ``ATTENDEE`` line, and here, because the change is
exactly the kind that invites a reader to assume the loop closes.

**And that is what makes a blank ORGANIZER stop being cosmetic.** ``CalendarSender.organizer()``
is allowed to answer ``""`` — a mail config with neither a declared ``from_email`` nor an
authenticated ``user`` has no From address to give, and the adapter says so honestly
(``test_coordinator_mailer.py``). Until now nothing read that ``""``: the builder rendered
``ORGANIZER:mailto:`` and the message went out regardless. With ``RSVP=TRUE`` every reply is
addressed to the ORGANIZER, so an empty one is an invitation with nowhere to answer. It is now
refused, NAMING the key, over the CONFIGURATION and never over the professor's request — and
nothing is sent.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import pytest

from cogno_praxis.coordinator import (
    CalendarEvent,
    CoordinatorConfig,
    CoordinatorConfigError,
    CoordinatorService,
    InMemorySpreadsheetStore,
    RecordingCalendarSender,
    build_ics_calendar,
    build_server,
)

_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_RULES = (
    f"SPREADSHEETS:\nDSA={_SID}\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
    'TAB_PROFESSORS: "Info"\nRANGE_PROFESSORS: "A1:E50"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
    'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n'
)
_TODAY = date(2026, 9, 8)
_SUPERVISOR = {"role": "SUPERVISOR", "identity_label": "Sofia", "professor": "Ana"}


def _service():
    cfg = CoordinatorConfig(_RULES)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [[""] * 5] * 3 + [
        ["Data", "Dia", "Professor", "Disciplina", "Sala"],
        ["10/09/2026", "Qui", "Ana", "Redes", "101"],
    ])
    store.put(_SID, "Info", [["Professor", "E-mail"], ["Ana", "ana@escola.test"]])
    return CoordinatorService(store, cfg, today=lambda: _TODAY)


# ── the events a control run produced, frozen ────────────────────────────────────────
#
# Captured from the worktree at `bce5b06` with every varying input pinned (a fixed `now`, a
# fixed `sequence`). It is the whole point of the byte twin below: a change that claims to move
# ONE token has to be shown moving one token, and "the tests still pass" does not show that.
_EVENTS = [
    CalendarEvent(uid="u1@cogno-praxis", summary="Redes — DE_09", day=date(2026, 9, 8),
                  time="19:00", description="Turma: DE_09 | Data: 08/09/2026",
                  location="Sala 101"),
    CalendarEvent(uid="u2@cogno-praxis", summary="NoSQL — DSA_33", day=date(2026, 9, 10)),
]
_KW = dict(organizer_email="coord@escola.test", organizer_name="Coordenação",
           attendee="ana@escola.test", tz_name="America/Sao_Paulo", sequence=42,
           duration_minutes=240, now=datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc))

_CONTROL_ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Cogno AI//Coordinator//EN\r\n"
    "CALSCALE:GREGORIAN\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:u1@cogno-praxis\r\n"
    "DTSTAMP:20260908T120000Z\r\nDTSTART;TZID=America/Sao_Paulo:20260908T190000\r\n"
    "DTEND;TZID=America/Sao_Paulo:20260908T230000\r\nSUMMARY:Redes — DE_09\r\n"
    "DESCRIPTION:Turma: DE_09 | Data: 08/09/2026\r\nLOCATION:Sala 101\r\n"
    "STATUS:CONFIRMED\r\nTRANSP:TRANSPARENT\r\nSEQUENCE:42\r\n"
    "ORGANIZER;CN=Coordenação:mailto:coord@escola.test\r\n"
    "ATTENDEE;RSVP=FALSE;PARTSTAT=ACCEPTED:mailto:ana@escola.test\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:u2@cogno-praxis\r\nDTSTAMP:20260908T120000Z\r\n"
    "DTSTART;VALUE=DATE:20260910\r\nDTEND;VALUE=DATE:20260911\r\nSUMMARY:NoSQL — DSA_33\r\n"
    "STATUS:CONFIRMED\r\nTRANSP:TRANSPARENT\r\nSEQUENCE:42\r\n"
    "ORGANIZER;CN=Coordenação:mailto:coord@escola.test\r\n"
    "ATTENDEE;RSVP=FALSE;PARTSTAT=ACCEPTED:mailto:ana@escola.test\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n")


# ── twin 1: with an address, the invitation asks ─────────────────────────────────────
def test_the_invitation_asks_for_a_reply_and_the_organizer_is_still_the_From():
    """``RSVP=TRUE``, and the ORGANIZER it points at is unchanged — read off the sender, never
    guessed beside it. One fact, one source: with RSVP on, a second, separately-configured
    address would be a mailbox the transport does not send from collecting the replies."""
    ics = build_ics_calendar(_EVENTS, **_KW)

    assert "ATTENDEE;RSVP=TRUE;PARTSTAT=ACCEPTED:mailto:ana@escola.test" in ics
    assert "RSVP=FALSE" not in ics
    assert "ORGANIZER;CN=Coordenação:mailto:coord@escola.test" in ics


def test_the_PARTSTAT_beside_it_deliberately_stays_ACCEPTED():
    """The decision, pinned so it cannot drift without somebody choosing to. Thirty classes at
    NEEDS-ACTION is thirty unanswered invitations in a person's calendar; the contradiction is
    the cheaper wrong, and it is only cheap because nothing reads the reply anyway."""
    ics = build_ics_calendar(_EVENTS, **_KW)

    assert "PARTSTAT=ACCEPTED" in ics
    assert "NEEDS-ACTION" not in ics


# ── twin 2 (the byte twin): NOTHING ELSE in the file moved ───────────────────────────
def test_everything_else_in_the_file_is_byte_for_byte_what_it_was():
    """The negative twin, and the only form of it worth having.

    Put the one token back and the file must be IDENTICAL to what the control commit produced —
    same PRODID, same METHOD, same UIDs, same DTSTAMP, same folding, same CRLFs, same trailing
    line. A change advertised as one token is measured as one token."""
    ics = build_ics_calendar(_EVENTS, **_KW)

    assert ics.replace("RSVP=TRUE", "RSVP=FALSE") == _CONTROL_ICS
    # and the count is right too: the substitution is one per VEVENT, not a lucky global
    assert ics.count("RSVP=TRUE") == len(_EVENTS)


def test_a_calendar_with_no_attendee_is_completely_untouched():
    """A file with no ATTENDEE line has no RSVP to change, so it must be byte-identical with no
    substitution at all — the change cannot have leaked into a neighbouring property."""
    without = dict(_KW, attendee="")
    ics = build_ics_calendar(_EVENTS, **without)

    assert "ATTENDEE" not in ics and "RSVP" not in ics
    expected = "\r\n".join(ln for ln in _CONTROL_ICS.split("\r\n")
                           if not ln.startswith("ATTENDEE;"))
    assert ics == expected


# ── twin 3: without a From address it refuses, NAMES the key, and sends nothing ───────
def test_the_builder_refuses_to_render_an_invitation_with_nowhere_to_answer():
    """The floor, under the domain refusal: a caller that walked past the service still cannot
    put ``ORGANIZER:mailto:`` on the wire. Blank and whitespace are the same answer."""
    for blank in ("", "   "):
        with pytest.raises(ValueError, match="ORGANIZER"):
            build_ics_calendar(_EVENTS, **dict(_KW, organizer_email=blank))


def test_the_send_refuses_NAMING_the_key_and_no_mail_leaves():
    """The refusal a person actually reads. It is about the CONFIGURATION — it names the line
    somebody has to add — and never about the professor or their request. And the witness that
    matters is the sender's own record: nothing was handed to it."""
    svc = _service()
    sender = RecordingCalendarSender(organizer_email="")

    async def run():
        with pytest.raises(CoordinatorConfigError) as exc:
            await svc.send_schedule_to_calendar(sender=sender, **_SUPERVISOR)
        msg = str(exc.value)
        assert "from_email" in msg and "user" in msg          # the keys are NAMED
        assert "Nothing was sent" in msg
    asyncio.run(run())

    assert sender.sent == [], "a refusal must not put a message in the mail"


def test_the_PREVIEW_refuses_the_same_way_rather_than_promising_a_send():
    """Both paths come through ``_prepare_calendar``, so the proposal inherits the refusal — a
    preview that offered to send a calendar the send will refuse is a promise nobody keeps."""
    svc = _service()
    with pytest.raises(CoordinatorConfigError):
        svc.preview_schedule_to_calendar(sender=RecordingCalendarSender(organizer_email=""),
                                         **_SUPERVISOR)


def test_the_refusal_reaches_the_model_as_NOT_CONFIGURED_not_as_a_breakdown():
    """The word the model reads is the word the professor eventually hears. A tenant whose SMTP
    is half-filled is not a system that broke, and "ERROR" is what gets relayed as "não consegui
    acessar"."""
    mcp = build_server(_service(), sender=RecordingCalendarSender(organizer_email=""))

    async def run():
        res = await mcp.call_tool("preview_schedule_to_calendar", dict(_SUPERVISOR))
        out = "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")
        assert out.startswith("NOT CONFIGURED:")
        assert "from_email" in out
        assert not out.startswith("ERROR")
    asyncio.run(run())


# ── the twin that keeps the refusal from being too eager ─────────────────────────────
def test_a_sender_that_DOES_declare_an_address_still_sends_exactly_as_before():
    """The other side of the gate. A refusal that fired on a correctly configured deployment
    would cost every professor their calendar to protect a case that is not theirs."""
    svc = _service()
    sender = RecordingCalendarSender(organizer_email="coord@escola.test",
                                     organizer_name="Coordenação")

    async def run():
        count, to, dropped = await svc.send_schedule_to_calendar(sender=sender, **_SUPERVISOR)
        assert (count, to, dropped) == (1, "ana@escola.test", 0)
    asyncio.run(run())

    assert len(sender.sent) == 1
    assert "RSVP=TRUE" in sender.sent[0]["ics"]

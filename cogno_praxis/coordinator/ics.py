"""The professor's schedule as an iCalendar (``.ics``) the recipient's calendar can IMPORT.

One mail, one attachment, **N ``VEVENT``s** — the shape a calendar imports in a single action.
The scheduler's booking invite (``cogno_host.invites``, over ``cogno_herald.build_ics_event``)
is the other shape: exactly ONE event, about one appointment, sent the moment it is booked. The
two are not a parameter apart. A booking has an appointment id and a guest; a class has neither
— it has a class group, a discipline and a day, and it comes in batches of thirty. So this is a
NEW entry point beside that one, and the booking invite is not touched by it:
``build_ics_event`` still renders the same bytes it rendered yesterday.

**The reply is not read, and this file will not pretend otherwise.** Since 2026-09-08 the
events carry ``RSVP=TRUE``, so the professor's own calendar offers them accept and decline —
and NOTHING IN THIS SYSTEM EVER LEARNS WHICH THEY CHOSE. There is no IMAP or POP path in, no
``METHOD:REPLY`` parser, no ``PARTSTAT`` reader, and no column in any table that records an
acceptance. A reply is delivered to the ``ORGANIZER`` mailbox and read by whoever reads that
mailbox, which is a person, not this code. Anyone building on top of this should assume the
loop is OPEN: a professor may decline every class in the file and the schedule will not move.

``PARTSTAT`` stays ``ACCEPTED`` beside that ``RSVP=TRUE``, which is a contradiction on purpose
— see the note at the ``ATTENDEE`` line for the thirty-unanswered-invitations reason.

**The UID is derived from CONTENT, and that is the whole design.** A calendar keeps one entry
per ``UID``; a second message carrying the same ``UID`` and a higher ``SEQUENCE`` UPDATES that
entry, and a message carrying a different one ADDS a second entry. So "send my September again
after the room changed" is only an update if the identifier survives the edit.

The obvious identifier — the spreadsheet row — does not survive anything. A row index is a
POSITION: insert one class at the top of the sheet and every row below it shifts down by one,
so every UID after the insertion changes, no message updates anything, and the professor's
calendar gets a second copy of the whole term. The identifier is therefore built out of the
facts a row CARRIES rather than where it sits: class group, discipline, date, and the hour when
the sheet records one. Those four are what a human would use to say *which class*, and they do
not move when a neighbouring row is added, removed or reordered.

The cost of content addressing is stated rather than hidden: correcting a typo in a discipline
name, or moving a class to another date (``confirm_swap``), MAKES A NEW EVENT — and the old one
is left in the calendar, because removing it would need a ``METHOD:CANCEL`` for an identifier
nobody remembered. Nothing here stores what was sent, so nothing here can cancel it.

**Time and zone.** A schedule sheet records a DAY; an hour column is optional and many tenants
have none. With no hour the event is ALL-DAY (``VALUE=DATE``), which is the honest rendering of
what the sheet knows. With an hour the event carries the tenant's ``TZID`` — never a floating
time and never raw UTC, because a class at 19:00 in São Paulo is not a class at 19:00 wherever
the reader's laptop happens to be. And when no zone was declared, the hour is DROPPED and the
event falls back to all-day: this module will not emit a time it cannot place.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional, Protocol, runtime_checkable

#: ``PRODID`` of the calendars this module renders. Distinct from the booking invite's
#: ``-//Cogno AI//Scheduler//EN`` on purpose: two products, two identifiers.
PRODID = "-//Cogno AI//Coordinator//EN"

#: The ``UID`` suffix. RFC 5545 wants a globally unique value and the conventional shape is
#: ``<opaque>@<domain>``; the opaque half is the content digest below.
UID_DOMAIN = "cogno-praxis"

#: How many hex characters of the digest ride in the ``UID``. 40 bits short of the full
#: SHA-256 and still far past any collision a tenant's schedule could produce.
_UID_HEX = 40

#: ``HH:MM`` / ``HH'h'MM`` / ``HHhMM`` / bare ``HHh`` — the shapes a schedule cell writes an
#: hour in. Anchored at the start so "19:00 às 22:30" reads its FIRST hour and nothing else.
_TIME = re.compile(r"^\s*([0-2]?\d)\s*[:hH]\s*([0-5]\d)?")


def _norm(text: str) -> str:
    """Accent-stripped, lowercased, whitespace-collapsed — the digest's input normalizer.

    The same normalization the service uses to compare labels, plus the whitespace collapse:
    a tenant who reformats ``"Turma  DE_09"`` to ``"Turma DE_09"`` must not thereby duplicate
    every class in the professor's calendar.
    """
    nfkd = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def parse_time(raw: str) -> str:
    """``"19h30"``/``"19:30"``/``"19h"`` → ``"19:30"``/``"19:00"``; anything else → ``""``.

    Returns a canonical ``HH:MM`` so the UID digest cannot be split by the two spellings of one
    hour, and so ``build_ics_calendar`` has a single shape to parse."""
    m = _TIME.match(raw or "")
    if not m:
        return ""
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if hour > 23:
        return ""
    return f"{hour:02d}:{minute:02d}"


def class_event_uid(*, turma: str, subject: str, day: Optional[date], date_str: str,
                    time: str = "") -> str:
    """The stable ``UID`` for one class — a digest of WHAT the class is, never WHERE it sits.

    The four inputs are the class group, the discipline, the date and (when the sheet has one)
    the hour. ``day`` is the parsed date and wins when it parsed; ``date_str`` is the fallback
    for a cell no parser could read, so an undatable row still gets a UID that is at least
    stable against a neighbour being inserted.

    Row index is deliberately NOT an input — see the module docstring. Neither is the
    PROFESSOR: a calendar is sent to one person, so their own name discriminates nothing, and
    including it would make a corrected spelling in the sheet duplicate their whole term.
    """
    key = "|".join((_norm(turma), _norm(subject),
                    day.isoformat() if day else _norm(date_str), _norm(time)))
    return f"{hashlib.sha256(key.encode('utf-8')).hexdigest()[:_UID_HEX]}@{UID_DOMAIN}"


#: The ``SEQUENCE`` epoch as POSIX seconds — 2020-01-01T00:00:00Z. Lifted from
#: ``cogno_host.invites._SEQ_EPOCH_POSIX``, deliberately the same rule for the same reason: a
#: client honours a repeated ``UID`` only at a HIGHER revision number, so the number has to be
#: monotonic per UID across every message we ever send about that event AND survive a process
#: restart. Elapsed seconds do both with no storage, and the offset keeps the value inside
#: int32 until ~2088 (from 1970 the ceiling would be 2038).
_SEQ_EPOCH_POSIX = 1_577_836_800


def sequence_now(now: Optional[float] = None) -> int:
    """The revision number for a calendar sent NOW — seconds since :data:`_SEQ_EPOCH_POSIX`.

    An INSTANT, never a wall clock: read as local naive time the number goes BACKWARDS across
    a DST fall-back, and a revision numbered below the one before it is silently dropped by
    every client (measured by ``cogno_host.invites``, whose note this repeats rather than
    re-derives).

    No per-UID tie-breaker here, unlike the booking invite's LRU. There it guards a real case —
    one turn that reschedules and then cancels the SAME appointment inside one second. A
    calendar export has no such pair: a re-send is one message about the whole set, and two of
    them inside one second would carry byte-identical content, so a client dropping the second
    loses nothing. Said out loud because the absence of the LRU is a DECISION, not an omission.
    """
    import time as _time
    return int(now if now is not None else _time.time()) - _SEQ_EPOCH_POSIX


@dataclass(frozen=True)
class CalendarEvent:
    """One ``VEVENT`` to render: an identity, a title, a day, and maybe an hour."""
    uid: str
    summary: str
    day: date
    time: str = ""                    # canonical "HH:MM"; "" → all-day
    description: str = ""
    location: str = ""


def _escape(text: str) -> str:
    """Escape a property VALUE per RFC 5545 §3.3.11."""
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """Fold one content line to the RFC 5545 §3.1 limit (75 octets, continuation lines
    starting with a space).

    Not decoration: a discipline name long enough to push ``SUMMARY`` past 75 octets is
    ordinary in an MBA schedule ("Fundamentos de Arquitetura de Software Distribuído"), and an
    unfolded long line is a malformed file — which some clients reject WHOLE, losing every one
    of the thirty classes over one of them. Folding counts OCTETS, not characters, and never
    splits a UTF-8 sequence.
    """
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return [line]
    out: list[str] = []
    limit = 75
    while raw:
        if len(raw) <= limit:
            out.append(raw.decode("utf-8"))
            break
        cut = limit
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:      # never split a UTF-8 sequence
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = raw[cut:]
        limit = 74                                        # continuation lines carry a leading space
    return [out[0]] + [" " + part for part in out[1:]]


def _utc_stamp(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics_calendar(
    events: Iterable[CalendarEvent],
    *,
    organizer_email: str,
    organizer_name: str = "",
    attendee: str = "",
    tz_name: str = "",
    sequence: int = 0,
    duration_minutes: int = 60,
    now: Optional[datetime] = None,
) -> str:
    """One ``VCALENDAR`` carrying every event — the file a professor imports in one action.

    ``sequence`` is the RFC 5545 revision number and applies to EVERY event in the file: a
    re-send is one message about the same set of UIDs, so one number moves them all. A client
    honours a repeated UID only when the number is HIGHER than the one it holds, so a re-send at
    an equal number is delivered, logged as sent, and silently discarded by the calendar — the
    same trap ``cogno_host.invites`` documents for the booking invite, and the caller owns the
    number for the same reason: only the caller knows the event's history.

    ``tz_name`` is the tenant's zone NAME (``America/Sao_Paulo``), rendered as a ``TZID``
    reference. Empty → every event is all-day, whatever hour it carries.

    Returns ``""`` for an empty event list — there is no such thing as a calendar with no
    events, and a caller that got nothing to send must say so rather than mail an empty file.
    """
    events = list(events)
    if not events:
        return ""
    if not organizer_email.strip():
        # The LAST guard before bytes, and it exists because of what the line above it now
        # says. With ``RSVP=TRUE`` every reply a client sends is addressed to the ORGANIZER,
        # so an empty one is an invitation with nowhere to answer — and the old behaviour was
        # to render ``ORGANIZER:mailto:`` and mail it anyway. The caller refuses first and with
        # a sentence a person can act on (``CoordinatorService._prepare_calendar``); this one
        # is the floor a future caller cannot walk past.
        raise ValueError(
            "a calendar cannot be built without an ORGANIZER address: with RSVP=TRUE the "
            "attendee's reply is addressed to it, so an empty one is an invitation with "
            "nowhere to answer")
    stamp = _utc_stamp(now)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
    ]
    for ev in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{ev.uid}")
        lines.append(f"DTSTAMP:{stamp}")
        if ev.time and tz_name:
            start = datetime.combine(ev.day, datetime.strptime(ev.time, "%H:%M").time())
            end = start + timedelta(minutes=duration_minutes)
            lines.append(f"DTSTART;TZID={tz_name}:{start.strftime('%Y%m%dT%H%M%S')}")
            lines.append(f"DTEND;TZID={tz_name}:{end.strftime('%Y%m%dT%H%M%S')}")
        else:
            # All-day: DTEND is EXCLUSIVE in RFC 5545, so a one-day event ends the NEXT day.
            lines.append(f"DTSTART;VALUE=DATE:{ev.day.strftime('%Y%m%d')}")
            lines.append(f"DTEND;VALUE=DATE:{(ev.day + timedelta(days=1)).strftime('%Y%m%d')}")
        lines.append(f"SUMMARY:{_escape(ev.summary)}")
        if ev.description:
            lines.append(f"DESCRIPTION:{_escape(ev.description)}")
        if ev.location:
            lines.append(f"LOCATION:{_escape(ev.location)}")
        lines.append("STATUS:CONFIRMED")
        lines.append("TRANSP:TRANSPARENT")
        lines.append(f"SEQUENCE:{int(sequence)}")
        if organizer_name:
            lines.append(
                f"ORGANIZER;CN={_escape(organizer_name)}:mailto:{organizer_email}")
        else:
            lines.append(f"ORGANIZER:mailto:{organizer_email}")
        if attendee:
            # RSVP=TRUE beside PARTSTAT=ACCEPTED is a DELIBERATE, and self-contradictory, pair:
            # it reads as "you are already down as attending, but tell me if that changes".
            # Each half is chosen against a measured cost and neither is free.
            #
            # RSVP=TRUE is what makes the professor's client offer the accept/decline controls
            # at all. PARTSTAT stays ACCEPTED because this file is THIRTY classes, imported in
            # one action: NEEDS-ACTION would turn every one of them into an unanswered
            # invitation sitting in a person's calendar, which is a cost they see every day, to
            # close an incoherence nobody sees.
            #
            # And the incoherence is smaller than it looks, because of what is NOT built:
            # NOTHING EVER READS THE REPLY. There is no IMAP/POP path into this system, no
            # METHOD:REPLY parser, no PARTSTAT reader, no column anywhere that records an
            # acceptance. The professor can now accept or decline in their own calendar and we
            # will not know. See the module docstring.
            lines.append(f"ATTENDEE;RSVP=TRUE;PARTSTAT=ACCEPTED:mailto:{attendee}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"


@runtime_checkable
class CalendarSender(Protocol):
    """Deliver one built calendar. The vertical owns WHAT is sent; the host owns HOW.

    The same shape as :class:`~cogno_praxis.coordinator.store.SpreadsheetStore`: a port, so the
    domain never learns whether the file left over SMTP, went to a fake, or went nowhere.

    ``organizer()`` is here and not on the caller because the ``ORGANIZER`` of the events IS
    the mailbox the message is sent FROM — one fact, and a caller that guessed it separately
    would eventually name an address the transport does not send from. Same derivation as the
    booking invite's ``cogno_host.invites._organizer``.

    ``send`` returns the only thing the domain reads: ``True`` means the message was ACCEPTED
    by the server, and nothing else may be reported to a human as "sent".
    """

    def organizer(self) -> "tuple[str, str]": ...

    async def send(self, *, to: str, subject: str, body: str, ics: str,
                   filename: str = "schedule.ics") -> bool: ...


class RecordingCalendarSender:
    """A zero-infra :class:`CalendarSender` for tests/dev: records, never delivers.

    ``ok=False`` reproduces a server that REFUSED the message — the branch where a human must
    not be told anything was sent."""

    def __init__(self, ok: bool = True, *, organizer_email: str = "agenda@example.test",
                 organizer_name: str = "Cogno") -> None:
        self.ok = ok
        self.sent: list[dict] = []
        self._organizer = (organizer_email, organizer_name)

    def organizer(self) -> "tuple[str, str]":
        return self._organizer

    async def send(self, *, to: str, subject: str, body: str, ics: str,
                   filename: str = "schedule.ics") -> bool:
        self.sent.append({"to": to, "subject": subject, "body": body,
                          "ics": ics, "filename": filename})
        return self.ok

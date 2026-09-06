"""The calendar export: one mail, N events, and identifiers that survive an edited spreadsheet.

The properties here are the ones a re-send depends on. A calendar keeps ONE entry per ``UID``,
so "send me September again" is an update only if the identifier is the same as last time, and a
DUPLICATE of the whole term if it is not. Every assertion below is about that, about the two
paths that must send NOTHING, or about the file being legal enough for a client to open at all.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from cogno_praxis.coordinator import (
    CoordinatorAccessError,
    CoordinatorConfig,
    CoordinatorError,
    CoordinatorService,
    InMemorySpreadsheetStore,
    RecordingCalendarSender,
    build_ics_calendar,
    class_event_uid,
)
from cogno_praxis.coordinator.ics import CalendarEvent, _fold, parse_time, sequence_now

_RULES = (
    "SPREADSHEETS:\nDSA_33=1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8\n"
    'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A1:F200"\n'
    'TAB_PROFESSORS: "Info"\nRANGE_PROFESSORS: "A1:C50"\n'
    'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
    'COLUMN_TIME: "Hora"\nCLASS_DURATION_MINUTES: 240\n'
    'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n'
)
_SID = "1RKtBqIpYeaXDI6UegpHzFEkM1R_H8_vz1NNHHcLHYX8"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Hora"]
_TODAY = date(2026, 7, 13)

_ROWS = [
    ["20/07/2026", "Seg", "Ana", "Redes", "101", "19:00"],
    ["27/07/2026", "Seg", "Ana", "Redes", "101", "19:00"],
    ["03/08/2026", "Seg", "Ana", "Machine Learning", "102", "19:00"],
]
_PROFS = [["Professor", "e-mail", "Titulação"], ["Ana", "ana@escola.test", "Doutora"]]


def _service(rows=None, *, header=None, profs=None, rules=_RULES, today=_TODAY):
    cfg = CoordinatorConfig(rules)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", [list(header or _HEADER)] + [list(r) for r in (rows or _ROWS)])
    store.put(_SID, "Info", [list(r) for r in (profs if profs is not None else _PROFS)])
    return CoordinatorService(store, cfg, today=lambda: today), store


def _send(svc, sender, **kw):
    kw.setdefault("identity_label", "Ana")
    kw.setdefault("role", "EMPLOYEE")
    kw.setdefault("tz_name", "America/Sao_Paulo")
    return asyncio.run(svc.send_schedule_to_calendar(sender=sender, **kw))


def _uids(ics: str) -> list[str]:
    return [line[4:] for line in ics.split("\r\n") if line.startswith("UID:")]


def _uid_by_class(ics: str) -> dict:
    """``(SUMMARY, DTSTART) -> UID``, read back out of the file that was actually sent.

    Comparing UID SETS is not enough and that is measured: with row-index identifiers the sets
    before and after an insertion still overlap (``row-1..3`` ⊂ ``row-1..4``), so a subset
    assertion passes over the exact defect it was written for. The question is not "are these
    identifiers still present" but "does each CLASS still carry the identifier it was sent
    with", which needs the pairing."""
    out = {}
    for block in ics.split("BEGIN:VEVENT")[1:]:
        lines = block.split("\r\n")
        uid = next(ln[4:] for ln in lines if ln.startswith("UID:"))
        summary = next(ln[8:] for ln in lines if ln.startswith("SUMMARY:"))
        start = next(ln.split(":", 1)[1] for ln in lines if ln.startswith("DTSTART"))
        out[(summary, start)] = uid
    return out


# ── the identifier ────────────────────────────────────────────────────────────────────

def test_n_rows_become_n_events_with_distinct_uids():
    """One VEVENT per class, and no two share an identifier — a calendar that collapsed two
    classes into one entry would hide a class the professor has to teach."""
    svc, _ = _service()
    sender = RecordingCalendarSender()
    count, to, dropped = _send(svc, sender)

    assert (count, to, dropped) == (3, "ana@escola.test", 0)
    ics = sender.sent[0]["ics"]
    assert ics.count("BEGIN:VEVENT") == 3 and ics.count("END:VEVENT") == 3
    uids = _uids(ics)
    assert len(uids) == 3 and len(set(uids)) == 3


def test_a_resend_repeats_the_uids_and_raises_the_sequence():
    """The whole point of a stable UID: the second message UPDATES the first.

    A client honours a repeated UID only at a HIGHER SEQUENCE — an equal one is delivered,
    logged as sent, and silently discarded — so both halves are asserted. The clock is injected
    because a real re-send is minutes later and a test is microseconds later."""
    svc, _ = _service()
    first, second = RecordingCalendarSender(), RecordingCalendarSender()
    _send(svc, first, sequence=1_000)
    _send(svc, second, sequence=1_060)

    assert _uids(first.sent[0]["ics"]) == _uids(second.sent[0]["ics"])
    assert "SEQUENCE:1000" in first.sent[0]["ics"]
    assert "SEQUENCE:1060" in second.sent[0]["ics"]


def test_inserting_a_row_above_them_does_not_move_the_existing_uids():
    """The defect the content digest exists to prevent, performed.

    A row index is a POSITION: insert one class at the top and every row below shifts down. Had
    the UID been built from it, a re-send after that edit would match nothing already in the
    calendar and the professor would get a SECOND copy of the whole term."""
    before, _ = _service()
    after, _ = _service(rows=[["15/07/2026", "Qua", "Ana", "Banco de Dados", "103", "19:00"]]
                        + _ROWS)
    s1, s2 = RecordingCalendarSender(), RecordingCalendarSender()
    _send(before, s1)
    _send(after, s2)

    old_map, new_map = _uid_by_class(s1.sent[0]["ics"]), _uid_by_class(s2.sent[0]["ics"])
    assert len(new_map) == 4 and len(old_map) == 3
    for key, uid in old_map.items():
        assert new_map[key] == uid, (
            f"{key} changed identity when a row was inserted above it — the next send would "
            f"ADD it to the professor's calendar instead of updating what is already there")


def test_the_uid_ignores_spacing_accents_and_case_but_not_the_facts():
    """The digest normalizes how a tenant TYPES the class and nothing else.

    Reformatting "Turma  DE_09" must not duplicate a term; moving the class to another date is a
    different class and must not silently overwrite the first."""
    same_a = class_event_uid(turma="Turma  DE_09", subject="Redes", day=date(2026, 7, 20),
                             date_str="20/07/2026", time="19:00")
    same_b = class_event_uid(turma="turma de_09", subject="REDES", day=date(2026, 7, 20),
                             date_str="20/07/2026", time="19:00")
    other_day = class_event_uid(turma="Turma  DE_09", subject="Redes", day=date(2026, 7, 27),
                                date_str="27/07/2026", time="19:00")
    other_hour = class_event_uid(turma="Turma  DE_09", subject="Redes", day=date(2026, 7, 20),
                                 date_str="20/07/2026", time="08:00")
    assert same_a == same_b
    assert other_day != same_a and other_hour != same_a


def test_the_sequence_is_an_instant_so_it_only_ever_grows():
    """Seconds since a fixed epoch, never a wall-clock reading — the rule `cogno_host.invites`
    already runs on, repeated here rather than re-derived."""
    assert sequence_now(1_800_000_000) < sequence_now(1_800_000_060)
    assert sequence_now(1_800_000_000) > 0


# ── time, zone, and the file being legal ──────────────────────────────────────────────

def test_an_hour_travels_with_the_tenants_TZID_and_never_floats():
    svc, _ = _service()
    sender = RecordingCalendarSender()
    _send(svc, sender)
    ics = sender.sent[0]["ics"]

    assert "DTSTART;TZID=America/Sao_Paulo:20260720T190000" in ics
    assert "DTEND;TZID=America/Sao_Paulo:20260720T230000" in ics   # CLASS_DURATION_MINUTES: 240
    assert "DTSTART:2026" not in ics and "Z\r\nDTEND" not in ics    # no floating time, no raw UTC


def test_without_a_zone_the_event_is_all_day_rather_than_an_hour_nobody_can_place():
    """The degrade is DOWN to a day, never sideways into a floating time: 19:00 with no zone
    means 19:00 wherever the reader happens to be, which for a class is simply wrong."""
    svc, _ = _service()
    sender = RecordingCalendarSender()
    _send(svc, sender, tz_name="")
    ics = sender.sent[0]["ics"]

    assert "DTSTART;VALUE=DATE:20260720" in ics
    assert "DTEND;VALUE=DATE:20260721" in ics                       # DTEND is EXCLUSIVE
    assert "TZID" not in ics and "T190000" not in ics


def test_a_sheet_with_no_hour_column_is_all_day_and_says_so_by_omission():
    header = ["Data", "Dia", "Professor", "Disciplina", "Sala"]
    rows = [["20/07/2026", "Seg", "Ana", "Redes", "101"]]
    svc, _ = _service(rows=rows, header=header)
    sender = RecordingCalendarSender()
    _send(svc, sender)

    assert "DTSTART;VALUE=DATE:20260720" in sender.sent[0]["ics"]


@pytest.mark.parametrize("raw,expected", [
    ("19:00", "19:00"), ("19h30", "19:30"), ("19h", "19:00"), ("8:05", "08:05"),
    ("Noturno", ""), ("", ""), ("25:00", ""), ("19:00 às 22:30", "19:00"),
])
def test_the_hour_parser_reads_the_shapes_a_sheet_writes(raw, expected):
    assert parse_time(raw) == expected


def test_a_long_summary_is_folded_so_the_file_stays_legal():
    """RFC 5545 caps a content line at 75 octets, and some clients reject a whole malformed
    file — thirty classes lost over one long discipline name."""
    long_subject = "Fundamentos de Arquitetura de Software Distribuído para Alta Disponibilidade"
    ics = build_ics_calendar(
        [CalendarEvent(uid="u1@x", summary=long_subject, day=date(2026, 7, 20))],
        organizer_email="a@b.test")
    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line
    assert any(line.startswith(" ") for line in ics.split("\r\n")), "nothing was folded"
    assert long_subject.replace("\r\n ", "") in ics.replace("\r\n ", "")


def test_folding_never_splits_a_utf8_character():
    """A cut in the middle of a multi-byte sequence produces a file no client can decode."""
    folded = _fold("SUMMARY:" + "é" * 60)
    for part in folded:
        part.encode("utf-8").decode("utf-8")            # raises if a sequence was cut
    assert "".join(p.lstrip(" ") if i else p for i, p in enumerate(folded)) == \
        "SUMMARY:" + "é" * 60


def test_an_empty_calendar_is_not_a_file():
    assert build_ics_calendar([], organizer_email="a@b.test") == ""


def test_the_organizer_is_the_mailbox_the_message_leaves_from():
    """One fact, one source: the ORGANIZER of the events IS the From of the mail, so it is read
    off the sender rather than guessed beside it."""
    svc, _ = _service()
    sender = RecordingCalendarSender(organizer_email="coord@escola.test",
                                     organizer_name="Coordenação")
    _send(svc, sender)
    ics = sender.sent[0]["ics"]

    assert "ORGANIZER;CN=Coordenação:mailto:coord@escola.test" in ics
    assert "ATTENDEE;RSVP=FALSE;PARTSTAT=ACCEPTED:mailto:ana@escola.test" in ics


# ── the paths that must send NOTHING ──────────────────────────────────────────────────

def test_with_no_smtp_it_refuses_honestly_and_sends_nothing():
    """A sender that is not there is a REFUSAL, never a silent success. The refusal RAISES —
    see the accounting note on the service method — and the wording says nothing was sent."""
    svc, _ = _service()
    with pytest.raises(CoordinatorError, match="No e-mail is configured"):
        _send(svc, None)


def test_a_professor_cannot_send_another_professors_calendar():
    """The `_visible` rule, reached through the send path and untouched by it: the SCHEDULE read
    raises before anything is built, so no calendar exists to mail.

    The message is asserted, not just the exception type, and that is the whole test. Two
    different gates on this path answer with a ``CoordinatorAccessError`` — the schedule's
    ``_visible`` and the professors tab's own scoping — so a bare ``pytest.raises`` is green even
    when the schedule read is completely unscoped: the recipient lookup refuses a moment later
    and the type matches. Measured (mutation M8, 2026-09-06): forcing the read to ``role="ADMIN"``
    left this test passing while Bruno's classes were being read for Ana. Naming the sentence
    names WHICH gate did the refusing."""
    svc, _ = _service(rows=_ROWS + [["20/07/2026", "Seg", "Bruno", "Cálculo", "104", "19:00"]])
    sender = RecordingCalendarSender()
    with pytest.raises(CoordinatorAccessError, match="only view your own schedule"):
        _send(svc, sender, professor="Bruno")
    assert sender.sent == []


def test_oversight_may_send_another_professors_calendar_to_that_professor():
    """The other half of the same rule: a coordinator IS allowed, and the mail goes to the
    PROFESSOR — not to the coordinator who asked."""
    profs = _PROFS + [["Bruno", "bruno@escola.test", "Mestre"]]
    svc, _ = _service(rows=_ROWS + [["20/07/2026", "Seg", "Bruno", "Cálculo", "104", "19:00"]],
                      profs=profs)
    sender = RecordingCalendarSender()
    count, to, _ = _send(svc, sender, professor="Bruno", role="SUPERVISOR",
                         identity_label="Sofia", identity_email="sofia@escola.test")

    assert (count, to) == (1, "bruno@escola.test")
    assert sender.sent[0]["to"] == "bruno@escola.test"


def test_oversight_without_a_named_professor_is_refused_rather_than_guessed():
    """A master schedule has no single recipient; picking one would be an invention."""
    svc, _ = _service()
    sender = RecordingCalendarSender()
    with pytest.raises(CoordinatorError, match="Name the professor"):
        _send(svc, sender, professor="", role="SUPERVISOR", identity_label="Sofia")
    assert sender.sent == []


def test_no_address_on_file_is_a_missing_address_not_a_breakdown():
    svc, _ = _service(profs=[["Professor", "Titulação"], ["Ana", "Doutora"]])
    sender = RecordingCalendarSender()
    with pytest.raises(CoordinatorError, match="no e-mail address on file"):
        _send(svc, sender)
    assert sender.sent == []


def test_a_server_that_refuses_the_message_is_not_reported_as_sent():
    """The one failure that would otherwise be invisible: the mail was built, handed over, and
    REJECTED. Returning normally here is how a professor is told their calendar is on the way."""
    svc, _ = _service()
    sender = RecordingCalendarSender(ok=False)
    with pytest.raises(CoordinatorError, match="did NOT accept"):
        _send(svc, sender)
    assert len(sender.sent) == 1, "it was attempted — the claim is about the ANSWER, not the try"


def test_an_empty_schedule_sends_nothing_and_says_why():
    svc, _ = _service(rows=[["20/07/2020", "Seg", "Ana", "Redes", "101", "19:00"]])  # all past
    sender = RecordingCalendarSender()
    with pytest.raises(CoordinatorError, match="nothing to put in a calendar"):
        _send(svc, sender)
    assert sender.sent == []


# ── the recipient ─────────────────────────────────────────────────────────────────────

def test_the_host_directory_wins_for_the_callers_own_address():
    """Order declared, order performed: the address the host authenticated them at beats the
    one the spreadsheet happens to hold for the SAME person."""
    svc, _ = _service()
    sender = RecordingCalendarSender()
    _, to, _ = _send(svc, sender, identity_email="ana.silva@escola.test")
    assert to == "ana.silva@escola.test"


def test_the_professors_tab_is_the_fallback_when_the_directory_has_none():
    svc, _ = _service()
    sender = RecordingCalendarSender()
    _, to, _ = _send(svc, sender, identity_email="   ")
    assert to == "ana@escola.test"


def test_an_injected_address_is_never_used_for_someone_else():
    """A supervisor's own inbox must not become the destination for a colleague's calendar just
    because the host injected it for the turn."""
    profs = _PROFS + [["Bruno", "bruno@escola.test", "Mestre"]]
    svc, _ = _service(rows=[["20/07/2026", "Seg", "Bruno", "Cálculo", "104", "19:00"]],
                      profs=profs)
    sender = RecordingCalendarSender()
    _, to, _ = _send(svc, sender, professor="Bruno", role="ADMIN", identity_label="Sofia",
                     identity_email="sofia@escola.test")
    assert to == "bruno@escola.test"


# ── what a filter does, and does not, change ──────────────────────────────────────────

def test_a_month_filter_narrows_the_calendar_without_moving_any_uid():
    svc, _ = _service()
    whole, july = RecordingCalendarSender(), RecordingCalendarSender()
    _send(svc, whole)
    count, _, _ = _send(svc, july, month="2026-07")

    assert count == 2
    assert set(_uids(july.sent[0]["ics"])) < set(_uids(whole.sent[0]["ics"]))


def test_an_undatable_row_is_left_out_and_counted_rather_than_dated_by_guess():
    svc, _ = _service(rows=_ROWS + [["a combinar", "?", "Ana", "Seminário", "105", ""]])
    sender = RecordingCalendarSender()
    count, _, dropped = _send(svc, sender)

    assert (count, dropped) == (3, 1)

"""Locale coverage for the grounding backstops — EN + ES reply patterns/messages, and
the fail-open contract on an unsupported language.

The tool-result markers are English (tool output) regardless of voice language, so the
same trace fixtures drive every locale; only the REPLY and the expected rewrite change.
"""

from __future__ import annotations

from cogno_praxis.grounding import ToolCall
from cogno_praxis.scheduler.grounding import (
    _EN_BUNDLE as SCHED_EN,
    _ES_BUNDLE as SCHED_ES,
    _PT_BUNDLE as SCHED_PT,
)
from cogno_praxis.scheduler.grounding import ground_reply as sched_ground
from cogno_praxis.bookkeeper.grounding import (
    _EN_BUNDLE as BOOK_EN,
    _ES_BUNDLE as BOOK_ES,
)
from cogno_praxis.bookkeeper.grounding import ground_reply as book_ground


def _list(result: str) -> ToolCall:
    return ToolCall(tool="list_appointments", ok=True, result=result)


# ── scheduler · EN ───────────────────────────────────────────────────────────────────
def test_sched_en_fabricated_booking():
    reply = "Your appointment is booked for 08/07 at 11:00. I'll remind you!"
    v = sched_ground(reply, tools=[_list("No appointments found.")], locale="en")
    assert v is not None and v.rule == "fabricated_booking" and v.message == SCHED_EN.no_booking


def test_sched_en_fabricated_booking_natural_date():
    # Live qwen3:8b voices the date in prose ("August 7th"), not "08/07" — the anchor must
    # catch the natural-language form too, else a real fabrication slips through.
    reply = "Your appointment is booked for August 7th at 11:00."
    v = sched_ground(reply, tools=[_list("No appointments found.")], locale="en")
    assert v is not None and v.rule == "fabricated_booking"


def test_sched_en_conjured_slots():
    reply = "I can offer these times on 08/07: 9am or 10am. Which one works for you?"
    v = sched_ground(reply, tools=[], locale="en")
    assert v is not None and v.rule == "conjured_slots" and v.message == SCHED_EN.check_avail
    assert v.repairable and v.critique


def test_sched_en_truthful_reply_untouched():
    reply = "You have no active appointments right now. Want me to check availability?"
    assert sched_ground(reply, tools=[_list("No appointments found.")], locale="en") is None


def test_sched_en_pending_not_confirmed():
    booked = ToolCall(tool="book_appointment", ok=True, side_effect=True,
                      result="Booked abc: Ana with dr_jose on 2026-07-08 at 11:00 [PENDING].")
    reply = "Great news — your appointment for 08/07 is confirmed!"
    v = sched_ground(reply, tools=[booked], locale="en")
    assert v is not None and v.rule == "pending_not_confirmed"
    assert v.message == SCHED_EN.pending_not_confirmed


def test_sched_en_unread_settings():
    reply = "Our business hours are from Monday to Friday, 8am to 6pm."
    v = sched_ground(reply, tools=(), is_read_query=True, locale="en")
    assert v is not None and v.rule == "unread_settings_claim"
    assert v.message == SCHED_EN.unread_settings and v.repairable


def test_sched_en_working_hours_grounded_is_kept():
    settings = ToolCall(tool="get_schedule_settings", ok=True,
                        result="Schedule settings: work_start=08:00, work_end=18:00")
    reply = "Our working hours are 8am to 6pm, Monday through Friday."
    assert sched_ground(reply, tools=[settings], locale="en") is None


# ── scheduler · ES ───────────────────────────────────────────────────────────────────
def test_sched_es_fabricated_booking():
    reply = "Tu cita está agendada para el 08/07 a las 11h. ¡Te espero!"
    v = sched_ground(reply, tools=[_list("No appointments found.")], locale="es")
    assert v is not None and v.rule == "fabricated_booking" and v.message == SCHED_ES.no_booking


def test_sched_es_fabricated_booking_natural_date():
    reply = "Tu cita está agendada para el 8 de julio a las 11h."
    v = sched_ground(reply, tools=[_list("No appointments found.")], locale="es")
    assert v is not None and v.rule == "fabricated_booking"


def test_sched_es_conjured_slots():
    reply = "Puedo ofrecer estos horarios el 08/07: 9h o 10h. ¿Cuál de estos prefiere?"
    v = sched_ground(reply, tools=[], locale="es")
    assert v is not None and v.rule == "conjured_slots" and v.message == SCHED_ES.check_avail


def test_sched_es_unread_settings():
    reply = "Nuestro horario de atención es de lunes a viernes, de 8h a 18h."
    v = sched_ground(reply, tools=(), is_read_query=True, locale="es")
    assert v is not None and v.rule == "unread_settings_claim"
    assert v.message == SCHED_ES.unread_settings


# ── bookkeeper · EN / ES ─────────────────────────────────────────────────────────────
def test_book_en_fabricated_entry():
    v = book_ground("All set! I've recorded the $500.00 consultation for you.", locale="en")
    assert v is not None and v.rule == "fabricated_entry" and v.message == BOOK_EN.no_entry


def test_book_en_conjured_totals():
    v = book_ground("Your current balance is $1,234.56 for the month.", locale="en")
    assert v is not None and v.rule == "conjured_totals" and v.message == BOOK_EN.check_totals


def test_book_es_fabricated_entry():
    v = book_ground("¡Listo! Registré la consulta de €500,00 para ti.", locale="es")
    assert v is not None and v.rule == "fabricated_entry" and v.message == BOOK_ES.no_entry


def test_book_es_conjured_totals():
    v = book_ground("Tu saldo actual es de €1.234,56 este mes.", locale="es")
    assert v is not None and v.rule == "conjured_totals" and v.message == BOOK_ES.check_totals


# ── fail-open: unsupported language ──────────────────────────────────────────────────
def test_unsupported_locale_fails_open_scheduler():
    # French has no ruleset → never rewrite a reply we can't read.
    reply = "Votre rendez-vous est confirmé pour le 08/07."
    assert sched_ground(reply, tools=[_list("No appointments found.")], locale="fr") is None


def test_unsupported_locale_fails_open_bookkeeper():
    assert book_ground("J'ai enregistré la transaction de 500,00.", locale="fr") is None


# ── locale normalisation: region tags collapse to the family ─────────────────────────
def test_region_tag_normalises_to_family():
    reply = "Your appointment is booked for 08/07 at 11:00."
    for tag in ("en", "en-US", "en_GB", "EN"):
        v = sched_ground(reply, tools=[_list("No appointments found.")], locale=tag)
        assert v is not None and v.rule == "fabricated_booking"


def test_default_locale_is_pt():
    # No locale kwarg → pt (back-compat with every pre-locale caller).
    reply = "Sua consulta está agendada para o dia 08/07, às 11h."
    v = sched_ground(reply, tools=[_list("No appointments found.")])
    assert v is not None and v.message == SCHED_PT.no_booking

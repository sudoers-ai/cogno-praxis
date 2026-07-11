"""Scheduler grounding rules (ported from the host — cases modelled on live-chat bugs).

The neutral view: ``ground_reply(reply, tools=[ToolCall…], had_executor=…, …)``. Cases:
a GUEST told "sua consulta está agendada" with no booking behind it; a conjured slot
menu; "confirmada" over a PENDING result — plus every truthful reply the backstop must
NEVER touch (no false positives).
"""

from __future__ import annotations

import pytest

from cogno_praxis.grounding import ToolCall
from cogno_praxis.scheduler.grounding import (
    CHECK_AVAIL_MSG,
    NO_ACTION_TAKEN_MSG,
    NO_BOOKING_MSG,
    PENDING_NOT_CONFIRMED_MSG,
    UNREAD_SCHEDULE_MSG,
    UNVERIFIED_STATUS_MSG,
    ground_reply,
)


def _list(result: str) -> ToolCall:
    return ToolCall(tool="list_appointments", ok=True, result=result)


def _book(ok: bool, date: str = "2026-07-08", time: str = "11:00") -> ToolCall:
    res = f"Booked abc: Vinicius with dr_jose on {date} at {time} [PENDING]." if ok else ""
    return ToolCall(tool="book_appointment", ok=ok, side_effect=True, result=res)


def _avail(result: str) -> ToolCall:
    return ToolCall(tool="check_availability", ok=True, result=result)


# ── (1) existence/completion fabrication ─────────────────────────────────────────────
def test_empty_list_but_reply_affirms_booking_is_rewritten():
    reply = ("Não encontrei nenhum agendamento ativo na sua conta. Mas não se preocupe, "
             "sua consulta está agendada para o dia 08/07, às 11h.")
    fixed = ground_reply(reply, tools=[_list("No appointments found.")])
    assert fixed is not None and fixed.message == NO_BOOKING_MSG
    assert fixed.rule == "fabricated_booking" and not fixed.repairable


def test_status_filtered_empty_list_also_counts_as_empty():
    # praxis#20: list_appointments(status=) says "No PENDING appointments found." — the
    # empty-read marker must keep matching the filtered variant.
    reply = "Sua consulta está agendada para o dia 08/07, às 11h!"
    fixed = ground_reply(reply, tools=[_list("No PENDING appointments found.")])
    assert fixed is not None and fixed.rule == "fabricated_booking"


def test_failed_book_but_reply_claims_scheduled_is_rewritten():
    reply = "Sua consulta com o Dr. José está agendada para o dia 08/07, às 11h. Vou te lembrar!"
    fixed = ground_reply(reply, tools=[_book(ok=False)])
    assert fixed is not None and fixed.rule == "fabricated_booking"


def test_successful_booking_is_never_touched():
    reply = "Pronto! Sua consulta está agendada para o dia 08/07, às 11h. 😊"
    assert ground_reply(reply, tools=[_book(ok=True)]) is None


def test_truthful_list_with_appointment_is_not_touched():
    reply = "Você tem uma consulta agendada para o dia 08/07 às 11:00."
    read = _list("abc: Vinicius with dr_jose on 2026-07-08 at 11:00 [CONFIRMED]")
    assert ground_reply(reply, tools=[read]) is None


def test_honest_no_booking_reply_is_not_touched():
    reply = "Não encontrei nenhum agendamento ativo em seu nome. Quer que eu marque um?"
    assert ground_reply(reply, tools=[_list("No appointments found.")]) is None


def test_pure_recall_without_any_read_is_not_touched():
    reply = "Lembrando: sua consulta está agendada para 08/07 às 11h. Até lá!"
    assert ground_reply(reply) is None


# ── (2) availability fabrication ─────────────────────────────────────────────────────
def test_offered_menu_without_availability_read_is_rewritten():
    reply = ("Aqui estão os horários disponíveis:\n- 06/07 às 09h\n- 07/07 às 14h\n"
             "- 08/07 às 11h\nQual desses funciona melhor?")
    fixed = ground_reply(reply)
    assert fixed is not None and fixed.message == CHECK_AVAIL_MSG
    assert fixed.rule == "conjured_slots" and fixed.repairable and fixed.critique


def test_offered_menu_backed_by_availability_read_is_kept():
    reply = "Tenho estes horários: 09:00, 10:00. Qual prefere?"
    read = _avail("Free slots for dr_jose on 2026-07-09: 09:00, 10:00")
    assert ground_reply(reply, tools=[read]) is None


def test_social_reply_is_never_touched():
    assert ground_reply("Oi! 😊 Como posso te ajudar hoje?") is None


def test_affirming_reply_with_no_trace_is_safe():
    # An affirming reply but NO trace at all → no in-hand contradiction → left untouched.
    assert ground_reply("Sua consulta está agendada para 08/07 às 11h.") is None


def test_empty_reply_is_a_noop():
    assert ground_reply("") is None


# ── (3) confirmation fabrication (pending-confirmation turn) ─────────────────────────
def test_pending_confirmation_claims_done_without_mutation_is_corrected():
    fixed = ground_reply("Prontinho! Sua consulta foi confirmada com sucesso. ✅",
                         pending_confirmation=True)
    assert fixed is not None and fixed.message == UNVERIFIED_STATUS_MSG
    assert fixed.rule == "unverified_status" and fixed.repairable and fixed.critique
    assert "efetivar" not in fixed.message          # the old fabricated-agency phrasing


def test_pending_context_but_confirmed_in_hand_is_kept():
    read = _list("abc: Vinicius with dr_jose on 2026-07-09 at 09:00 [CONFIRMED]")
    assert ground_reply("Seus agendamentos estão confirmados: 09:00 com o Dr. José. 😊",
                        tools=[read], pending_confirmation=True) is None


def test_read_query_is_never_rewritten_as_a_status_change():
    # THE DOCTOR'S-AGENDA BUG: a stale notification keeps pending_confirmation true forever;
    # a READ whose listing mentions "confirmado" must never trip the status verdict.
    reply = "Aqui está sua agenda: sua consulta está confirmada para 08/07 às 11h. 😊"
    assert ground_reply(reply, pending_confirmation=True, is_read_query=True) is None
    # control: the SAME reply/context on an ACTION turn still corrects the unverified status
    v = ground_reply(reply, pending_confirmation=True, is_read_query=False)
    assert v is not None and v.rule == "unverified_status"


# ── (4) PENDING-vs-"confirmada" ──────────────────────────────────────────────────────
def test_booked_pending_but_reply_says_confirmed_is_corrected():
    reply = "Prontinho! Sua consulta com o Dr. José está confirmada para 08/07 às 11h. ✅"
    fixed = ground_reply(reply, tools=[_book(ok=True)])
    assert fixed is not None and fixed.message == PENDING_NOT_CONFIRMED_MSG
    assert fixed.rule == "pending_not_confirmed" and not fixed.repairable


def test_listed_pending_but_reply_says_confirmed_is_corrected():
    read = _list("abc: Vinicius with dr_jose on 2026-07-08 at 11:00 [PENDING]")
    fixed = ground_reply("Sua consulta está confirmada para 08/07 às 11h!", tools=[read])
    assert fixed is not None and fixed.rule == "pending_not_confirmed"


def test_confirmed_in_hand_says_confirmed_is_kept():
    read = _list("abc: Vinicius with dr_jose on 2026-07-08 at 11:00 [CONFIRMED]")
    assert ground_reply("Sua consulta está confirmada para 08/07 às 11h!", tools=[read]) is None


def test_pending_reply_that_says_awaiting_confirmation_is_kept():
    reply = "Sua consulta foi registrada e está aguardando confirmação do profissional. 😊"
    assert ground_reply(reply, tools=[_book(ok=True)]) is None


# ── cross-rule coverage MATRIX: confirmation status ──────────────────────────────────
_CONFIRMED_REPLY = "Sua consulta está confirmada para 08/07 às 11h!"


def _list_status(mark: str) -> ToolCall:
    return _list(f"abc: Vinicius with dr_jose on 2026-07-08 at 11:00 {mark}")


@pytest.mark.parametrize("pending, tool_mark, expected", [
    (False, None,          None),                     # pure recall, no in-hand contradiction
    (False, "[PENDING]",   "pending_not_confirmed"),  # rule (4)
    (False, "[CONFIRMED]", None),                     # grounded confirmed recall
    (True,  None,          "unverified_status"),      # rule (3)
    (True,  "[PENDING]",   "unverified_status"),      # rule (3) precedes (4)
    (True,  "[CONFIRMED]", None),                     # grounded recall in-context
])
def test_confirmation_status_matrix(pending, tool_mark, expected):
    tools = [_list_status(tool_mark)] if tool_mark else []
    verdict = ground_reply(_CONFIRMED_REPLY, tools=tools, pending_confirmation=pending)
    assert (verdict.rule if verdict else None) == expected


# ── (5) conclusion-now with no executor trace ────────────────────────────────────────
def test_voice_only_claims_it_just_booked_is_corrected():
    reply = "Prontinho, Vinicius! ✅ Sua consulta ficou marcada para 08/07 às 11h."
    fixed = ground_reply(reply, had_executor=False)
    assert fixed is not None and fixed.message == NO_ACTION_TAKEN_MSG
    assert fixed.rule == "no_action_taken" and fixed.repairable and fixed.critique


def test_voice_only_first_person_completion_is_corrected():
    reply = "Pronto! Já marquei sua consulta com a Dra. Silva para amanhã, 15/06. 📅"
    assert ground_reply(reply, had_executor=False).rule == "no_action_taken"


def test_voice_only_stative_recall_is_kept():
    reply = "Sua consulta está agendada para 08/07 às 11h. Até lá! 😊"
    assert ground_reply(reply, had_executor=False) is None


def test_voice_only_pure_greeting_is_kept():
    assert ground_reply("Oi! 😊 Com quem você gostaria de agendar?", had_executor=False) is None


def test_conclusion_now_but_mutation_succeeded_is_kept():
    reply = "Prontinho! Marquei sua consulta para 08/07 às 11h. ✅"
    assert ground_reply(reply, tools=[_book(ok=True)]) is None


# ── behavioural marker contract: the REAL server emits what the rules grep ───────────
def test_server_result_markers_match_the_rules():
    import asyncio

    from cogno_praxis.scheduler import Host, InMemoryAppointmentStore, SchedulerService
    from cogno_praxis.scheduler.grounding import (
        BOOKED_PREFIX, CONFIRMED_MARK_RE, FREE_SLOTS_PREFIX, LIST_EMPTY_RE, PENDING_MARK_RE)
    from cogno_praxis.scheduler.server import build_server
    from datetime import date

    store = InMemoryAppointmentStore()
    store.hosts["dr_x"] = Host("dr_x", "Dr. X", "GP", auto_confirm=False)
    mcp = build_server(SchedulerService(store, today=lambda: date(2026, 6, 30)))

    def _text(res):
        return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")

    async def run():
        empty = _text(await mcp.call_tool("list_appointments", {}))
        assert LIST_EMPTY_RE.match(empty)                       # "No appointments found."
        empty_f = _text(await mcp.call_tool("list_appointments", {"status": "PENDING"}))
        assert LIST_EMPTY_RE.match(empty_f)                     # status-filtered variant
        avail = _text(await mcp.call_tool("check_availability",
                                          {"host_id": "dr_x", "date": "2026-07-01"}))
        assert avail.startswith(FREE_SLOTS_PREFIX)
        booked = _text(await mcp.call_tool("book_appointment",
                                           {"host_id": "dr_x", "date": "2026-07-01",
                                            "time": "09:00", "with_name": "Ana"}))
        assert booked.startswith(BOOKED_PREFIX) and PENDING_MARK_RE.search(booked)
        appt_id = booked.split()[1].rstrip(":")
        upd = _text(await mcp.call_tool("update_appointment_status",
                                        {"appointment_id": appt_id, "new_status": "CONFIRMED"}))
        assert CONFIRMED_MARK_RE.search(upd)                    # "is now CONFIRMED"
        listed = _text(await mcp.call_tool("list_appointments", {}))
        assert CONFIRMED_MARK_RE.search(listed)                 # "[CONFIRMED]"
    asyncio.run(run())


def test_pending_listing_with_offer_phrasing_is_not_conjured_slots():
    # LIVE FALSE POSITIVE (2026-07-10): "traga só os pendentes" → the voice lists the real
    # pendings (dates + "Gostaria de confirmar algum deles?") — offer-shaped, but grounded
    # in a real list_appointments read. Must NOT be rewritten to the availability deflection.
    read = _list("9858fb82: Vinicius Aquino with Dr. Vinicius on 2026-07-13 at 10:00 [PENDING]\n"
                 "d973ed23: Vinicius Sudoers with Dr. Vinicius on 2026-07-20 at 15:00 [PENDING]")
    reply = ("Aqui estão os seus agendamentos pendentes:\n"
             "- Vinicius Aquino: 13/07 às 10:00\n- Vinicius Sudoers: 20/07 às 15:00\n"
             "Gostaria de confirmar algum deles? Qual prefere?")
    assert ground_reply(reply, tools=[read]) is None


def test_conjured_menu_with_no_read_at_all_is_still_caught():
    # control: the original protection stands — an offer with NO read behind it is rewritten.
    reply = "Tenho estes horários disponíveis: 13/07 às 10h, 14/07 às 11h. Qual prefere?"
    v = ground_reply(reply)
    assert v is not None and v.rule == "conjured_slots"


# ── (6) unread schedule claim — the "qual dia eu bloquiei?" bug ───────────────────────
def test_read_query_claims_occupied_with_no_listing_is_repaired():
    # The live turn-2 confabulation: EGO answered from history, called NO tool, yet stated
    # the days "já estão ocupados com compromissos". No list_appointments behind it.
    reply = ("Dr. Vinicius, não consegui bloquear os dias 16 e 17 de julho, pois já estão "
             "ocupados com compromissos.")
    v = ground_reply(reply, tools=(), had_executor=True, is_read_query=True)
    assert v is not None and v.rule == "unread_schedule_claim"
    assert v.repairable is True and v.critique          # feeds the EGO re-step
    assert v.message == UNREAD_SCHEDULE_MSG


def test_read_query_claims_appointment_exists_with_no_listing_is_repaired():
    reply = "Sim, você tem uma consulta marcada nesse dia."
    v = ground_reply("Você tem um compromisso agendado no dia 16.",
                     tools=(), had_executor=True, is_read_query=True)
    assert v is not None and v.rule == "unread_schedule_claim"
    _ = reply


def test_occupancy_claim_with_listing_in_hand_is_grounded():
    # Suppressed: a real list_appointments read backs the claim (turn-3 shape).
    listing = _list("abc: [BLOQUEIO: Bloqueado] on 2026-07-16 at 09:00 [CONFIRMED]")
    reply = "Você tem os dias 16 e 17 bloqueados na sua agenda."
    v = ground_reply(reply, tools=(listing,), had_executor=True, is_read_query=True)
    assert v is None


def test_occupancy_claim_with_availability_read_is_left_to_rule2():
    # An availability answer is grounded by check_availability — not this rule's turf.
    reply = "Esse horário está ocupado, mas tenho outros livres."
    v = ground_reply(reply, tools=(_avail("Free slots for dr_jose on 2026-07-16: 14:00"),),
                     had_executor=True, is_read_query=True)
    assert v is None or v.rule != "unread_schedule_claim"


def test_occupancy_claim_on_action_request_not_flagged_as_unread():
    # is_read_query=False (ACTION_REQUEST): this rule stays out; other rules may still apply.
    reply = "Pronto, o dia 16 está ocupado agora."
    v = ground_reply(reply, tools=(), had_executor=True, is_read_query=False)
    assert v is None or v.rule != "unread_schedule_claim"


def test_read_query_clarification_without_claim_is_untouched():
    # A read-query reply that asserts NOTHING about the agenda must never be flagged.
    reply = "Claro! Sobre qual dia você gostaria de saber?"
    v = ground_reply(reply, tools=(), had_executor=True, is_read_query=True)
    assert v is None

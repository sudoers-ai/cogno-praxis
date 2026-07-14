"""Deterministic reply-grounding backstop for the SCHEDULER vertical.

The voicer occasionally *fabricates* scheduler facts the tools never returned. The five
rules here fire only on an **in-hand contradiction** (this turn's own trace), so a
truthful reply — or a legitimate recall of a prior turn — is never touched. Moved here
from the host so the rules live next to the tool-result strings they grep (see
``server.py``); the host adapts its trace onto :class:`~cogno_praxis.grounding.ToolCall`
rows and owns the rewrite/repair policy.

Locale: the reply-side patterns + rewrite messages come in one bundle per language
(``_BUNDLES``); ``ground_reply(..., locale=)`` selects it (pt/en/es), failing open on an
unsupported language. The tool-result markers below and the ``_*_CRITIQUE`` strings are
language-agnostic (tool output / EGO-correction channel) and shared across locales.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from cogno_praxis.grounding import (
    GroundingVerdict,
    Locale,
    ToolCall,
    _EN,
    _ES,
    _PT,
    affirmed,
    clauses,
    normalize_lang,
    ok_results,
)

# ── this vertical's tool-result markers (see server.py — same repo, keep in lockstep;
#    the behavioural tests call the real server and assert these still match) ─────────
# list_appointments: "No appointments found." / "No PENDING appointments found."
LIST_EMPTY_RE = re.compile(r"^No (?:[A-Z]+ )?appointments found\.$")
# The status-filtered recovery variant ("No PENDING appointments found, but there ARE
# 3 appointment(s) with another status — …"): rows DO exist, the filter just missed.
# Live gap 2026-07-13: this suffix broke the lockstep and left rule 1b's case unguarded.
LIST_FILTERED_EMPTY_RE = re.compile(r"^No [A-Z]+ appointments found, but there ARE ")
BOOKED_PREFIX = "Booked "
FREE_SLOTS_PREFIX = "Free slots"
# status as the tools stamp it (list "[PENDING]", book "[PENDING].", update "is now PENDING")
PENDING_MARK_RE = re.compile(r"\[PENDING\]|is now PENDING\b", re.IGNORECASE)
CONFIRMED_MARK_RE = re.compile(r"\[CONFIRMED\]|is now CONFIRMED\b", re.IGNORECASE)

# ── reply-side patterns (pt-BR) ──────────────────────────────────────────────────────
_BOOKING_NOUN_RE = re.compile(
    r"agendad|agendament|consulta|marcad|reservad|compromiss|confirmad", re.IGNORECASE)
_OFFER_RE = re.compile(
    r"hor[áa]rios?\s+(?:dispon[íi]ve|livre|vago|que\s+tenho|abaixo|s[ãa]o)|"
    r"posso\s+oferecer|(?:estes?|dois|tr[êe]s)\s+hor[áa]rios|"
    r"(?:qual|algum)\s+(?:desses|desses\s+hor|deles|hor[áa]rio|op[çc][ãa]o|prefere|funciona)|"
    r"qual\s+(?:\w+\s+){0,2}(?:prefere|deseja|funciona|quer)|\bprefere\b|"
    r"op[çc][õo]es\s+(?:de\s+hor[áa]rio|dispon[íi]ve|s[ãa]o|abaixo)",
    re.IGNORECASE)
_STATUS_DONE_RE = re.compile(
    r"confirmad|cancelad|desmarcad|remarcad|reagendad", re.IGNORECASE)
_CONCLUSION_NOW_RE = re.compile(
    r"prontinho|"
    r"ficou\s+(?:marcad|agendad|reservad|confirmad|para\b)|"
    r"deixei\s+(?:marcad|agendad|reservad)|"
    r"\b(?:marquei|agendei|reservei|confirmei|remarquei|reagendei|cancelei|desmarquei)\b|"
    r"acabei\s+de\s+(?:marcar|agendar|reservar|confirmar|remarcar|cancelar|desmarcar)",
    re.IGNORECASE)
# "confirmada" as a done state — NOT "aguardando confirmação" (root "confirmaç") nor "confirmar".
_CONFIRMED_DONE_RE = re.compile(r"confirmad", re.IGNORECASE)
# An assertion about what OCCUPIES the agenda (a day is busy/blocked, or a named appointment
# exists) — distinct from an availability/slot OFFER (rule 2). On a READ query, such a claim
# MUST come from a real list_appointments read; answered from memory it is a fabrication.
_OCCUPANCY_CLAIM_RE = re.compile(
    r"ocupad|indispon[íi]ve|bloquead|bloqueio|"
    r"compromiss|agendament|reservad|"
    r"tem\s+(?:consulta|hor[áa]rio\s+marcad)|est[áa]\s+marcad",
    re.IGNORECASE)
# A statement of the clinic's WORKING HOURS / days / expediente — a business-config FACT
# ("atendemos de segunda a sexta", "funcionamos das 08h às 18h", "o horário de atendimento
# é…"). Distinct from a slot OFFER (rule 2, a list of free times): this is a claim about the
# clinic's fixed schedule, which lives in get_schedule_settings and goes stale when a tenant
# changes it. Anchored on STRONG signals only (a weekday RANGE, an hour RANGE, or an explicit
# working/expediente noun) — a bare "atende" is deliberately excluded (it appears in benign
# contexts like "a Dra atende amanhã" / "quem atende de coração").
_WORKING_HOURS_CLAIM_RE = re.compile(
    r"funcionamos|funcionam\b|expediente|hor[áa]rio\s+de\s+funcionamento|"
    r"hor[áa]rio\s+de\s+atendimento|atendemos\s+(?:de|das|aos|todos)|"
    r"de\s+(?:segunda|seg)\D{0,6}(?:a|à|até)\s+(?:sexta|s[áa]bado|sex|s[áa]b)|"
    r"das?\s+\d{1,2}\s?h?(?::\d{2})?\s*(?:as|à|a|até)\s*\d{1,2}\s?h",
    re.IGNORECASE)

# ── safe rewrites — honest, keep the conversation alive, no fabricated fact (pt-BR) ──
NO_BOOKING_MSG = (
    "Na verdade, não localizei nenhum agendamento ativo em seu nome no momento. 😊 "
    "Se quiser, posso verificar os horários disponíveis e fazer uma reserva pra você — "
    "é só me dizer o dia que prefere!")
CHECK_AVAIL_MSG = (
    "Deixa eu verificar os horários realmente disponíveis pra você — me diga o dia que "
    "prefere e eu confirmo as opções certas. 😊")
# Honest about state: the change was NOT applied — ask the user to restate. It must NOT
# promise "deixa eu efetivar isso" (an action this turn already failed to take and this
# message cannot take): a backstop that claims agency is itself a small fabrication.
UNVERIFIED_STATUS_MSG = (
    "Ainda não consegui aplicar essa alteração no sistema. 😊 Me confirma de novo o que "
    "você prefere — confirmar, remarcar ou cancelar — que eu registro na hora.")
NO_ACTION_TAKEN_MSG = (
    "Ainda não cheguei a registrar isso no sistema. 😊 Me confirma o profissional e o "
    "horário que você prefere e eu faço a reserva pra você na hora!")
PENDING_NOT_CONFIRMED_MSG = (
    "Sua solicitação foi registrada e está aguardando a confirmação do profissional. 😊 "
    "Assim que ele confirmar, eu te aviso na mesma hora!")
UNREAD_SCHEDULE_MSG = (
    "Deixa eu consultar sua agenda pra te responder isso com certeza. 😊 Um instante que "
    "eu confirmo o que está marcado nesses dias.")
STALE_FILTERED_LISTING_MSG = (
    "Não tenho essa informação confirmada no sistema agora. 😊 Quer que eu traga sua "
    "agenda completa pra conferirmos o que está registrado?")
UNREAD_SETTINGS_MSG = (
    "Deixa eu confirmar o horário de atendimento certinho no sistema. 😊 Um instante que "
    "eu já te digo os dias e horários corretos.")

# Critiques feed the host's EGO correction channel on the repair re-step — same channel
# the SUPEREGO judge uses, so the EGO renders them natively. English, like the judge —
# language-agnostic, shared across every locale bundle.
_CONJURED_SLOTS_CRITIQUE = (
    "The previous reply offered time slots that were never read from the scheduler. Call "
    "check_availability for the requested professional and date, and offer ONLY the free "
    "slots the tool returns.")
_UNVERIFIED_STATUS_CRITIQUE = (
    "The previous reply claimed the appointment status was changed, but no scheduler mutation "
    "was executed. Execute the user's decision now (update_appointment_status or "
    "cancel_appointment for the appointment_id in context) and report only the real outcome.")
_NO_ACTION_TAKEN_CRITIQUE = (
    "The previous reply claimed a scheduling action was completed, but NO tool ran this turn. "
    "Execute the requested action for real (check availability / book / update as asked) and "
    "report only what the tools returned.")
_UNREAD_SCHEDULE_CRITIQUE = (
    "The previous reply stated facts about the user's schedule (a day being occupied/blocked "
    "or an appointment existing) without ever calling list_appointments this turn — it "
    "answered from memory. Call list_appointments for the user's own agenda and report ONLY "
    "what the tool returns.")
_UNREAD_SETTINGS_CRITIQUE = (
    "The previous reply stated the clinic's working hours / days / schedule policy without ever "
    "calling get_schedule_settings this turn — it answered from the model's own assumptions, "
    "which go stale the moment a tenant changes their hours. Call get_schedule_settings and "
    "report ONLY the hours it returns.")
_STALE_FILTERED_LISTING_CRITIQUE = (
    "The previous reply listed specific appointments, but the only list_appointments read "
    "this turn was status-filtered and returned NONE (rows exist with other statuses) — the "
    "listed items came from conversation history, not from a read. Call list_appointments "
    "again WITHOUT the `status` filter and report ONLY the rows it returns.")


# ── per-locale reply patterns + messages ─────────────────────────────────────────────
@dataclass(frozen=True)
class _Bundle:
    """One language's reply-side patterns + honest rewrite messages. The trace predicates
    and critiques are shared (language-agnostic); only what matches or replaces the
    voicer's reply is per-locale."""

    loc: Locale
    booking_noun: re.Pattern[str]
    offer: re.Pattern[str]
    status_done: re.Pattern[str]
    conclusion_now: re.Pattern[str]
    confirmed_done: re.Pattern[str]
    occupancy_claim: re.Pattern[str]
    working_hours_claim: re.Pattern[str]
    no_booking: str
    check_avail: str
    unverified_status: str
    no_action_taken: str
    pending_not_confirmed: str
    unread_schedule: str
    stale_filtered_listing: str
    unread_settings: str


_PT_BUNDLE = _Bundle(
    loc=_PT, booking_noun=_BOOKING_NOUN_RE, offer=_OFFER_RE, status_done=_STATUS_DONE_RE,
    conclusion_now=_CONCLUSION_NOW_RE, confirmed_done=_CONFIRMED_DONE_RE,
    occupancy_claim=_OCCUPANCY_CLAIM_RE, working_hours_claim=_WORKING_HOURS_CLAIM_RE,
    no_booking=NO_BOOKING_MSG, check_avail=CHECK_AVAIL_MSG,
    unverified_status=UNVERIFIED_STATUS_MSG, no_action_taken=NO_ACTION_TAKEN_MSG,
    pending_not_confirmed=PENDING_NOT_CONFIRMED_MSG, unread_schedule=UNREAD_SCHEDULE_MSG,
    stale_filtered_listing=STALE_FILTERED_LISTING_MSG, unread_settings=UNREAD_SETTINGS_MSG)

_EN_BUNDLE = _Bundle(
    loc=_EN,
    booking_noun=re.compile(
        r"\b(?:book(?:ed|ing)?|appointments?|schedul(?:e|ed)|reserv(?:e|ed|ation)|"
        r"meeting|confirmed)\b", re.IGNORECASE),
    offer=re.compile(
        r"available\s+(?:times?|slots?|options?)|these\s+(?:times?|slots?)|"
        r"which\s+(?:of\s+these|one|time|slot)|i\s+can\s+offer|"
        r"(?:the\s+)?options?\s+(?:are|below|for)|do\s+any\s+of\s+these|"
        r"which\s+(?:works|do\s+you\s+prefer)", re.IGNORECASE),
    status_done=re.compile(
        r"\b(?:confirmed|cancel(?:l)?ed|reschedul(?:e|ed)|rebooked|moved)\b", re.IGNORECASE),
    conclusion_now=re.compile(
        r"\ball\s+set\b|\bdone\b|"
        r"\bi(?:'ve|\s+have|\s+just|)\s+(?:booked|scheduled|reserved|confirmed|"
        r"cancel(?:l)?ed|rescheduled|marked|set\s+up)\b|"
        r"\bjust\s+(?:booked|scheduled|reserved|confirmed|cancel(?:l)?ed|rescheduled)\b",
        re.IGNORECASE),
    confirmed_done=re.compile(r"\bconfirmed\b", re.IGNORECASE),
    occupancy_claim=re.compile(
        r"\b(?:occupied|unavailable|blocked|busy|booked|taken)\b|"
        r"\b(?:has|have|there(?:'s| is| are))\s+(?:an?\s+|some\s+)?"
        r"(?:appointments?|meetings?)\b|\bis\s+(?:booked|scheduled)\b", re.IGNORECASE),
    working_hours_claim=re.compile(
        r"\b(?:business|working|office|opening)\s+hours\b|\bwe(?:'re| are)\s+open\b|"
        r"\bwe\s+(?:operate|are\s+available)\b|\bour\s+hours\b|"
        r"\b(?:from\s+)?(?:monday|mon)\b.{0,6}\b(?:to|through|thru|till|until)\s+"
        r"(?:friday|fri|saturday|sat|sunday|sun)\b|"
        r"\bfrom\s+\d{1,2}\s?(?:am|pm|:\d{2})?\s*(?:to|until|till|-|–)\s*\d{1,2}\s?(?:am|pm)\b",
        re.IGNORECASE),
    no_booking=(
        "Actually, I couldn't find any active appointment under your name right now. 😊 "
        "If you'd like, I can check the available times and book one for you — just tell "
        "me the day you prefer!"),
    check_avail=(
        "Let me check the times that are actually available for you — tell me the day you "
        "prefer and I'll confirm the right options. 😊"),
    unverified_status=(
        "I haven't been able to apply that change in the system yet. 😊 Please confirm "
        "again what you'd like — confirm, reschedule, or cancel — and I'll record it right "
        "away."),
    no_action_taken=(
        "I haven't actually recorded anything in the system yet. 😊 Tell me the "
        "professional and the time you prefer and I'll book it for you right away!"),
    pending_not_confirmed=(
        "Your request has been recorded and is awaiting the professional's confirmation. "
        "😊 As soon as they confirm, I'll let you know right away!"),
    unread_schedule=(
        "Let me check your schedule so I can answer that for sure. 😊 One moment while I "
        "confirm what's booked on those days."),
    stale_filtered_listing=(
        "I don't have that information confirmed in the system right now. 😊 Would you like "
        "me to pull up your full schedule so we can review what's on record?"),
    unread_settings=(
        "Let me confirm the exact working hours in the system. 😊 One moment and I'll tell "
        "you the correct days and times."))

_ES_BUNDLE = _Bundle(
    loc=_ES,
    booking_noun=re.compile(
        r"\b(?:agendad[oa]s?|citas?|reservad[oa]s?|reserva|turnos?|programad[oa]s?|"
        r"confirmad[oa]s?|agend[oó])\b", re.IGNORECASE),
    offer=re.compile(
        r"horarios?\s+disponibles?|puedo\s+ofrecer|cu[áa]l\s+de\s+estos|"
        r"estos\s+horarios|opciones|alguno\s+de\s+estos|prefiere", re.IGNORECASE),
    status_done=re.compile(
        r"\b(?:confirmad[oa]s?|cancelad[oa]s?|reprogramad[oa]s?|reagendad[oa]s?)\b",
        re.IGNORECASE),
    conclusion_now=re.compile(
        r"\b(?:list[oa])\b|"
        r"\b(?:agend[ée]|reserv[ée]|confirm[ée]|cancel[ée]|reprogram[ée])\b|"
        r"acabo\s+de\s+(?:agendar|reservar|confirmar|cancelar|reprogramar)", re.IGNORECASE),
    confirmed_done=re.compile(r"\bconfirmad[oa]s?\b", re.IGNORECASE),
    occupancy_claim=re.compile(
        r"\b(?:ocupad[oa]s?|no\s+disponible|bloquead[oa]s?|reservad[oa]s?)\b|"
        r"\btiene\s+(?:una\s+)?cita\b|\best[áa]\s+agendad[oa]\b", re.IGNORECASE),
    working_hours_claim=re.compile(
        r"horario\s+de\s+(?:atenci[óo]n|trabajo|apertura|funcionamiento)|"
        r"atendemos\s+(?:de|los)|abrimos\b|trabajamos\s+(?:de|los)|"
        r"de\s+lunes\s+(?:a|hasta)\s+(?:viernes|s[áa]bado|domingo)|"
        r"de\s+\d{1,2}\s?h?(?::\d{2})?\s*a\s*\d{1,2}\s?h", re.IGNORECASE),
    no_booking=(
        "En realidad, no encontré ninguna cita activa a tu nombre en este momento. 😊 Si "
        "quieres, puedo consultar los horarios disponibles y reservar una para ti — ¡solo "
        "dime el día que prefieres!"),
    check_avail=(
        "Déjame consultar los horarios que están realmente disponibles para ti — dime el "
        "día que prefieres y te confirmo las opciones correctas. 😊"),
    unverified_status=(
        "Todavía no pude aplicar ese cambio en el sistema. 😊 Confírmame de nuevo lo que "
        "prefieres — confirmar, reprogramar o cancelar — y lo registro al instante."),
    no_action_taken=(
        "Todavía no llegué a registrar esto en el sistema. 😊 Dime el profesional y el "
        "horario que prefieres y hago la reserva para ti al instante."),
    pending_not_confirmed=(
        "Tu solicitud fue registrada y está esperando la confirmación del profesional. 😊 "
        "En cuanto confirme, ¡te aviso de inmediato!"),
    unread_schedule=(
        "Déjame consultar tu agenda para responderte con certeza. 😊 Un momento y confirmo "
        "lo que está agendado esos días."),
    stale_filtered_listing=(
        "No tengo esa información confirmada en el sistema ahora. 😊 ¿Quieres que traiga tu "
        "agenda completa para revisar lo que está registrado?"),
    unread_settings=(
        "Déjame confirmar el horario de atención exacto en el sistema. 😊 Un momento y te "
        "digo los días y horarios correctos."))

_BUNDLES: dict[str, _Bundle] = {"pt": _PT_BUNDLE, "en": _EN_BUNDLE, "es": _ES_BUNDLE}


# ── trace predicates (language-agnostic — they grep the English tool markers) ─────────
def _list_read_empty(tools: Sequence[ToolCall]) -> bool:
    """A ``list_appointments`` ran this turn and EVERY read came back empty."""
    reads = ok_results(tools, "list_appointments")
    return bool(reads) and all(LIST_EMPTY_RE.match(r.strip()) for r in reads)


def _list_reads_all_filtered_empty(tools: Sequence[ToolCall]) -> bool:
    """EVERY list read this turn was the status-filtered-empty recovery variant — rows
    exist with other statuses, but NO row content is in hand this turn."""
    reads = ok_results(tools, "list_appointments")
    return bool(reads) and all(LIST_FILTERED_EMPTY_RE.match(r.strip()) for r in reads)


def _book_attempted(tools: Sequence[ToolCall]) -> bool:
    return any(t.tool == "book_appointment" for t in tools)


def _booked_ok(tools: Sequence[ToolCall]) -> bool:
    return any(r.startswith(BOOKED_PREFIX) for r in ok_results(tools, "book_appointment"))


def _availability_read(tools: Sequence[ToolCall]) -> bool:
    return bool(ok_results(tools, "check_availability"))


def _settings_read(tools: Sequence[ToolCall]) -> bool:
    """The clinic's schedule settings were read/written this turn (get/set both echo them)."""
    return bool(ok_results(tools, "get_schedule_settings")
                or ok_results(tools, "set_schedule_settings"))


def _contradicts_booking(tools: Sequence[ToolCall]) -> bool:
    """In-hand evidence that the user has NO relevant booking / the commit did not happen:
    an empty list read, or a book that was attempted but did not succeed. Never fires on
    pure recall (no read/attempt this turn), so a legit prior-turn reminder is safe."""
    if _booked_ok(tools):
        return False
    return _list_read_empty(tools) or _book_attempted(tools)


def _status_changed(tools: Sequence[ToolCall]) -> bool:
    """A scheduler MUTATION actually succeeded this turn (confirm/cancel/reschedule/book)."""
    return any(ok_results(tools, t) for t in ("update_appointment_status", "cancel_appointment",
                                              "reschedule_appointment", "book_appointment"))


def _pending_in_hand(tools: Sequence[ToolCall]) -> bool:
    return any(PENDING_MARK_RE.search(r) for r in ok_results(tools))


def _confirmed_in_hand(tools: Sequence[ToolCall]) -> bool:
    return any(CONFIRMED_MARK_RE.search(r) for r in ok_results(tools))


# ── reply predicates (locale-parameterised) ──────────────────────────────────────────
def _affirms_booking(reply: str, b: _Bundle) -> bool:
    """Some clause affirms a dated appointment exists / was made (booking noun + date, not
    negated in that clause)."""
    return any(b.booking_noun.search(c) and b.loc.date.search(c) and not b.loc.neg.search(c)
               for c in clauses(reply))


def _offers_slots(reply: str, b: _Bundle) -> bool:
    return bool(b.offer.search(reply) and b.loc.date.search(reply))


def _lists_dated_appointment(reply: str, b: _Bundle) -> bool:
    """The reply presents at least one concrete dated appointment — a booking noun in a
    non-negated clause plus a date somewhere. Unlike :func:`_affirms_booking` (both in ONE
    clause, for a single "sua consulta está agendada para 08/07" affirmation), this spans
    the reply so a multi-line listing (header noun + dated item lines) is caught."""
    return bool(affirmed(reply, b.booking_noun, neg=b.loc.neg) and b.loc.date.search(reply))


def _concludes_action_now(reply: str, b: _Bundle) -> bool:
    """The reply claims the assistant JUST performed a scheduling action *this turn*
    (first-person "marquei/confirmei", "prontinho, ficou marcada") — distinct from a
    stative recall. Requires a concrete anchor (date or booking noun) so a bare
    "pronto!" doesn't trip it."""
    if not (b.loc.date.search(reply) or b.booking_noun.search(reply)):
        return False
    return affirmed(reply, b.conclusion_now, neg=b.loc.neg)


def ground_reply(reply: str, *, tools: Sequence[ToolCall] = (), had_executor: bool = True,
                 is_read_query: bool = False, pending_confirmation: bool = False,
                 locale: str = "pt") -> Optional[GroundingVerdict]:
    """Return a :class:`GroundingVerdict` if ``reply`` fabricates a scheduler fact, else None.

    ``tools`` is this turn's executed-call trace; ``had_executor`` is False when the turn
    routed straight to the voicer (no executor ran at all); ``is_read_query`` marks a
    read/listing turn (a stative "confirmado" in a listing is never a status-change claim);
    ``pending_confirmation`` marks a turn that carried an accept/refuse notice in context;
    ``locale`` is the reply's language family (pt/en/es) — an unsupported language returns
    None (fail open: never rewrite a reply we have no rules for)."""
    if not reply:
        return None
    b = _BUNDLES.get(normalize_lang(locale))
    if b is None:
        return None

    # (1) existence/completion fabrication — the reply affirms a booking, but the trace
    #     contradicts it (empty read, or a failed/absent commit). Not repairable: the
    #     executor DID run and the honest "no active booking" is final.
    if _affirms_booking(reply, b) and _contradicts_booking(tools):
        return GroundingVerdict(rule="fabricated_booking", message=b.no_booking)

    # (1b) stale filtered listing — the reply lists concrete appointments, but the only
    #     read in hand is a status-filtered EMPTY with the other-statuses hint, so the
    #     listed items can only have come from conversation history (live fabrication
    #     2026-07-13: a days-old "aguardando confirmação" listing re-voiced over
    #     "No PENDING appointments found, but there ARE 28…"). NO_BOOKING_MSG would lie
    #     here (rows DO exist), so this is its own rule. Repairable: re-list unfiltered.
    #     Suppressed when a mutation succeeded (its result grounds the dates in the reply)
    #     or an availability read is in hand (offer dates are rule 2's turf).
    if (_lists_dated_appointment(reply, b) and _list_reads_all_filtered_empty(tools)
            and not _status_changed(tools) and not _availability_read(tools)):
        return GroundingVerdict(rule="stale_filtered_listing", message=b.stale_filtered_listing,
                                repairable=True, critique=_STALE_FILTERED_LISTING_CRITIQUE)

    # (2) availability fabrication — a slot menu with no availability read behind it.
    #     Repairable: the right answer is to actually CALL check_availability.
    #     Suppressed when a list_appointments read is IN HAND: a listing of the user's own
    #     appointments carries dates + "qual deles…" phrasing and read as an offer, but it is
    #     grounded in a real read — live false positive 2026-07-10: "traga só os pendentes"
    #     had its legitimate listing rewritten to CHECK_AVAIL_MSG (and the repair re-ran the
    #     whole pipeline). The rule targets a menu conjured from NOTHING.
    if (_offers_slots(reply, b) and not _availability_read(tools)
            and not ok_results(tools, "list_appointments")):
        return GroundingVerdict(rule="conjured_slots", message=b.check_avail,
                                repairable=True, critique=_CONJURED_SLOTS_CRITIQUE)

    # (3) confirmation fabrication — in a pending-confirmation turn the reply claims the
    #     appointment was confirmed/cancelled, but NO scheduler mutation ran. Never on a
    #     read; suppressed when a CONFIRMED result is in hand (grounded stative recall).
    if (not is_read_query and pending_confirmation
            and affirmed(reply, b.status_done, neg=b.loc.neg)
            and not _status_changed(tools) and not _confirmed_in_hand(tools)):
        return GroundingVerdict(rule="unverified_status", message=b.unverified_status,
                                repairable=True, critique=_UNVERIFIED_STATUS_CRITIQUE)

    # (4) PENDING-vs-"confirmada" — the tools show PENDING (awaiting the professional) but
    #     the voice upgrades it to "confirmada". Not repairable: it IS pending.
    if (affirmed(reply, b.confirmed_done, neg=b.loc.neg) and _pending_in_hand(tools)
            and not _confirmed_in_hand(tools)):
        return GroundingVerdict(rule="pending_not_confirmed", message=b.pending_not_confirmed)

    # (5) conclusion-now with NO executor trace — the turn routed straight to the voicer,
    #     yet the reply claims it just booked/marked something. Repairable: the repair
    #     re-step forces the executor route, undoing the misroute.
    if not had_executor and not is_read_query and _concludes_action_now(reply, b):
        return GroundingVerdict(rule="no_action_taken", message=b.no_action_taken,
                                repairable=True, critique=_NO_ACTION_TAKEN_CRITIQUE)

    # (6) unread schedule claim — a READ query whose reply asserts what is booked/blocked/
    #     occupied, yet NO list_appointments read ran this turn (the executor answered from
    #     conversation history instead of reading). This is the "qual dia eu bloquiei?" bug:
    #     the model confabulated "já estão ocupados" without ever querying the agenda.
    #     Repairable: the re-step forces a real listing. Suppressed when a listing OR an
    #     availability read is in hand (that claim is grounded; availability is rule 2's turf).
    if (is_read_query and affirmed(reply, b.occupancy_claim, neg=b.loc.neg)
            and not ok_results(tools, "list_appointments")
            and not _availability_read(tools)):
        return GroundingVerdict(rule="unread_schedule_claim", message=b.unread_schedule,
                                repairable=True, critique=_UNREAD_SCHEDULE_CRITIQUE)

    # (7) unread SETTINGS claim — the reply states the clinic's working hours / days / expediente
    #     (a business-config fact), yet get_schedule_settings was NEVER called this turn: the model
    #     answered from its own priors (live finding — it fabricated "das 08h às 18h" that isn't in
    #     the prompt, and would be WRONG for a tenant that changed hours via set_schedule_settings).
    #     Repairable: the re-step forces the read. Suppressed when a settings read/write is in hand.
    if affirmed(reply, b.working_hours_claim, neg=b.loc.neg) and not _settings_read(tools):
        return GroundingVerdict(rule="unread_settings_claim", message=b.unread_settings,
                                repairable=True, critique=_UNREAD_SETTINGS_CRITIQUE)

    return None

"""Deterministic reply-grounding backstop for the BOOKKEEPER vertical.

Money is the worst place to fabricate: a reply that claims a transaction was recorded
(or quotes totals) that the tools never produced misleads the user's FINANCES. Same
design as the scheduler backstop: fire only on an in-hand contradiction with this
turn's own trace; truthful replies and prior-turn recalls are never touched. Rules
live next to the tool-result strings they grep (see ``server.py``).

Locale: reply-side patterns + rewrite messages come one bundle per language
(``_BUNDLES``); ``ground_reply(..., locale=)`` selects it (pt/en/es), failing open on an
unsupported language. Tool markers + ``_*_CRITIQUE`` strings are language-agnostic.
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
    normalize_lang,
    ok_results,
)

# ── this vertical's tool-result markers (see server.py — same repo, keep in lockstep) ─
INCOME_RECORDED_PREFIX = "Income recorded: "
EXPENSE_RECORDED_PREFIX = "Expense recorded: "
REMOVED_PREFIX = "Removed: "
SUMMARY_HEAD_RE = re.compile(r"^Income:\s")     # get_summary's first line

# ── reply-side patterns (pt-BR) ──────────────────────────────────────────────────────
# The reply claims an entry was RECORDED this turn (first person or done-participle).
_RECORDED_RE = re.compile(
    r"\b(?:registrei|lancei|lançei|anotei)\b|"
    r"\b(?:registrad|lançad|lancad|anotad)[oa]s?\b|"
    r"acabei\s+de\s+(?:registrar|lançar|lancar|anotar)",
    re.IGNORECASE)
# The reply quotes totals/saldo (a money figure near a totals noun).
_TOTALS_RE = re.compile(
    r"\b(?:total|totais|saldo|l[íi]quido|entradas?|sa[íi]das?|faturamento|balan[çc]o)\b",
    re.IGNORECASE)
# The reply claims a removal was performed.
_REMOVED_RE = re.compile(
    r"\b(?:removi|apaguei|exclu[íi]|deletei)\b|\b(?:removid|exclu[íi]d|apagad)[oa]s?\b",
    re.IGNORECASE)

# ── safe rewrites — honest, keep the conversation alive (pt-BR) ───────────────────────
NO_ENTRY_MSG = (
    "Na verdade, esse lançamento ainda não foi registrado no sistema. Me confirma a "
    "descrição e o valor que eu registro agora e te retorno o comprovante.")
CHECK_TOTALS_MSG = (
    "Deixa eu consultar os números reais no sistema antes de te passar totais — me diga "
    "o período que você quer ver e eu trago o resumo exato.")
NO_REMOVAL_MSG = (
    "Nenhum lançamento foi removido ainda. Me diz qual lançamento você quer remover "
    "(descrição ou valor) que eu localizo e removo agora.")

# Critiques feed the EGO correction channel — English, language-agnostic, shared.
_NO_ENTRY_CRITIQUE = (
    "The previous reply claimed a transaction was recorded, but no add_income/add_outcome "
    "succeeded this turn. Record the entry for real (confirm description and amount) and "
    "report only what the tool returned.")
_CHECK_TOTALS_CRITIQUE = (
    "The previous reply quoted financial totals that were never read from the bookkeeper. "
    "Call get_summary (or search) for the requested period and quote ONLY the figures the "
    "tool returns.")
_NO_REMOVAL_CRITIQUE = (
    "The previous reply claimed a transaction was removed, but no remove_by_search succeeded "
    "this turn. Perform the removal for real and report only the tool's outcome.")


# ── per-locale reply patterns + messages ─────────────────────────────────────────────
@dataclass(frozen=True)
class _Bundle:
    """One language's reply-side patterns + honest rewrite messages (trace predicates and
    critiques are shared/language-agnostic)."""

    loc: Locale
    recorded: re.Pattern[str]
    totals: re.Pattern[str]
    removed: re.Pattern[str]
    no_entry: str
    check_totals: str
    no_removal: str


_PT_BUNDLE = _Bundle(
    loc=_PT, recorded=_RECORDED_RE, totals=_TOTALS_RE, removed=_REMOVED_RE,
    no_entry=NO_ENTRY_MSG, check_totals=CHECK_TOTALS_MSG, no_removal=NO_REMOVAL_MSG)

_EN_BUNDLE = _Bundle(
    loc=_EN,
    recorded=re.compile(
        r"\b(?:recorded|logged|entered|booked)\b|"
        r"\bi(?:'ve|\s+have|\s+just|)\s+(?:recorded|logged|added|entered)\b|"
        r"\bjust\s+(?:recorded|logged|added|entered)\b", re.IGNORECASE),
    totals=re.compile(
        r"\b(?:total|totals|balance|net|income|expenses?|revenue|profit|turnover)\b",
        re.IGNORECASE),
    removed=re.compile(
        r"\b(?:removed|deleted|erased)\b|"
        r"\bi(?:'ve|\s+have|\s+just|)\s+(?:removed|deleted|erased)\b", re.IGNORECASE),
    no_entry=(
        "Actually, that entry hasn't been recorded in the system yet. Confirm the "
        "description and the amount and I'll record it now and send you the receipt."),
    check_totals=(
        "Let me pull the real numbers from the system before I give you any totals — tell "
        "me the period you'd like to see and I'll bring the exact summary."),
    no_removal=(
        "No entry has been removed yet. Tell me which entry you want to remove (description "
        "or amount) and I'll find it and remove it now."))

_ES_BUNDLE = _Bundle(
    loc=_ES,
    recorded=re.compile(
        r"\b(?:registr[ée]|anot[ée]|apunt[ée]|a[ñn]ad[íi])\b|"
        r"\b(?:registrad|anotad|apuntad|a[ñn]adid)[oa]s?\b|"
        r"acabo\s+de\s+(?:registrar|anotar|apuntar|a[ñn]adir)", re.IGNORECASE),
    totals=re.compile(
        r"\b(?:total|totales|saldo|neto|ingresos?|gastos?|egresos?|facturaci[óo]n|"
        r"balance)\b", re.IGNORECASE),
    removed=re.compile(
        r"\b(?:elimin[ée]|borr[ée]|quit[ée])\b|\b(?:eliminad|borrad)[oa]s?\b", re.IGNORECASE),
    no_entry=(
        "En realidad, ese registro todavía no fue guardado en el sistema. Confírmame la "
        "descripción y el monto y lo registro ahora y te envío el comprobante."),
    check_totals=(
        "Déjame consultar los números reales en el sistema antes de darte totales — dime "
        "el período que quieres ver y te traigo el resumen exacto."),
    no_removal=(
        "Todavía no se eliminó ningún registro. Dime cuál registro quieres eliminar "
        "(descripción o monto) y lo localizo y lo elimino ahora."))

_BUNDLES: dict[str, _Bundle] = {"pt": _PT_BUNDLE, "en": _EN_BUNDLE, "es": _ES_BUNDLE}


# ── trace predicates (language-agnostic — grep the English tool markers) ──────────────
def _entry_recorded(tools: Sequence[ToolCall]) -> bool:
    """An add_income/add_outcome SUCCEEDED this turn (the ERROR: shape is ok=True but not
    a recorded entry — the bookkeeper server relays domain refusals as text)."""
    for tool in ("add_income", "add_outcome"):
        for r in ok_results(tools, tool):
            if r.startswith((INCOME_RECORDED_PREFIX, EXPENSE_RECORDED_PREFIX)):
                return True
    return False


def _summary_read(tools: Sequence[ToolCall]) -> bool:
    """A get_summary/search read succeeded this turn (any figures in hand)."""
    return bool(ok_results(tools, "get_summary")) or bool(ok_results(tools, "search"))


def _removed_ok(tools: Sequence[ToolCall]) -> bool:
    return any(r.startswith(REMOVED_PREFIX) for r in ok_results(tools, "remove_by_search"))


def ground_reply(reply: str, *, tools: Sequence[ToolCall] = (), had_executor: bool = True,
                 is_read_query: bool = False, pending_confirmation: bool = False,
                 locale: str = "pt") -> Optional[GroundingVerdict]:
    """Return a :class:`GroundingVerdict` if ``reply`` fabricates a bookkeeping fact, else None.

    Same signature as the scheduler backstop (the host adapter treats every vertical
    alike); ``is_read_query``/``pending_confirmation`` are accepted for symmetry;
    ``locale`` selects the language bundle (pt/en/es), None on an unsupported language."""
    if not reply:
        return None
    b = _BUNDLES.get(normalize_lang(locale))
    if b is None:
        return None

    # (1) fabricated entry — the reply claims a transaction was recorded (with a money
    #     anchor so book-keeping small talk doesn't trip it), but no write succeeded.
    #     Repairable: record it for real.
    if (b.loc.money.search(reply) and affirmed(reply, b.recorded, neg=b.loc.neg)
            and not _entry_recorded(tools)):
        return GroundingVerdict(rule="fabricated_entry", message=b.no_entry,
                                repairable=True, critique=_NO_ENTRY_CRITIQUE)

    # (2) fabricated removal — "removi/excluí" with no successful remove_by_search.
    #     Repairable: perform the removal for real.
    if affirmed(reply, b.removed, neg=b.loc.neg) and not _removed_ok(tools):
        return GroundingVerdict(rule="fabricated_removal", message=b.no_removal,
                                repairable=True, critique=_NO_REMOVAL_CRITIQUE)

    # (3) conjured totals — the reply quotes saldo/totals with no summary/search read in
    #     hand. Repairable: read the real numbers. Checked LAST: a recorded-entry reply
    #     legitimately echoes the amount ("registrei R$ 500") without a summary read.
    if (b.loc.money.search(reply) and affirmed(reply, b.totals, neg=b.loc.neg)
            and not _summary_read(tools) and not _entry_recorded(tools)):
        return GroundingVerdict(rule="conjured_totals", message=b.check_totals,
                                repairable=True, critique=_CHECK_TOTALS_CRITIQUE)

    return None

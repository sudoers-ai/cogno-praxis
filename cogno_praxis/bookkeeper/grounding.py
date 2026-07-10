"""Deterministic reply-grounding backstop for the BOOKKEEPER vertical.

Money is the worst place to fabricate: a reply that claims a transaction was recorded
(or quotes totals) that the tools never produced misleads the user's FINANCES. Same
design as the scheduler backstop: fire only on an in-hand contradiction with this
turn's own trace; truthful replies and prior-turn recalls are never touched. Rules
live next to the tool-result strings they grep (see ``server.py``).
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from cogno_praxis.grounding import (
    MONEY_RE,
    GroundingVerdict,
    ToolCall,
    affirmed,
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

# ── safe rewrites — honest, keep the conversation alive ──────────────────────────────
NO_ENTRY_MSG = (
    "Na verdade, esse lançamento ainda não foi registrado no sistema. Me confirma a "
    "descrição e o valor que eu registro agora e te retorno o comprovante.")
CHECK_TOTALS_MSG = (
    "Deixa eu consultar os números reais no sistema antes de te passar totais — me diga "
    "o período que você quer ver e eu trago o resumo exato.")
NO_REMOVAL_MSG = (
    "Nenhum lançamento foi removido ainda. Me diz qual lançamento você quer remover "
    "(descrição ou valor) que eu localizo e removo agora.")

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
                 is_read_query: bool = False,
                 pending_confirmation: bool = False) -> Optional[GroundingVerdict]:
    """Return a :class:`GroundingVerdict` if ``reply`` fabricates a bookkeeping fact, else None.

    Same signature as the scheduler backstop (the host adapter treats every vertical
    alike); ``is_read_query``/``pending_confirmation`` are accepted for symmetry."""
    if not reply:
        return None

    # (1) fabricated entry — the reply claims a transaction was recorded (with a money
    #     anchor so book-keeping small talk doesn't trip it), but no write succeeded.
    #     Repairable: record it for real.
    if (MONEY_RE.search(reply) and affirmed(reply, _RECORDED_RE)
            and not _entry_recorded(tools)):
        return GroundingVerdict(rule="fabricated_entry", message=NO_ENTRY_MSG,
                                repairable=True, critique=_NO_ENTRY_CRITIQUE)

    # (2) fabricated removal — "removi/excluí" with no successful remove_by_search.
    #     Repairable: perform the removal for real.
    if affirmed(reply, _REMOVED_RE) and not _removed_ok(tools):
        return GroundingVerdict(rule="fabricated_removal", message=NO_REMOVAL_MSG,
                                repairable=True, critique=_NO_REMOVAL_CRITIQUE)

    # (3) conjured totals — the reply quotes saldo/totals with no summary/search read in
    #     hand. Repairable: read the real numbers. Checked LAST: a recorded-entry reply
    #     legitimately echoes the amount ("registrei R$ 500") without a summary read.
    if (MONEY_RE.search(reply) and affirmed(reply, _TOTALS_RE)
            and not _summary_read(tools) and not _entry_recorded(tools)):
        return GroundingVerdict(rule="conjured_totals", message=CHECK_TOTALS_MSG,
                                repairable=True, critique=_CHECK_TOTALS_CRITIQUE)

    return None

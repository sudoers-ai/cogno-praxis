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
from decimal import Decimal, InvalidOperation
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
    """A get_summary/search read succeeded this turn (real figures in hand)."""
    return bool(ok_results(tools, "get_summary")) or bool(ok_results(tools, "search"))


# Amount comparison, rebuilt after six revisions of locale-guessing parsers. The lesson:
# every attempt to decide "is this dot a decimal or a thousands separator?" failed in one
# direction or the other, so this does not decide. It reads a candidate BOTH ways and a
# match under EITHER reading counts — which is sound here because the question is not "what
# is this number" but "did math produce it".
_CANDIDATE = re.compile(r"-?\d[\d.,]*")
# A number is an AMOUNT when a currency marker touches it (sigil before, currency word
# after) or it is written with cents. Bare integers are not: "São 3 cortes" is not a claim
# about the books, and treating it as one rewrote correct replies.
_AMOUNT_CONTEXT = re.compile(
    r"(?:R\$|US\$|\$|€)\s*(-?\d[\d.,]*)"
    r"|(-?\d[\d.,]*)\s*(?:reais|real|reales|euros?|d[oó]lares|dollars|usd|brl)\b"
    r"|(-?\d[\d.,]*[.,]\d{2})\b")


def _canonical(raw: str) -> "Optional[Decimal]":
    """The value of a token the TOOL produced — dot-decimal, no thousands separators.

    The tool's output is machine-written and never ambiguous, so it gets ONE reading. An
    earlier version ran the ambiguous reader over this side too, and that is not a subtlety:
    a computed 48.6 then also counted as 486, and a fabricated "saldo de R$ 486,00" was
    grounded by a computation of R$ 48,60. The comment there claimed the dual reading "cannot
    produce a false GROUNDING" — true of the REPLY side, false the moment it is applied here.
    """
    try:
        return Decimal(raw.replace(",", "").strip().rstrip("."))
    except (InvalidOperation, ValueError):
        return None


def _readings(raw: str) -> "set[Decimal]":
    """Every value ``raw`` could denote — dot-decimal AND comma-decimal. REPLY side only.

    The voicer's convention is genuinely unknown: a pt-BR reply writes "R$ 48,60", an EN one
    "$48.60", and either may quote the tool's own "48.6" verbatim. Reading both ways here is
    safe because the reply side is the one being CHECKED — a value passes only if it matches
    something the tool actually computed.
    """
    out: "set[Decimal]" = set()
    for candidate in ({raw.replace(".", "").replace(",", "."), raw.replace(",", "")}
                      | {raw.replace(",", ".")} if raw.count(",") + raw.count(".") <= 1
                      else {raw.replace(".", "").replace(",", "."), raw.replace(",", "")}):
        try:
            out.add(Decimal(candidate.rstrip(".,")))
        except (InvalidOperation, ValueError):
            continue
    return out


def _quoted_amounts(reply: str) -> "list[set[Decimal]]":
    """One entry per amount the reply states, each the set of values it could denote."""
    found: "list[set[Decimal]]" = []
    for match in _AMOUNT_CONTEXT.finditer(reply or ""):
        raw = next((g for g in match.groups() if g), "")
        readings = _readings(raw)
        if readings:
            found.append(readings)
    return found


def _computed_values(tools: Sequence[ToolCall]) -> "set[Decimal]":
    """The values ``math`` RETURNED — the right-hand side only.

    The result echoes the caller's own expression ("12400 * 1 = 12400"), so scanning the
    whole string grounded every number the MODEL supplied: one throwaway call laundered an
    invented balance past the backstop. Only what follows the final "=" counts, and an
    identity operation (the result also appearing among the operands) counts for nothing —
    that is the laundering shape itself.
    """
    values: "set[Decimal]" = set()
    for result in ok_results(tools, "math"):
        if result.startswith("ERROR:") or "=" not in result:
            continue
        left, _, right = result.rpartition("=")
        value = _canonical(right.strip())
        if value is None:
            continue
        computed = {value}
        operands = {v for v in (_canonical(t) for t in _CANDIDATE.findall(left))
                    if v is not None}
        if computed & operands:
            continue                      # "12400 * 1 = 12400" — grounds nothing
        values |= computed
        # The voicer rounds a long tail to cents ("33,33" for 33.333333), so the rounded
        # rendering of a computed value is the same claim.
        for value in list(computed):
            values.add(value.quantize(Decimal("0.01")))
    return values


# Any number at all. Used to decide whether the reply carries digits the amount extractor
# could NOT account for — the exemption is refused when it does.
_ANY_NUMBER = re.compile(r"-?\d[\d.,]*")


def _math_covers_the_amounts(reply: str, tools: Sequence[ToolCall]) -> bool:
    """Did ``math`` produce every amount the reply states?

    Figure-wise, not turn-wide: counting any successful math call as grounding exempted the
    WHOLE reply, so "o corte fica R$ 48,60 — aliás, seu saldo é R$ 12.400,00" shipped an
    invented balance. Unlike get_summary/search, math READS nothing; it can only vouch for
    what it computed.
    """
    computed = _computed_values(tools)
    if not computed:
        return False
    quoted = _quoted_amounts(reply)
    if not quoted or not all(readings & computed for readings in quoted):
        return False
    # Every DIGIT in the reply must be accounted for — matched as an amount the tool
    # computed, or recognisable as something that is not money. An unparsed number REFUSES
    # the exemption instead of riding along: "…R$ 48,60 e o faturamento foi 12 mil reais"
    # and "Saldo do mês: 12.400" both slipped past an extractor that only looked for
    # sigils and cents, and the miss failed OPEN — the direction a fabrication guard must
    # never take. Now the weaker the parse, the SAFER the outcome.
    accounted: "set[Decimal]" = set()
    for readings in quoted:
        accounted |= readings
    for match in _ANY_NUMBER.finditer(reply or ""):
        values = _readings(match.group(0))
        if not values or values & accounted or values & computed:
            continue
        # A SCALE or currency word right after makes it money whatever its size: "12 mil
        # reais" is a balance, and the small-integer exemption below was swallowing it.
        if _SCALE_AFTER.match(reply[match.end():match.end() + 24]):
            return False
        if values & _NOT_MONEY or _is_year(match.group(0), values):
            continue          # a count ("São 3 cortes") or a year ("Em 2026") is no claim
        return False
    return True


# Small bare integers are counts, not amounts ("São 3 cortes", "em 2 dias"). A fabricated
# BALANCE is never written as a bare 3 — and treating counts as amounts rewrote correct
# replies, which is how this check earned its narrow shape.
_NOT_MONEY = {Decimal(n) for n in range(0, 32)}

def _is_year(raw: str, values: "set[Decimal]") -> bool:
    """A bare four-digit number in the calendar range — "Em 2026 o total fica…".

    Written plainly (no separator, no cents): an AMOUNT of two thousand and twenty-six reais
    would carry a sigil or cents and be captured as one, and those paths run first.
    """
    return (raw.isdigit() and len(raw) == 4
            and any(Decimal(1900) <= v <= Decimal(2100) for v in values))


_SCALE_AFTER = re.compile(
    r"^\s*(mil|milh[oõ]es?|milhao|mi|k|reais|real|reales|euros?|d[oó]lares|dollars|"
    r"thousand|million)\b")


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
            and not _summary_read(tools) and not _entry_recorded(tools)
            and not _math_covers_the_amounts(reply, tools)):
        return GroundingVerdict(rule="conjured_totals", message=b.check_totals,
                                repairable=True, critique=_CHECK_TOTALS_CRITIQUE)

    return None

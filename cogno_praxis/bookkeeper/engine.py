"""Pure bookkeeping rules — validation, defaults, aggregation. No I/O, no side effects.

Ported (behaviour) from the parent ``cogno/mcp/modules/bookkeeper``. Everything here reads
inputs + existing transactions and produces values/errors; persistence lives in the store and
orchestration in the service (mirrors ``scheduler/engine.py``).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Iterable, Optional

# Transaction kinds.
INCOME = "income"
OUTCOME = "outcome"


# ── One argument, one number ──────────────────────────────────────────────────────────
# :func:`parse_amount` used to keep every digit in the string and DROP everything else, so an
# argument naming two numbers silently produced a THIRD that nobody said. Measured offline
# against this function on the base commit:
#
#     "150 ou 200"       -> 150200.00        "entre 300 e 400"  -> 300400.00
#     "R$ 100 a R$ 200"  -> 100200.00        "12/05 R$ 300"     -> 1205300.00
#
# The last one is a DATE glued onto an amount. None of these is a rounding error: the figure
# recorded is one the user never uttered, and it is recorded silently, at full confidence.
#
# The asymmetry is the whole reason this REFUSES instead of choosing one: a lançamento that
# never happened is VISIBLE in the books — the owner sees a gap and asks — while a lançamento
# of the wrong amount is not. So an argument that does not read as ONE number is refused.
#
# And the refusal says what to DO, not only which forms exist. Naming only the forms gets the
# same wrong input reworded (the ``resolve_date`` lesson, already written into ``math``'s own
# error in ``server.py``); what the model must do here is ASK, because the missing fact is the
# user's and nobody else has it.
_NUMBER_RUN = re.compile(r"\d(?:[\d.,]*\d)?")

#: Tail of every refusal on the recording path — the model's next move is a QUESTION.
_ASK_DONT_GUESS = (
    " Nothing was recorded. ASK the user for the exact amount as a single number and call "
    "this tool again with what they answer — never guess, average, round, or pick one of "
    "several numbers.")


class BookkeeperError(ValueError):
    """A domain-rule violation (invalid amount, bad date, …). The service re-raises it and the
    server maps it to a recoverable tool error (fed back so the model self-corrects)."""


def parse_amount(raw: object) -> float:
    """Coerce a user/LLM-supplied amount to a positive float, or raise.

    Accepts ``150``, ``150.0``, ``"150"``, ``"R$ 1.500,50"`` (pt-BR) and ``"1,500.50"`` (en).

    An argument that names no number, or more than one, is REFUSED with a reason that tells
    the model to ASK the user — never to guess or approximate. See :data:`_NUMBER_RUN`.
    """
    if isinstance(raw, (int, float)):
        amount = float(raw)
    else:
        text = str(raw).strip()
        negative = "-" in text
        # ONE argument, ONE number — see _NUMBER_RUN. Currency symbols, spaces and words
        # around the figure are still dropped; a SECOND figure is not, because dropping the
        # gap between two numbers is what glued them into a third.
        runs = _NUMBER_RUN.findall(text)
        if not runs:
            raise BookkeeperError(f"no amount in {raw!r}." + _ASK_DONT_GUESS)
        if len(runs) > 1:
            raise BookkeeperError(
                f"{raw!r} names {len(runs)} numbers ({', '.join(runs)}), so there is no single "
                "amount to record." + _ASK_DONT_GUESS)
        s = runs[0]
        # The RIGHTMOST separator is the decimal point; the other is a thousands separator.
        # Handles both "1.500,50" (pt-BR) and "1,500.50" (en).
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
        try:
            amount = float(s)
        except ValueError as exc:
            raise BookkeeperError(f"invalid amount: {raw!r}." + _ASK_DONT_GUESS) from exc
        if negative:
            amount = -amount
    if amount <= 0:
        raise BookkeeperError(f"amount must be positive, got {amount}." + _ASK_DONT_GUESS)
    return round(amount, 2)


def resolve_date(raw: object, today: date) -> str:
    """Return an ISO ``YYYY-MM-DD`` date. Empty/None → ``today``; an ISO string is validated.

    Relative phrases ("ontem", "hoje") are NOT resolved here — the host injects ``[TODAY]`` and
    the model passes an explicit date; anything unparseable falls back to today (never invents)."""
    if raw is None or str(raw).strip() == "":
        return today.isoformat()
    try:
        return date.fromisoformat(str(raw).strip()).isoformat()
    except ValueError:
        return today.isoformat()


def normalize_name(name: str) -> str:
    """Trim + collapse whitespace for a client/description (display value, not a key)."""
    return " ".join((name or "").split())


def _fold(s: str) -> str:
    """Accent/case-insensitive fold for keyword search (matches the scheduler's ``_fold``)."""
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode("ascii")


def matches_query(text: str, query: str) -> bool:
    """True if ``query`` (accent/case-insensitive) is a substring of ``text``. Empty query → all."""
    q = _fold(query).strip()
    return not q or q in _fold(text)


def amount_in_query(query: str) -> "Optional[float]":
    """The money figure a query names, or ``None`` when it names none.

    Reuses :func:`parse_amount`, which is the point: the four ways a contact and a tool spell
    the same figure — ``45``, ``45.00``, ``45,00``, ``R$ 45,00`` — converge on one float there,
    and a second reader would be a second set of separator rules to keep in step.

    It never raises: a query that is not a figure (``"material"``) is simply not an amount
    query, and a query naming SEVERAL figures (``"45.00 2026-09-06"``) is refused by
    ``parse_amount`` for the reason written at :data:`_NUMBER_RUN` and is not one either.
    """
    try:
        return parse_amount(query)
    except BookkeeperError:
        return None


def matches_entry(description: str, client_name: str, amount: float, query: str) -> bool:
    """Does this entry answer ``query`` — by its words, or by its VALUE?

    ``matches_query`` alone reads the description and the client name, and the AMOUNT is not
    in that haystack at all. So a contact who says "remove a de 45,00" — the most natural way
    to name an entry, and the one measured live — searched for a number in a text field that
    never contained one, and was told no such entry exists. Over a row that was right there.
    That answer is not "I failed"; to the contact it is a false statement about their own
    books, which is worse than an error.

    **The tolerance is on the NUMERIC side and only there.** The value axis compares two
    floats for EXACT equality to the cent, so ``45`` finds the 45.00 entry and can never find
    the 450.00 one. Widening the TEXT side instead — a prefix, a fuzzy distance — is what
    would let a removal select a neighbouring row, silently, and this function deliberately
    does not do it. When more than one entry matches, the caller proposes and asks (see
    ``BookkeeperService.remove_by_search``); it never picks.
    """
    if matches_query(f"{description} {client_name}", query):
        return True
    wanted = amount_in_query(query)
    return wanted is not None and round(float(amount), 2) == wanted


def summarize(amounts_income: Iterable[float], amounts_outcome: Iterable[float]) -> dict:
    """Totals + net for a set of income/outcome amounts (rounded to cents)."""
    total_in = round(sum(amounts_income), 2)
    total_out = round(sum(amounts_outcome), 2)
    return {"total_income": total_in, "total_outcome": total_out,
            "net": round(total_in - total_out, 2)}

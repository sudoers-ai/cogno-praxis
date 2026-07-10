"""Pure bookkeeping rules — validation, defaults, aggregation. No I/O, no side effects.

Ported (behaviour) from the parent ``cogno/mcp/modules/bookkeeper``. Everything here reads
inputs + existing transactions and produces values/errors; persistence lives in the store and
orchestration in the service (mirrors ``scheduler/engine.py``).
"""

from __future__ import annotations

import unicodedata
from datetime import date
from typing import Iterable

# Transaction kinds.
INCOME = "income"
OUTCOME = "outcome"
VALID_KINDS: tuple[str, ...] = (INCOME, OUTCOME)


class BookkeeperError(ValueError):
    """A domain-rule violation (invalid amount, bad date, …). The service re-raises it and the
    server maps it to a recoverable tool error (fed back so the model self-corrects)."""


def parse_amount(raw: object) -> float:
    """Coerce a user/LLM-supplied amount to a positive float, or raise.

    Accepts ``150``, ``150.0``, ``"150"``, ``"R$ 1.500,50"`` (pt-BR) and ``"1,500.50"`` (en).
    """
    if isinstance(raw, (int, float)):
        amount = float(raw)
    else:
        text = str(raw).strip()
        negative = "-" in text
        # strip currency symbols/spaces/letters, keep digits + separators
        s = "".join(ch for ch in text if ch.isdigit() or ch in ",.")
        if not s:
            raise BookkeeperError(f"invalid amount: {raw!r}")
        # The RIGHTMOST separator is the decimal point; the other is a thousands separator.
        # Handles both "1.500,50" (pt-BR) and "1,500.50" (en).
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
        try:
            amount = float(s)
        except ValueError as exc:
            raise BookkeeperError(f"invalid amount: {raw!r}") from exc
        if negative:
            amount = -amount
    if amount <= 0:
        raise BookkeeperError(f"amount must be positive, got {amount}")
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


def summarize(amounts_income: Iterable[float], amounts_outcome: Iterable[float]) -> dict:
    """Totals + net for a set of income/outcome amounts (rounded to cents)."""
    total_in = round(sum(amounts_income), 2)
    total_out = round(sum(amounts_outcome), 2)
    return {"total_income": total_in, "total_outcome": total_out,
            "net": round(total_in - total_out, 2)}

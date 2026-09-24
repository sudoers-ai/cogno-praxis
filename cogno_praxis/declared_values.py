"""Values a business DECLARED in a persona's configuration — the one definition.

A tenant can write fixed values into a persona's rules (a price, a rate, a fee, a due date)
and expect the persona to quote them WITHOUT a tool: the rules are what the persona was told,
and the executor reads them like any other instruction. Every anti-fabrication rule in this
repo asks one question — *where did this figure come from?* — and until this module the only
answers it recognised were the turn's tool results. So a reply that quoted the tenant's own
configured price, exactly, was indistinguishable from one that invented it, and the net
rewrote it.

**What counts, and it is deliberately narrow:** a VALUE written LITERALLY in the text — money,
a percentage, a calendar date, a number with a unit of time. Never a name, never a phrase,
never a claim: the rules are DIRECTION as much as fact, and a sentence in them is not evidence
that anything happened. And never a value COMPUTED from them — a sum, a correction, a monthly
total built from an hourly rate is not written anywhere, so it is not declared.

Three consumers, one grammar, which is why this lives in ONE place:

* the host EXTRACTS the declared set from the persona's rules, resolved for THIS contact's role
  (:func:`declared_values`) and hands the literal strings on — to the vertical backstops here
  and to the judge/voice prompt in the core;
* the backstops COMPARE a reply's values against that set (:func:`values_declared`);
* both sides go through the same parser, so a rate written ``R$ 120,00`` in the rules and
  ``R$ 120`` in the reply are the same value, and ``R$ 1.440`` is never one-point-four-four.

Pure, deterministic, no I/O. Language-agnostic on purpose: the tenant writes its rules in its
own grammar, the voice may answer in another, and the value is the same value.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional, Sequence, Tuple

#: Upper bound on how many declared values one persona configuration hands on. Past it the
#: remaining values are simply NOT declared — the strict direction: an undeclared value is
#: judged exactly as it was before this module existed.
MAX_DECLARED_VALUES = 128

_NUM = r"\d(?:[\d.,]*\d)?"
_CURRENCY = r"(?:R\$|US\$|€|\$)"
_CURRENCY_WORD = r"(?:reais|real|d[óo]lares|d[óo]lar|dollars?|euros?)"
# Units of TIME only — the values a service business configures beside a price (a 4 h class,
# a 30 min slot, a 12-month plan). Not "aulas", "pessoas" or "itens": a count of things is a
# fact about the world, and a count written in the rules is an instruction, not a reading.
_UNIT_WORDS = {
    "h": "h", "hr": "h", "hrs": "h", "hora": "h", "horas": "h", "hour": "h", "hours": "h",
    "min": "min", "minuto": "min", "minutos": "min", "minute": "min", "minutes": "min",
    "dia": "d", "dias": "d", "día": "d", "días": "d", "day": "d", "days": "d",
    "semana": "w", "semanas": "w", "week": "w", "weeks": "w",
    "mes": "mo", "mês": "mo", "meses": "mo", "month": "mo", "months": "mo",
    "ano": "y", "anos": "y", "año": "y", "años": "y", "year": "y", "years": "y",
}
_UNIT = "(?:" + "|".join(sorted((re.escape(u) for u in _UNIT_WORDS), key=len, reverse=True)) + ")"

# ONE scanner. The alternatives are ordered so the longest reading wins at each position:
# a currency symbol first, then a currency word after the number, then a percentage, a date,
# a number with a unit, and last a bare decimal amount (``1.440,00`` / ``1,440.00`` — the shape
# every money anchor in this repo already reads as money).
_VALUE_RE = re.compile(
    rf"(?P<money>{_CURRENCY}\s?{_NUM})"
    rf"|(?P<money_word>\b{_NUM}\s?{_CURRENCY_WORD}\b)"
    rf"|(?P<pct>\b{_NUM}\s?%)"
    r"|(?P<date>\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b)"
    rf"|(?P<unit>\b{_NUM}\s?{_UNIT}(?![\w]))"
    r"|(?P<bare>\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d{1,3}(?:,\d{3})*\.\d{2}\b)",
    re.IGNORECASE)

_DIGITS_RE = re.compile(_NUM)

# ``("money", amount)`` · ``("pct", value)`` · ``("unit", value, unit)`` ·
# ``("date", day, month, year-or-None)`` — the kind first, so two kinds never compare equal.
Key = Tuple[object, ...]


def _amount(num: str) -> Optional[Decimal]:
    """A written number onto its value, whichever grammar wrote it.

    Both separators present → the LAST one is the decimal point. One separator kind → it is a
    thousands separator when it repeats or is followed by exactly three digits, else a decimal
    point. So ``1.440,00`` = ``1,440.00`` = ``1440``, ``R$ 1.440`` is one thousand four hundred
    and forty (never 1.44), and ``12,5`` is twelve and a half."""
    s = num
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        if len(parts) > 2 or len(parts[-1]) == 3:
            s = "".join(parts)
        else:
            s = parts[0] + "." + parts[1]
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _key(m: "re.Match[str]") -> Optional[Key]:
    kind = m.lastgroup or ""
    text = m.group(0)
    if kind == "date":
        if "-" in text:
            y, mo, d = (int(p) for p in text.split("-"))
            return ("date", d, mo, y)
        parts = [int(p) for p in text.split("/")]
        year: Optional[int] = None
        if len(parts) == 3:
            year = parts[2] + 2000 if parts[2] < 100 else parts[2]
        return ("date", parts[0], parts[1], year)
    num = _DIGITS_RE.search(text)
    value = _amount(num.group(0)) if num else None
    if value is None:
        return None
    if kind in ("money", "money_word", "bare"):
        return ("money", value.quantize(Decimal("0.01")))
    if kind == "pct":
        return ("pct", value.normalize())
    if kind == "unit":
        unit = text[num.end():].strip().lower() if num else ""
        return ("unit", value.normalize(), _UNIT_WORDS.get(unit, unit))
    return None


def _scan(text: str) -> "Iterable[tuple[str, Key]]":
    for m in _VALUE_RE.finditer(text or ""):
        k = _key(m)
        if k is not None:
            yield " ".join(m.group(0).split()), k


def declared_values(text: str, *, limit: int = MAX_DECLARED_VALUES) -> "tuple[str, ...]":
    """The VALUES written literally in ``text``, as written, in order, without repeats.

    Money, percentages, calendar dates and numbers with a unit of time — nothing else. What
    comes back is the literal token (whitespace collapsed), so a prompt that shows it shows the
    tenant's own spelling; two spellings of the same value are kept once, first spelling wins.
    At most ``limit`` values; the rest are not declared (the strict direction)."""
    out: "list[str]" = []
    seen: "set[Key]" = set()
    for literal, k in _scan(text):
        if k in seen:
            continue
        seen.add(k)
        out.append(literal)
        if len(out) >= limit:
            break
    return tuple(out)


def value_keys(text: str) -> "list[Key]":
    """Every value in ``text`` as its normalised key — the comparison half of the grammar."""
    return [k for _, k in _scan(text)]


def _covered(k: Key, declared: "Sequence[Key]") -> bool:
    if k in declared:
        return True
    if k[0] != "date":
        return False
    # A date written without its year matches the same day and month written with one — the
    # rules say "05/10/2026" and the reply "05/10", or the other way round. Two DIFFERENT years
    # never match.
    return any(d[0] == "date" and d[1] == k[1] and d[2] == k[2]
               and (d[3] is None or k[3] is None) for d in declared)


def values_declared(reply: str, declared: "Sequence[str]") -> bool:
    """Every value the reply states is one the configuration declared — and it states one.

    ``False`` when the reply carries no value at all (nothing for a declaration to ground) or
    when the declared set is empty, so a persona with no values in its rules is judged exactly
    as before. ``False`` as soon as ONE value is not declared: a reply that quotes the tenant's
    price beside a total it worked out is not a quotation, and the total is exactly the value
    this exemption must not reach."""
    if not declared:
        return False
    got = value_keys(reply)
    if not got:
        return False
    decl = value_keys("\n".join(str(v) for v in declared if v))
    return bool(decl) and all(_covered(k, decl) for k in got)

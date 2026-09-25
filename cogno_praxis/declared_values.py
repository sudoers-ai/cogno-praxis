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

**Three readings a shared grammar owes every consumer** (F2.1, measured on the value-provenance
disagreements — each one a value the extractor read WRONG, not a source it lacked):

* **the sign.** ``R$ -45,00``, ``R$-45,00``, ``-R$ 45,00`` and a bare ``-45.00`` are MINUS
  forty-five. The sign is read only when written directly against the number or its currency
  symbol — ``R$ 45,00 - R$ 10,00`` stays two positive amounts, ``10-20`` a range. Reading it as
  forty-five let a value of the opposite sign pass as the same value. Money only.
* **the broken bold.** ``**R$**\n**1.440**`` is one value: between the currency symbol and its
  number the scanner allows blanks, markdown emphasis and at most ONE line break (a blank line
  in between is another paragraph, not one value). The literal comes back without the
  emphasis, ``R$ 1.440``.
* **the unit under a machine key.** ``"window_days": 7`` is seven DAYS: a bare number whose key
  has a unit word as one of its parts reads as that unit (plural words and the ``d``/``h``/
  ``min`` abbreviations only; a singular part — ``day``, ``month``, ``hour`` — is a calendar
  component or a rate far more often than a duration). The key must look like a machine's
  (quoted, snake_case, or ``key=``), so prose ("Dias: 7") is never read this way, and a bare
  ``7`` under a key that names no unit (``"id": 7``) reads nothing, as before.
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
# The unit words a MACHINE key may carry as one of its parts (``window_days``, ``durationMinutes``,
# ``ttl_h``): PLURALS and abbreviations only. A singular part names a calendar COMPONENT far more
# often than a duration — ``{"year": 2026, "month": 9, "day": 25}`` is a date, ``day_of_week: 3``
# is a Wednesday, ``price_per_hour: 120`` is a rate — and none of them is "25 dias" or "120 horas".
_KEY_UNIT_WORDS = {
    "days": "d", "dias": "d", "d": "d",
    "hours": "h", "horas": "h", "hrs": "h", "h": "h",
    "minutes": "min", "minutos": "min", "mins": "min", "min": "min",
    "weeks": "w", "semanas": "w",
    "months": "mo", "meses": "mo",
    "years": "y", "anos": "y",
}

# A minus sign, ASCII or U+2212, written DIRECTLY against what it negates — never across a space
# (``R$ 45,00 - R$ 10,00`` is a subtraction, not a negative ten), and never after a word, a digit
# or a separator (``10-20`` is a range, ``2026-09-25`` a date, ``(11) 91234-5678`` a phone).
_SIGN = r"(?:(?<![\w.,/\-−])[-−])"
# What may stand between a currency symbol and its number: blanks and markdown emphasis on ONE
# line, and at most ONE line break — the voice's broken bold, ``**R$**\n**1.440**``. Two line
# breaks are another paragraph: a currency ending one and a number opening the next are not one
# value.
_CUR_GAP = r"(?:[^\S\r\n]|[*_]){0,4}(?:\r?\n(?:[^\S\r\n]|[*_]){0,4})?"
# A MACHINE key naming a unit, then its number: ``"window_days": 7``, ``ttl_h=24``,
# ``"days": 7``. The key must LOOK like a machine's — quoted, or snake_case, or followed by ``=`` —
# so prose ("Dias: 7") is never read this way; and ONE of its ``_`` parts must BE a unit word
# (whole, not a prefix), IN the pattern, so a key that names no unit (``"amount": 45.00``) is never
# consumed here and its number is read exactly as it was before this existed.
_KEY_UNIT = "|".join(sorted((re.escape(u) for u in _KEY_UNIT_WORDS), key=len, reverse=True))
_PART = r"[A-Za-z0-9]+"
_UNIT_PART = rf"(?i:{_KEY_UNIT})(?![A-Za-z0-9])"
_SNAKE = rf"(?:{_PART}_)+{_UNIT_PART}(?:_{_PART})*|{_UNIT_PART}(?:_{_PART})+"
_KEYED = (rf"(?:[\"'](?P<qk>{_SNAKE}|{_UNIT_PART})[\"']\s*[:=]"
          rf"|\b(?P<sk>{_SNAKE})\s*[:=]"
          rf"|\b(?P<ek>{_UNIT_PART})\s*=)"
          rf"\s*[\"']?(?P<kn>{_NUM})(?![\d]|[.,]\d)[\"']?")

# ONE scanner. The alternatives are ordered so the longest reading wins at each position:
# a currency symbol first, then a currency word after the number, then a percentage, a date,
# a number with a unit, and last a bare decimal amount (``1.440,00`` / ``1,440.00`` — the shape
# every money anchor in this repo already reads as money).
_VALUE_RE = re.compile(
    rf"(?P<money>{_SIGN}?{_CURRENCY}{_CUR_GAP}[-−]?{_NUM})"
    rf"|(?P<money_word>{_SIGN}?\b{_NUM}\s?{_CURRENCY_WORD}\b)"
    rf"|(?P<pct>\b{_NUM}\s?%)"
    r"|(?P<date>\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b)"
    rf"|(?P<keyed>{_KEYED})"
    rf"|(?P<unit>\b{_NUM}\s?{_UNIT}(?![\w]))"
    rf"|(?P<bare>{_SIGN}?(?:\b\d{{1,3}}(?:\.\d{{3}})*,\d{{2}}\b|\b\d{{1,3}}(?:,\d{{3}})*\.\d{{2}}\b))",
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


def _key_parts(key: str) -> "list[str]":
    """A machine key's parts: ``window_days`` → window, days."""
    return [p.lower() for p in key.split("_") if p]


def _keyed_unit(m: "re.Match[str]") -> Optional[Key]:
    """``("unit", value, unit)`` when ONE part of the machine key names a unit of time, else
    ``None`` — a key that names no unit (``id``, ``count``, ``amount``) reads nothing, so a bare
    ``7`` under it never becomes "7 dias". Two parts naming two different units: nothing either,
    the key does not say which."""
    key = m.group("qk") or m.group("sk") or m.group("ek") or ""
    units = {_KEY_UNIT_WORDS[p] for p in _key_parts(key) if p in _KEY_UNIT_WORDS}
    value = _amount(m.group("kn"))
    if len(units) != 1 or value is None:
        return None
    return ("unit", value.normalize(), units.pop())


def _negative(text: str, num_start: int) -> bool:
    """A minus sign written before the number (or before its currency symbol)."""
    return any(ch in "-−" for ch in text[:num_start])


def _key(m: "re.Match[str]") -> Optional[Key]:
    kind = m.lastgroup or ""
    text = m.group(0)
    if kind == "keyed":
        return _keyed_unit(m)
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
        if num is not None and _negative(text, num.start()):
            value = -value
        return ("money", value.quantize(Decimal("0.01")))
    if kind == "pct":
        return ("pct", value.normalize())
    if kind == "unit":
        unit = text[num.end():].strip().lower() if num else ""
        return ("unit", value.normalize(), _UNIT_WORDS.get(unit, unit))
    return None


def _literal(m: "re.Match[str]") -> str:
    """The value as written, whitespace collapsed — and, for money, without the markdown emphasis
    a broken bold left between the symbol and the number (``**R$**\n**1.440**`` → ``R$ 1.440``),
    so a prompt that shows it shows a value and the grammar reads it back as the same key."""
    text = m.group(0)
    if m.lastgroup == "money":
        text = re.sub(r"[*_]", "", text)
    return " ".join(text.split())


def _scan(text: str) -> "Iterable[tuple[str, Key]]":
    for m in _VALUE_RE.finditer(text or ""):
        k = _key(m)
        if k is not None:
            yield _literal(m), k


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

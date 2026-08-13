"""Exact arithmetic for the bookkeeper — the ``math`` tool's engine.

Money, so :class:`~decimal.Decimal` and never ``float``: 0.1 + 0.2 must be 0.3 for someone
keeping books, and "0.30000000000000004" reaching a voicer is worse than no answer.

Evaluation is a whitelisted AST walk — never ``eval``. An expression carrying anything but
numbers, the five operators, parentheses and a unary sign is REFUSED with the reason, never
coerced into something that looks like an answer.

Pure and importable on its own: the MCP tool in ``server.py`` is only a shell over
:func:`evaluate`, so "what is allowed" has exactly one definition.
"""

from __future__ import annotations

import ast
import operator
import re
from decimal import (Decimal, DecimalException, ROUND_HALF_UP,
                     localcontext)
from typing import Any

_BINOPS: "dict[type, Any]" = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY: "dict[type, Any]" = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# Bounds against expressions that are cheap to type and expensive to evaluate (9**9**9).
_MAX_EXPONENT = 12
_MAX_LEN = 200
# A repeating division in full Decimal precision is 28 digits and the voicer reproduces
# figures verbatim, so the TAIL is capped for presentation. Capped, NOT crushed to cents:
# quantizing to 2 places turned 35/1000 into 0.04 (a 14% error) and 7/2000 into 0 — a tool
# whose description promises "EXACTLY" shipping a wrong number is worse than a long one.
# Six places keeps unit costs and per-item ratios intact.
_MAX_PLACES = Decimal("0.000001")

# ANY dot followed by exactly three digits is refused. Both readings are real — "1.850" is
# pt-BR for 1850, "1.075" is a 7.5% multiplier — and the tool cannot know which, so it must
# not choose: the two failures are not symmetric. A refusal is recoverable text the EGO
# feeds straight back to the model; a WRONG number is not detectable anywhere downstream and
# the voicer reproduces it verbatim. Measured on the previous revision, which allowed the
# single-dot form: "12.500 + 3.000" answered 15.5 instead of 15500.
#
# The refusal names the unambiguous rewrite, so the model recovers in one step instead of
# rephrasing the same ambiguity (the resolve_date lesson).
# A leading zero excludes the thousands reading ("0.035" can only be a fraction).
_AMBIGUOUS_DOT_GROUP = re.compile(r"\b[1-9]\d{0,2}\.\d{3}\b")


class MathError(ValueError):
    """Refused expression — carries the reason the model is told."""


def _eval(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise MathError(f"{node.value!r} is not a number")
        # str() first: Decimal(0.1) carries the float's error, Decimal("0.1") does not.
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow):
            if right != right.to_integral_value() or abs(right) > _MAX_EXPONENT:
                raise MathError(
                    f"exponent {right} is not allowed (whole numbers up to {_MAX_EXPONENT})")
        return _BINOPS[type(node.op)](left, right)
    raise MathError("only numbers and + - * / ** ( ) are allowed — no names, "
                    "functions or comparisons")


def evaluate(expression: str) -> Decimal:
    """Evaluate an arithmetic expression exactly. Raises :class:`MathError` when refused."""
    expr = (expression or "").strip()
    if not expr:
        raise MathError("empty expression")
    if len(expr) > _MAX_LEN:
        raise MathError(f"expression too long (max {_MAX_LEN} characters)")
    # The thousands separator is REFUSED, not guessed: "1,5" is one-and-a-half in pt-BR and
    # Python reads it as a TUPLE — either guess ships a wrong number as a right-looking one.
    if "," in expr:
        raise MathError("use '.' for decimals and no thousands separator: 1234.56, not "
                        "1.234,56 or 1,234.56")
    if match := _AMBIGUOUS_DOT_GROUP.search(expr):
        # Quote what THEY sent, not a literal from the source — an earlier message named
        # "1.850" at a caller who never wrote it.
        token = match.group(0)
        whole, frac = token.split(".")
        raise MathError(
            f"{token!r} is ambiguous — {whole}{frac} (thousands) or {whole} and {frac}"
            f" thousandths? Send {whole}{frac}, or write the fraction as "
            f"{whole}{frac}/1000.")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise MathError(f"not a valid arithmetic expression: {exc.msg}") from exc
    try:
        with localcontext() as ctx:
            ctx.prec = 28
            result = _eval(tree)
        if not result.is_finite():
            # Decimal saturates to Infinity/NaN instead of raising. Returning it would voice
            # "Infinity" to a business owner as if it were a figure — refuse it as what it
            # is: a number too large to be an answer.
            raise MathError("the result is too large to be a real figure — check the numbers")
        return result
    except MathError:
        raise
    except DecimalException as exc:
        # EVERY decimal failure, not a hand-listed few: Overflow and InvalidOperation are
        # DecimalException subclasses but NOT OverflowError/ValueError, so the old tuple let
        # them escape and the MCP tool RAISED where its contract says it returns a
        # recoverable "ERROR: ..." string.
        kind = type(exc).__name__
        raise MathError("division by zero" if "DivisionByZero" in kind
                        else f"could not evaluate: {kind}") from exc
    except (OverflowError, ValueError) as exc:
        raise MathError(f"could not evaluate: {exc}") from exc


def format_number(value: Decimal, *, cap_tail: bool = True) -> str:
    """Plain decimal string — no scientific notation, no 28-digit tails.

    ``cap_tail`` caps a repeating result at six decimals (100/3 → 33.333333), which is the
    long-tail problem without the wrong-number one: an earlier version quantized to CENTS
    and turned 35/1000 into 0.04 and 7/2000 into 0. Exact results are never padded (1998
    stays "1998") and never touched — only a tail longer than six places is rounded, with
    commercial ROUND_HALF_UP.
    """
    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    # ``as_tuple().exponent`` is an int for a finite Decimal and a marker string for
    # NaN/Infinity — neither of which arrives here (the evaluator raises first), but the
    # type says otherwise and a silent TypeError in a money path is not worth the shortcut.
    if cap_tail and isinstance(exponent, int) and -exponent > 6:
        # ROUND_HALF_UP, not Decimal's default banker's rounding. It only bites on the
        # 7th decimal place (everything shorter is returned untouched), so it is about the
        # LAST digit of a long tail — 1/3 rendering as 0.333333 and 2/3 as 0.666667 — not
        # about cents. An earlier comment here claimed it produced 0.13 for 2.50*0.05; the
        # function returns 0.125, exactly, and always did.
        normalized = value.quantize(_MAX_PLACES, rounding=ROUND_HALF_UP).normalize()
    if normalized == normalized.to_integral_value():
        # normalize() renders 2500 as 2.5E+3 — quantize back to the plain integer form.
        # A huge exponent cannot be quantized (InvalidOperation); ``format`` renders it
        # plainly anyway, so the shortcut is skipped rather than allowed to raise HERE,
        # outside the evaluator's try, where the tool's "recoverable ERROR:" contract
        # does not reach.
        try:
            normalized = normalized.quantize(Decimal(1))
        except DecimalException:
            pass
    return format(normalized, "f")

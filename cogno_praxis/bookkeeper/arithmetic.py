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
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
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
# Money is quoted to cents. 100/3 in full Decimal precision is 28 digits, and the voicer
# reproduces figures verbatim — so a division result is rounded for presentation while the
# exact value stays available to callers that want it.
_MONEY_PLACES = Decimal("0.01")


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
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise MathError(f"not a valid arithmetic expression: {exc.msg}") from exc
    try:
        with localcontext() as ctx:
            ctx.prec = 28
            return _eval(tree)
    except MathError:
        raise
    except DivisionByZero as exc:
        raise MathError("division by zero") from exc
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise MathError(f"could not evaluate: {exc}") from exc


def format_number(value: Decimal, *, money: bool = True) -> str:
    """Plain decimal string — no scientific notation, no 28-digit tails.

    ``money`` rounds a non-terminating result to cents (100/3 → 33.33): the figure is spoken
    verbatim, and a 28-digit tail is noise a business owner cannot use. An exact result is
    never padded — 1998 stays "1998", not "1998.00".
    """
    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    # ``as_tuple().exponent`` is an int for a finite Decimal and a marker string for
    # NaN/Infinity — neither of which arrives here (the evaluator raises first), but the
    # type says otherwise and a silent TypeError in a money path is not worth the shortcut.
    if money and isinstance(exponent, int) and -exponent > 2:
        normalized = value.quantize(_MONEY_PLACES).normalize()
    if normalized == normalized.to_integral_value():
        # normalize() renders 2500 as 2.5E+3 — quantize back to the plain integer form.
        normalized = normalized.quantize(Decimal(1))
    return format(normalized, "f")

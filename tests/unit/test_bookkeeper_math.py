"""The bookkeeper's ``math`` tool — evaluator, MCP surface, and grounding.

It lives HERE, with the vertical, because that is what it is: a bookkeeping tool. A first
attempt put it in the host as a builtin, and the placement itself produced a defect — the
vertical's grounding rule grounds figures against ITS OWN tools, could not see a host
builtin, and rewrote a legitimately computed answer into "let me check the real numbers in
the system". Same repo, same rule, no exception needed anywhere else.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from cogno_praxis.bookkeeper.arithmetic import MathError, evaluate, format_number
from cogno_praxis.bookkeeper.grounding import ground_reply
from cogno_praxis.bookkeeper.server import build_server
from cogno_praxis.grounding import ToolCall


# ── the evaluator ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("expr,expected", [
    ("1850 * 1.08", "1998"),          # a reajuste — the motivating case
    ("(1200 - 340) / 4", "215"),
    ("0.1 + 0.2", "0.3"),             # Decimal, not float: 0.30000000000000004 is not money
    ("2 ** 10", "1024"),
    ("-5 + 3", "-2"),
    ("1000 * 0.15", "150"),
])
def test_exact_arithmetic(expr, expected):
    assert format_number(evaluate(expr)) == expected


@pytest.mark.parametrize("bad,reason", [
    ("__import__('os').system('ls')", "only numbers"),   # the eval() nightmare, refused
    ("x + 1", "only numbers"),
    ("abs(-3)", "only numbers"),
    ("1 > 2", "only numbers"),
    ("9**9**9", "exponent"),                             # cheap to type, expensive to run
    ("1/0", "division by zero"),
    ("", "empty"),
    ("1850 *", "not a valid arithmetic expression"),
])
def test_refused_with_a_reason(bad, reason):
    with pytest.raises(MathError, match=reason):
        evaluate(bad)


def test_the_comma_is_refused_not_guessed():
    """'1,5' is one-and-a-half in pt-BR — and a TUPLE in Python. Guessing either way ships a
    wrong number as a right-looking answer, so it is refused with the correct form."""
    with pytest.raises(MathError, match="use '.' for decimals"):
        evaluate("1,5 * 2")
    with pytest.raises(MathError):
        evaluate("1.234,56 + 1")


def test_the_tail_is_CAPPED_never_crushed_to_cents():
    """Review finding, and the worst kind: the first version quantized to CENTS to kill the
    28-digit tail, and a tool promising "EXACTLY" started shipping wrong numbers — 35/1000
    became 0.04 (14% off) and 7/2000 became 0. Six places kills the tail and keeps unit
    costs and per-item ratios intact."""
    assert format_number(evaluate("35/1000")) == "0.035"
    assert format_number(evaluate("7/2000")) == "0.0035"
    assert format_number(evaluate("100/3")) == "33.333333"
    # commercial rounding, not Decimal's banker's default: the client's invoice says 0,13
    assert format_number(evaluate("2.50 * 0.05")) == "0.125"
    assert format_number(Decimal("0.1255")) == "0.1255"


def test_money_rounding_and_no_scientific_notation():
    """The voicer reproduces figures verbatim, so "2.5E+3" would be SPOKEN to a business
    owner and a 28-digit tail is noise nobody can use. Exact results are never padded."""
    assert format_number(evaluate("2500 * 1")) == "2500"
    assert format_number(evaluate("1850 * 1.08")) == "1998"      # not "1998.00"
    assert "E" not in format_number(evaluate("2500000 * 2"))
    # the exact value stays available for a caller that wants it
    assert evaluate("100/3") != Decimal("33.33")


def test_the_tool_ACCEPTS_ITS_OWN_output():
    """A guard whose recovery path manufactures the failure it guards against has negative
    value. The ambiguity guard refused format_number's own three-decimal output (385/8 =
    48.125, handed straight back on the next loop step) and told the model to resend 48125 —
    a 1000x error the grounding backstop then blessed as a real computation."""
    computed = format_number(evaluate("385/8"))
    assert computed == "48.125"
    assert format_number(evaluate(f"{computed} * 2")) == "96.25"
    # the multipliers the tool is advertised for
    assert format_number(evaluate("1850 * 1.075")) == "1988.75"
    # only the form that can be nothing but thousands is refused
    with pytest.raises(MathError, match="thousands separator"):
        evaluate("1.234.567 + 1")


def test_a_result_too_large_to_be_a_figure_is_refused():
    """Decimal saturates to Infinity instead of raising, and "Infinity" would be SPOKEN to a
    business owner as if it were an answer. Also pins the exception contract: Overflow and
    InvalidOperation are DecimalException — not OverflowError — so a hand-listed tuple let
    them escape and the MCP tool RAISED where it promises a recoverable "ERROR:" string."""
    with pytest.raises(MathError, match="too large"):
        evaluate("1e400 * 1e400")


def test_a_long_expression_is_refused():
    with pytest.raises(MathError, match="too long"):
        evaluate("1+" * 200 + "1")


# ── the MCP surface ──────────────────────────────────────────────────────────────────
def _call(tool: str, args: dict) -> str:
    content, _ = asyncio.run(build_server().call_tool(tool, args))
    return content[0].text


def test_math_is_a_read_only_tool_of_this_server():
    mcp = build_server()
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    assert "math" in tools, "the bookkeeper's own tool set — not a host builtin"
    ann = tools["math"].annotations
    # read-only: no confirmation gate, no read-only mask — it computes, it does not write
    assert ann.readOnlyHint is True and not getattr(ann, "destructiveHint", False)
    # the DESCRIPTION is the promise the model reads: it must be the small one
    assert "does NOT read the books" in (tools["math"].description or "")


def test_the_tool_returns_the_figure_and_the_error_says_what_to_do():
    assert "1998" in _call("math", {"expression": "1850 * 1.08"})
    refused = _call("math", {"expression": "preço * 1.08"})
    assert refused.startswith("ERROR:")          # the module's recoverable-failure convention
    # the resolve_date lesson: name the ACTION, not only the allowed forms
    assert "ASK the user" in refused


# ── grounding: a computed figure is NOT a conjured total ─────────────────────────────
_SAYS_A_TOTAL = "O total com o reajuste fica R$ 48,60."


def test_math_grounds_a_computed_reply_exactly_like_its_SIBLING_reads():
    """Eight review rounds went into making this figure-WISE — does every amount in the reply
    trace to a computation? — and each round of that parser shipped a defect in one direction
    or the other. What ended it: the rule was NEVER figure-wise. ``get_summary`` puts one
    number in hand and exempts the whole reply, so a fabricated balance beside a real read
    already passes. Holding ``math`` to a stricter standard than the rule's own baseline cost
    120 lines of parser that was wrong more often than right.

    This pins the SYMMETRY, so a future author cannot 'tighten' math alone again without the
    test naming why that asymmetry is the bug."""
    say = "O total do mês é R$ 12.400,00."
    fabricated_beside = "Entrou R$ 200,00. Seu saldo acumulado é R$ 987.654,00."
    for tool in ("get_summary", "search", "math"):
        result = "45 * 1.08 = 48.6" if tool == "math" else "Entradas: R$ 200,00"
        assert ground_reply(say, tools=[ToolCall(tool=tool, result=result,
                                                 ok=True)]) is None, tool
        # the rule's PRE-EXISTING exposure, identical for all three — not a math-only hole
        assert ground_reply(fabricated_beside,
                            tools=[ToolCall(tool=tool, result=result, ok=True)]) is None, tool


def test_a_computed_figure_grounds_the_reply():
    """The defect that proved the placement: with math outside this module, ``conjured_totals``
    could not see it and rewrote the answer. Here the rule grounds it like any other read."""
    assert ground_reply(_SAYS_A_TOTAL, tools=[]) is not None          # no read at all → caught
    grounded = ground_reply(_SAYS_A_TOTAL, tools=[
        ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True)])
    assert grounded is None


def test_a_REFUSED_math_call_grounds_nothing():
    """A refusal is exactly the turn where the model failed to compute and may have guessed —
    handing it the exemption would invert the rule. Refusals ride an "ERROR:" string (ok=True
    at the MCP layer, the add_income convention), so ``ok`` alone is not the test."""
    verdict = ground_reply(_SAYS_A_TOTAL, tools=[
        ToolCall(tool="math", result="ERROR: could not compute", ok=True)])
    assert verdict is not None and verdict.rule == "conjured_totals"


def test_the_persona_prompt_carries_the_arithmetic_rule_and_its_boundary():
    """The duty belongs to the persona that owns the tool — not to a host flag. Both halves
    must be there: never compute in your head, AND math is not how the books are totalled."""
    from pathlib import Path

    import cogno_praxis
    text = (Path(cogno_praxis.__file__).resolve().parent / "bookkeeper" / "prompts"
            / "system.txt").read_text(encoding="utf-8")
    assert "math()" in text
    assert "get_summary" in text.split("## Arithmetic", 1)[1]

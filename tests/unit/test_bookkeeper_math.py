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


def test_money_rounding_and_no_scientific_notation():
    """The voicer reproduces figures verbatim, so "2.5E+3" would be SPOKEN to a business
    owner and a 28-digit tail is noise nobody can use. Exact results are never padded."""
    assert format_number(evaluate("100/3")) == "33.33"
    assert format_number(evaluate("2500 * 1")) == "2500"
    assert format_number(evaluate("1850 * 1.08")) == "1998"      # not "1998.00"
    assert "E" not in format_number(evaluate("2500000 * 2"))
    # the exact value stays available for a caller that wants it
    assert evaluate("100/3") != Decimal("33.33")


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

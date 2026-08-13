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


def test_an_AMBIGUOUS_dot_group_is_refused_never_guessed():
    """Third position on this guard, and the reasoning that settles it: "1.850" is pt-BR for
    1850 and "1.075" is a 7.5% multiplier — the tool cannot know which, so it must not pick.
    The two failures are NOT symmetric. A refusal is recoverable text the EGO feeds straight
    back; a WRONG number is invisible downstream and the voicer speaks it verbatim.

    Measured on the revision that allowed the single-dot form: "12.500 + 3.000" answered
    15.5 instead of 15500."""
    for ambiguous in ("12.500 + 3.000", "1.850 * 2", "1850 * 1.075", "2.500 / 2"):
        with pytest.raises(MathError, match="ambiguous"):
            evaluate(ambiguous)
    # a leading zero excludes the thousands reading — these are plain fractions
    assert format_number(evaluate("0.035 * 2")) == "0.07"
    assert format_number(evaluate("1998.005 + 0")) == "1998.005"
    # two decimals are never a thousands group
    assert format_number(evaluate("45 * 1.08")) == "48.6"


def test_the_refusal_shows_BOTH_readings_and_how_to_send_each():
    """It quotes the caller's own token (an earlier message named "1.850" at someone who
    never wrote it) and names the unambiguous rewrite, so the model recovers in one step
    instead of rephrasing the same ambiguity — the resolve_date lesson."""
    with pytest.raises(MathError) as exc:
        evaluate("1.075 * 1000")
    message = str(exc.value)
    assert "'1.075'" in message          # what they sent
    assert "1075" in message             # the thousands reading
    assert "1075/1000" in message        # how to write the fraction instead


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


def test_a_computed_figure_grounds_the_reply():
    """The defect that proved the placement: with math outside this module, ``conjured_totals``
    could not see it and rewrote the answer. Here the rule grounds it like any other read."""
    assert ground_reply(_SAYS_A_TOTAL, tools=[]) is not None          # no read at all → caught
    grounded = ground_reply(_SAYS_A_TOTAL, tools=[
        ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True)])
    assert grounded is None


def test_grounding_ignores_numerals_that_are_not_amounts():
    """Requiring EVERY numeral to come from math un-grounded correct answers: "o total com o
    reajuste de 8% fica R$ 48,60" failed on the 8, and so did any reply naming a year or an
    item count. Only MONEY amounts are claims about the books."""
    computed = [ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True)]
    for reply in ("O total com o reajuste de 8% fica R$ 48,60.",
                  "Em 2026 o total fica R$ 48,60.",
                  "São 3 cortes; o total com reajuste fica R$ 48,60."):
        assert ground_reply(reply, tools=computed) is None, reply


def test_grounding_follows_the_LOCALE_not_a_hardcoded_pt_BR():
    """`ground_reply` receives ``locale`` and the amount parsing must follow it: an English
    reply writes "$48.60" (dot decimal), and reading the dot as a thousands separator turned
    it into 4860 — making the exemption unreachable for 100% of English turns."""
    computed = [ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True)]
    assert ground_reply("The total with the increase is $48.60.",
                        tools=computed, locale="en") is None
    smuggled = ground_reply("The total is $48.60. Your balance is $12,400.00.",
                            tools=computed, locale="en")
    assert smuggled is not None and smuggled.rule == "conjured_totals"


def test_math_grounds_ONLY_the_figures_it_produced():
    """Review finding, the most dangerous: the exemption was turn-WIDE, so any successful
    math call excused the whole reply and a fabricated ledger total shipped alongside a
    legitimate computation. Unlike get_summary/search, math reads nothing — it echoes back
    numbers the model supplied, so it can only ground what it actually returned."""
    computed = [ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True)]
    assert ground_reply("O total com o reajuste fica R$ 48,60.", tools=computed) is None
    smuggled = ground_reply(
        "O corte fica R$ 48,60. Seu saldo do mês está em R$ 12.400,00.", tools=computed)
    assert smuggled is not None and smuggled.rule == "conjured_totals"


def test_an_operand_the_model_TYPED_does_not_ground_anything():
    """The result echoes the caller's expression ("12400 * 1 = 12400"), so scanning the whole
    string grounded every number the MODEL supplied — one throwaway call laundered an
    invented balance past the backstop. Only the right-hand side counts, and an identity
    operation (result also among the operands) counts for nothing: that IS the laundering
    shape."""
    laundered = ground_reply(
        "O corte fica R$ 48,60. Saldo: R$ 12.400,00.",
        tools=[ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True),
               ToolCall(tool="math", result="12400 * 1 = 12400", ok=True)])
    assert laundered is not None and laundered.rule == "conjured_totals"


def test_the_TOOL_side_is_read_canonically_never_ambiguously():
    """The dual reading is safe on the REPLY (the voicer's convention is unknown) and unsound
    on the TOOL output (machine-written, dot-decimal). Applying it to both made a computed
    48.6 also count as 486, so a fabricated "saldo de R$ 486,00" was grounded by a
    computation of R$ 48,60 — an order of magnitude out, blessed by the guard."""
    computed = [ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True)]
    inflated = ground_reply("Seu saldo total do mês é R$ 486,00.", tools=computed)
    assert inflated is not None and inflated.rule == "conjured_totals"
    assert ground_reply("O total com reajuste fica R$ 48,60.", tools=computed) is None


def test_a_number_the_parser_cannot_account_for_REFUSES_the_exemption():
    """The direction a fabrication guard must never take is fail-OPEN, and the amount regex
    silently took it: "12 mil reais" and a bare "12.400" were invisible, so an invented
    balance rode along beside one legitimate computed figure. An unaccounted number now
    refuses the exemption — the weaker the parse, the SAFER the outcome."""
    computed = [ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True)]
    for smuggled in ("Seu total fica R$ 48,60 e o faturamento foi 12 mil reais.",
                     "O total fica R$ 48,60. Saldo do mês: 12.400.",
                     "O total fica R$ 48,60. Saldo: 12400 reais."):
        verdict = ground_reply(smuggled, tools=computed)
        assert verdict is not None and verdict.rule == "conjured_totals", smuggled
    # …while numbers that are plainly NOT money keep a correct reply intact
    for fine in ("São 3 cortes; o total fica R$ 48,60.",
                 "Em 2026 o total fica R$ 48,60.",
                 "O total com reajuste de 8% fica R$ 48,60."):
        assert ground_reply(fine, tools=computed) is None, fine


def test_an_amount_written_any_common_way_is_recognised():
    """Six revisions of locale-keyed parsers each failed in one direction. This one does not
    DECIDE what a separator means — it reads a candidate both ways and a match under either
    counts, which is sound because a value only passes if math actually computed it."""
    computed = [ToolCall(tool="math", result="45 * 1.08 = 48.6", ok=True)]
    # The LOCALE selects which bundle's money detector runs at all (a pt bundle does not
    # recognise "$48.60"), so it travels with each phrasing here — as it does in production.
    for grounded, locale in (("O total fica R$ 48,60.", "pt"),        # pt-BR voicer
                             ("O total fica R$ 48.60.", "pt"),        # the TOOL's own output,
                             ("The total is $48.60.", "en")):         # quoted verbatim
        assert ground_reply(grounded, tools=computed, locale=locale) is None, grounded
    # …and an amount math did NOT produce is caught however it is written
    for fabricated, locale in (("O corte fica R$ 48,60. Saldo: R$ 12.400,00.", "pt"),
                               ("O corte fica R$ 48,60. Saldo: 12.400 reais.", "pt"),
                               ("The total is $48.60. Your balance is $12,400.00.", "en")):
        verdict = ground_reply(fabricated, tools=computed, locale=locale)
        assert verdict is not None and verdict.rule == "conjured_totals", fabricated


def test_a_rounded_rendering_of_a_long_tail_still_grounds():
    """The voicer quotes cents ("R$ 33,33") for a value the tool returned as 33.333333 —
    the same claim, and demanding the exact string rewrote correct replies."""
    assert ground_reply("Cada folha sai a R$ 33,33.",
                        tools=[ToolCall(tool="math", result="100/3 = 33.333333",
                                        ok=True)]) is None


def test_the_SIGN_is_part_of_the_figure():
    """A computed LOSS voiced as a profit is a different claim: dropping the sign on either
    side grounded "o total do mês é R$ 500,00" against a computed -500."""
    loss = [ToolCall(tool="math", result="300 - 800 = -500", ok=True)]
    flipped = ground_reply("O total do mês é R$ 500,00.", tools=loss)
    assert flipped is not None and flipped.rule == "conjured_totals"
    assert ground_reply("O resultado do mês é -R$ 500,00.", tools=loss) is None


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

"""The BOOKKEEPER voice writes numbers in the system's format, pt-BR — only the MARKS change.

The platform owner asked for the figures in the format the panel uses, pt-BR: the currency as R$,
a decimal comma, a thousands dot, dates as dd/mm/aaaa. The core calls a ROUNDED figure invented —
anima's ``_FIGURES_HAVE_A_SOURCE`` in the voice ``# Task``, and the divergence net
(``SuperegoStage._draft_divergence``), which re-runs the voice when a figure of the reply is not in
the data — so the rule keeps every decimal the data carries and never rounds, and the voice's own
«present figures exactly as the tools returned them … never round» still holds: the value and the
decimals do not move, only the marks do.

GEMEO: every «RIGHT», never «WRONG» pair of the rule survives the net with WRONG as the data (the
consultor's method on praxis #198). CONTROL: the net is live — a figure the data does not hold is
flagged. Pure, no model.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

VOICE = Path(__file__).resolve().parents[2] / "cogno_praxis" / "bookkeeper" / "prompts" / "voice.txt"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _rule() -> str:
    flat = _flat(VOICE.read_text(encoding="utf-8"))
    return flat[flat.index("In a reply in Portuguese, write them in the system's format"):]


def _pairs() -> "list[tuple[str, str]]":
    return re.findall(r"«([^»]+)», never «([^»]+)»", _rule())


@pytest.mark.parametrize("phrase", [
    "In a reply in Portuguese, write them in the system's format, pt-BR — only the MARKS change, "
    "never the value or its decimals",
    "the currency as R$, a decimal comma and a thousands dot",
    "«R$ 1.234,5678», never «R$ 1,234.5678»",
    "and dates as dd/mm/aaaa («04/11/2026», never «2026-11-04»)",
    # the line the rule must not contradict
    "Present figures exactly as the tools returned them (amounts, totals, dates, client names) — "
    "never round, alter, or invent a number.",
])
def test_the_voice_carries_the_pt_br_marks_rule(phrase):
    assert phrase in _flat(VOICE.read_text(encoding="utf-8"))


def test_the_rule_gives_a_money_and_a_date_example():
    pairs = _pairs()
    assert len(pairs) >= 3, pairs
    assert any("R$" in right for right, _ in pairs) and any("/" in right for right, _ in pairs)


def test_GEMEO_no_example_of_the_rule_is_an_invented_figure():
    from cogno_anima.stages.superego import SuperegoStage
    flagged = {}
    for right, wrong in _pairs():
        _lost, invented = SuperegoStage._draft_divergence(wrong, wrong, right)
        if invented:
            flagged[right] = invented
    assert not flagged, ("the rule orders the voice to write a figure the core's net calls "
                         f"invented over the data it names: {flagged}")


def test_CONTROLO_the_net_flags_a_figure_the_data_does_not_hold():
    from cogno_anima.stages.superego import SuperegoStage
    _lost, invented = SuperegoStage._draft_divergence("R$ 2.5832", "R$ 2.5832", "R$ 3,10")
    assert invented == ["310"]



def test_GEMEO_the_pt_br_marks_are_for_a_reply_in_portuguese_only():
    """The consultor on #199: the bookkeeper also answers in English and Spanish (its grounding
    bundles), and the voice writes IN the user's language — an English reader of «R$ 1.234,56»
    reads about 1.23, and of «04/11/2026» reads April 11. So the pt-BR marks are conditioned on
    a reply in Portuguese; another language keeps its own marks; «never round» holds for all."""
    flat = _flat(VOICE.read_text(encoding="utf-8"))
    assert "In a reply in Portuguese, write them in the system's format, pt-BR" in flat
    assert "In a reply in another language, keep that language's marks." in flat
    assert "In every language, keep every decimal the data carries and never round." in flat
    # the unconditioned form is gone: no «pt-BR — never the English one» for every reply
    assert "never the English one" not in flat


def test_CONTROLO_the_three_pairs_are_still_given():
    assert _pairs() == [("R$ 1.234,5678", "R$ 1,234.5678"), ("R$ 2,5832", "R$ 2.5832"),
                        ("04/11/2026", "2026-11-04")]

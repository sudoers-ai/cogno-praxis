"""Consultor twin, praxis #198 (NEO numbers in pt-BR): the rule may not order a rounding the core
calls invention.

The new voice line gives its examples as «RIGHT», never «WRONG». The WRONG side of the money pair
is what the host's cost reader prints today (``analytics_adapter.py``: ``R$ {x:.4f}``), so the
rule orders the voice to turn the data's ``R$ 2.5832`` into ``R$ 2,58``. The core says the
opposite twice:

* in the prompt — anima's ``_FIGURES_HAVE_A_SOURCE`` (the voice ``# Task``): «A figure you
  remember, assume or ROUND is invented: leave it out»;
* in code — the divergence net (``SuperegoStage._draft_divergence``, on every turn the judge
  approved and every call ran ok — a clean cost read): ``R$ 2,58`` over data ``R$ 2.5832`` is
  invented ``258``, the voice is re-run with «HARD RULE — REWRITE», and the second reply wins as
  soon as it keeps the four decimals. Measured on anima 9af154a (the host's pin).

So on the very turn the rule is for, the net undoes it and pays a second voice call; on a turn
without an approved draft the model holds two contradictory hard rules. The panel the owner named
as the format («registado na UI») does not round below a cent either: ``fmtCurrency`` in
``tokens/page.tsx`` writes 4 decimals when 0 < value < 0.01, where «2 decimals» says «R$ 0,00».

GEMEO: every «RIGHT», never «WRONG» pair of the numbers rule survives the net with WRONG as the
data. CONTROL: the net is live — a figure that is not in the data is flagged. Pure, no model."""
from __future__ import annotations

import re
from pathlib import Path

from cogno_anima.stages.superego import SuperegoStage

VOICE = Path(__file__).resolve().parents[2] / "cogno_praxis" / "admin" / "prompts" / "voice.txt"


def _numbers_rule() -> str:
    flat = " ".join(VOICE.read_text(encoding="utf-8").split())
    start = flat.index("Numbers come in the system's format")
    return flat[start:]


def _pairs() -> "list[tuple[str, str]]":
    return re.findall(r"«([^»]+)», never «([^»]+)»", _numbers_rule())


def test_the_rule_gives_examples_to_check():
    assert len(_pairs()) >= 2, _pairs()


def test_GEMEO_no_example_of_the_rule_is_an_invented_figure():
    flagged = {}
    for right, wrong in _pairs():
        _lost, invented = SuperegoStage._draft_divergence(wrong, wrong, right)
        if invented:
            flagged[right] = invented
    assert not flagged, ("the rule orders the voice to write a figure the core's net calls "
                         f"invented over the data it names: {flagged}")


def test_CONTROLO_the_net_flags_a_figure_the_data_does_not_hold():
    _lost, invented = SuperegoStage._draft_divergence("R$ 2.5832", "R$ 2.5832", "R$ 3,10")
    assert invented == ["310"]

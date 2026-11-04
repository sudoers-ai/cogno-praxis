"""The BOOKKEEPER asks the cost tool for a CHART, and the judge reads one as the tool's output
(request 777e9b69, on top of 66a0acf2).

The chart is drawn by ``cogno_praxis.charts`` inside the host's ``token_cost_analytics``
(``visual=…``) from the tool's own figures, so the executor never builds one and never writes a
value of its own. This repo owns the two lines that send the executor there and tell the judge
what the bars are. Both are ADDED lines; undoing them gives the request-1 head byte for byte.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from tests.unit.test_bookkeeper_ai_cost_by_week_and_model import VISUAL_LIMITS, VISUAL_SYSTEM
from tests.unit.test_bookkeeper_ai_cost_comes_from_the_cost_tool import _judge_prompt

PROMPTS = Path(__import__("cogno_praxis").__file__).resolve().parent / "bookkeeper" / "prompts"

#: ``sha256`` of the two files at the request-1 head (66a0acf2), before these lines.
SYSTEM_BEFORE = "39dc42bfe6049b242c61fd8f32e5cc3b58d3a775ca512c5bfdbb3614ac3bdc9a"
LIMITS_BEFORE = "1df9ae05f917bb18a1b2309e512f6cb33b629510a76c497d1d83845c376dc40a"


def _raw(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_executor_asks_the_cost_tool_for_the_chart():
    system = _raw("system.txt")
    assert system.count(VISUAL_SYSTEM) == 1
    assert 'visual="auto"' in system and "the tool sends the text version" in _flat(system)


def test_the_judge_reads_the_bars_as_a_picture_of_the_figures():
    assert _raw("limits.txt").count(VISUAL_LIMITS) == 1


def test_undoing_the_two_lines_gives_the_request_1_head_byte_for_byte():
    assert _sha(_raw("system.txt").replace(VISUAL_SYSTEM, "", 1)) == SYSTEM_BEFORE
    assert _sha(_raw("limits.txt").replace(VISUAL_LIMITS, "", 1)) == LIMITS_BEFORE


def test_the_judge_prompt_carries_the_chart_rule_and_the_text_before_does_not():
    before = _raw("limits.txt").replace(VISUAL_LIMITS, "", 1)
    rule = "its bars are a picture of the figures written beside them"
    assert rule not in _flat(_judge_prompt(before))
    assert rule in _flat(_judge_prompt(_raw("limits.txt")))

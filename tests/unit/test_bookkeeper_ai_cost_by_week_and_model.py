"""The BOOKKEEPER's text knows the AI-cost report by WEEK and by MODEL, the split by model, and the
«Not available» answer — and ``get_usage`` says the report is not on the turn (request 66a0acf2).

The request the owner approved: the bookkeeper's AI-cost analysis delivers aggregated reports by
model and by week, with a series fit for a chart; the tool takes granularity, period and dimension
coherently and says clearly when a dimension is not available; AI costs stay apart from the books'
expenses. The tool is the host's ``token_cost_analytics`` (``cogno-host``: ``week``/``model`` cuts,
``by="model"``, ``format="json"``); this repo owns the text that sends the executor there and the
judge's rule that grounds what it returns.

What this file pins: the twins (the executor's mapping, the judge's approve line, ``get_usage``'s
note), the reconstruction (undoing the two lines gives ``origin/main`` 78d3db8 byte for byte, so
nothing else moved), and the judge prompt the core renders over the new ``limits.txt``.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from tests.unit.test_bookkeeper_ai_cost_comes_from_the_cost_tool import (CUR_DISTINGUISH,
                                                                          CUR_MAPPING,
                                                                          NEW_DISTINGUISH,
                                                                          NEW_MAPPING,
                                                                          _judge_prompt)

PKG = Path(__import__("cogno_praxis").__file__).resolve().parent
PROMPTS = PKG / "bookkeeper" / "prompts"

#: ``sha256`` of the two files at ``origin/main`` 78d3db8, before this request.
SYSTEM_BEFORE = "a6db743904c3ebbe812d4a39d781f06724e1248f48240c73b4f1fa59376c4ab8"
LIMITS_BEFORE = "e64431a18082ddbb734a328fbd1a6a2ee51207a2b060036667e7d00ceee5916a"


def _read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_executor_text_names_week_model_the_split_and_not_available():
    system = _flat(_read("system.txt"))
    assert ("by message, day, week, month, conversation, persona, user or model" in system)
    assert "token_cost_analytics(granularity?, period?, dimension?, by?)" in system
    assert 'by="model" splits a day/week/month cut by model' in system
    assert ('A cut it does not carry (per client, per expense category) comes back "Not '
            'available": say so, never rebuild it from the books.') in system


def test_the_judge_grounds_the_new_cuts_and_a_not_available_answer():
    limits = _flat(_read("limits.txt"))
    assert "(message, day, week, month, conversation, persona, user or model, and a time cut " \
           "split by model)" in limits
    assert ('its "Not available" for a cut it does not carry, reported as such, is CORRECT'
            in limits)


def test_get_usage_says_the_report_is_not_on_this_turn_and_never_in_the_books():
    from cogno_praxis.bookkeeper.service import BookkeeperService
    note = BookkeeperService.usage_note()
    assert "not available on this turn" in note and "host" in note
    assert "never AI cost" in note
    assert not any(ch.isdigit() for ch in note)          # a note, never a figure


def test_undoing_the_two_lines_gives_main_byte_for_byte():
    system, limits = _read("system.txt"), _read("limits.txt")
    assert _sha(system.replace(CUR_MAPPING, NEW_MAPPING, 1)) == SYSTEM_BEFORE
    assert _sha(limits.replace(CUR_DISTINGUISH, NEW_DISTINGUISH, 1)) == LIMITS_BEFORE
    assert _sha(system) != SYSTEM_BEFORE and _sha(limits) != LIMITS_BEFORE


def test_the_judge_prompt_carries_the_not_available_rule_and_the_old_text_does_not():
    new = _read("limits.txt")
    old = new.replace(CUR_DISTINGUISH, NEW_DISTINGUISH, 1)
    assert '"Not available"' not in _flat(_judge_prompt(old))      # the world before
    assert ('its "Not available" for a cut it does not carry, reported as such, is CORRECT'
            in _flat(_judge_prompt(new)))

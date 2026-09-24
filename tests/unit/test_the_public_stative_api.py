"""The stative decision is PUBLIC API — the host's generic net reads it, so its shape is pinned.

`bookkeeper.ground_reply` exempts the possessive stative («tenho registrado: R$ 10,00 de
aluguel») when every value in the reply is one the business declared and no ledger write was
called. A host's own generic net reads the SAME participle, and with a copy of the rule it
rewrote what this rule had passed. So the decision is exported — `write_attempted`,
`mask_possessive_stative`, `mask_declared_stative` — and a host calls it instead of copying it.
A rename or a change of meaning here is a contract change, and this file is where it shows.

Values invented.
"""

from __future__ import annotations

import pytest

import cogno_praxis.bookkeeper.grounding as bk
from cogno_praxis.bookkeeper.grounding import (ground_reply, mask_declared_stative,
                                               mask_possessive_stative, write_attempted)
from cogno_praxis.grounding import ToolCall

DECLARED = ("R$ 10,00", "2%")
STATIVE = "Tenho registrado o seguinte: R$ 10,00 de aluguel da sala."


def test_the_three_names_are_exported():
    for name in ("write_attempted", "mask_possessive_stative", "mask_declared_stative"):
        assert name in bk.__all__
        assert callable(getattr(bk, name))
    assert bk._write_attempted is write_attempted          # the old name still answers


@pytest.mark.parametrize("tools,expected", [
    ((), False),
    ((ToolCall(tool="get_summary", ok=True, result="Income: R$ 1,00"),), False),
    ((ToolCall(tool="add_outcome", ok=False, error="refused"),), True),     # CALLED, failed
    ((ToolCall(tool="remove_by_search", ok=True, result="Removed: x"),), True),
    ((ToolCall(tool="some_write", ok=True, side_effect=True),), True),       # unnamed write
])
def test_write_attempted_is_a_fact_about_the_calls(tools, expected):
    assert write_attempted(list(tools)) is expected


@pytest.mark.parametrize("reply,locale", [
    ("Tenho registrado: R$ 10,00.", "pt"),
    ("Temos aqui registrados R$ 10,00.", "pt"),
    ("Tengo registrado: €10,00.", "es"),
])
def test_mask_possessive_stative_blanks_the_stative_clause(reply, locale):
    masked = mask_possessive_stative(reply, locale)
    assert "registrad" not in masked.lower()
    assert "10,00" in masked                               # the rest of the reply is kept


@pytest.mark.parametrize("reply,locale", [
    ("Registrado! R$ 10,00.", "pt"),                       # the bare participle is not stative
    ("I have $10.00 recorded.", "en"),                     # en has no stative pattern
    ("Tenho registrado: R$ 10,00.", "xx"),                 # unsupported locale
])
def test_mask_possessive_stative_leaves_everything_else_alone(reply, locale):
    assert mask_possessive_stative(reply, locale) == reply


def test_mask_declared_stative_masks_only_under_both_conditions():
    assert "registrad" not in mask_declared_stative(
        STATIVE, declared_values=DECLARED, locale="pt").lower()
    # nothing declared / a value not declared / a write called → the reply unchanged
    assert mask_declared_stative(STATIVE, locale="pt") == STATIVE
    assert mask_declared_stative("Tenho registrado: R$ 12,00.", declared_values=DECLARED,
                                 locale="pt") == "Tenho registrado: R$ 12,00."
    called = [ToolCall(tool="add_outcome", ok=False, error="refused")]
    assert mask_declared_stative(STATIVE, tools=called, declared_values=DECLARED,
                                 locale="pt") == STATIVE


def test_ground_reply_reads_the_same_decision_it_exports():
    """The exported decision and the rule agree, on the non-read turn where the decision is the
    whole exemption: masked → no verdict; unmasked (a write called) → fabricated_entry."""
    assert ground_reply(STATIVE, tools=[], is_read_query=False, locale="pt",
                        declared_values=DECLARED) is None
    called = [ToolCall(tool="add_outcome", ok=False, error="refused")]
    v = ground_reply(STATIVE, tools=called, is_read_query=False, locale="pt",
                     declared_values=DECLARED)
    assert v is not None and v.rule == "fabricated_entry"

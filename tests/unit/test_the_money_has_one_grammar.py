"""One money grammar in this repo, pinned across the two files that spell it.

``bookkeeper`` #116 established the rule and paid for it: of the 19 money tokens contacts typed
at that vertical, 18 carried a comma decimal; of the 160 the tools answered with, 159 carried a
dot. The two halves of one conversation in two grammars, with nothing downstream reconciling
them — the voice prompt forbids the voicer from trying, and the preserved-term backstop flags it
if it does.

:func:`cogno_praxis.render.money_brl` is the shared renderer's copy of those three lines. It is
a copy because the canonical one lives in a file another author holds; what makes a copy safe is
a pin in BOTH directions, the same treatment this repo gives the duplicated ``cogno-mcp`` meta
keys. Collapse the two into one the day one author holds both files — this test survives the
collapse and keeps meaning something.

The values are the ones #116 was written for: the thousands separator is where the en-US reading
turns ``R$ 1.250`` into one and twenty-five.
"""

from __future__ import annotations

import pytest

from cogno_praxis.bookkeeper.server import _brl
from cogno_praxis.render import money_brl

_TABLE = [
    (0.0, "R$ 0,00"),
    (0.5, "R$ 0,50"),
    (45.0, "R$ 45,00"),
    (1250.0, "R$ 1.250,00"),
    (12500.9, "R$ 12.500,90"),
    (1234567.89, "R$ 1.234.567,89"),
    # The sign lands INSIDE, after the symbol. Recorded as it is rather than as it ought to
    # be: whether "R$ -1.250,00" or "-R$ 1.250,00" is right for a ledger is the bookkeeper's
    # question, and a shared renderer that quietly answered it differently would be the second
    # grammar this file exists to prevent.
    (-1250.0, "R$ -1.250,00"),
]


@pytest.mark.parametrize("value,expected", _TABLE)
def test_the_shared_renderer_writes_pt_br_money(value, expected):
    assert money_brl(value) == expected


@pytest.mark.parametrize("value,_expected", _TABLE)
def test_the_two_copies_agree_byte_for_byte(value, _expected):
    """The pin. A change to either file that the other does not follow is RED here."""
    assert money_brl(value) == _brl(value)

"""`R$ 1.250,00` — the pt-BR grammar, on BOTH sides of the vertical.

Two defects, one on each side, and they compose into one bad turn:

  READ   ``parse_amount("1.250")`` returned **1.25**. With both separators present the
         rightmost one decides and the reading is unambiguous; with only DOTS there is no
         rightmost-wins to apply and the code fell through to the en reading. An expense of
         R$ 1.250 was recorded as R$ 1,25 — understated by a factor of 1000, silently.
  WRITE  ``_brl`` emitted ``"R$ 1,250.00"`` — the en-US grammar — to a pt-BR contact.

What settles the READ side is not the locale but the arithmetic of money: an amount has two
decimal places, so a separator followed by exactly THREE digits cannot be a decimal point.
That holds in pt-BR and in en alike.

The WRITE side is settled by three things that agree: the contact's own grammar, the voice
prompt (which forbids the voicer from re-formatting a tool figure), and this repo's own
declaration of what Brazilian money looks like — ``cogno_praxis.grounding._PT.money``.

Synthetic figures throughout; no tenant, contact or real value appears in this file.
"""

import pytest

from cogno_praxis.bookkeeper.engine import parse_amount
from cogno_praxis.bookkeeper.server import _brl, _entry_line
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.grounding import _EN, _PT

ME = "identity-synthetic-1"


# ── READ: the thousands dot is a thousands dot ────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("1.250", 1250.00),              # <- returned 1.25 on the base commit
    ("R$ 1.250", 1250.00),
    ("12.500", 12500.00),            # <- returned 12.5
    ("123.456", 123456.00),
    ("1.234.567", 1234567.00),
])
def test_a_dot_group_of_three_digits_is_thousands_not_a_decimal(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # THE NEGATIVE TWIN of the rule above: a dot that is really a decimal point stays one.
    ("150.50", 150.50),              # two digits — a decimal, and money has two
    ("1.5", 1.50),                   # one digit
    ("45.00", 45.00),
    ("1.2345", 1.23),                # four digits — not a thousands group either
                                     # (rounded to cents by parse_amount, as always)
    # and every form that already worked keeps working, both grammars
    ("R$ 1.500,50", 1500.50),        # pt-BR, both separators
    ("1,500.50", 1500.50),           # en, both separators
    ("1.250,00", 1250.00),
    ("89,90", 89.90),
    ("150", 150.00),
])
def test_the_rule_does_not_reach_a_real_decimal_or_the_forms_that_worked(raw, expected):
    assert parse_amount(raw) == expected


def test_the_two_graphies_of_the_same_figure_agree():
    """`1.250` and `1.250,00` are the same money and must store the same number."""
    assert parse_amount("1.250") == parse_amount("1.250,00") == parse_amount("R$ 1.250,00")


# ── WRITE: what the contact reads ─────────────────────────────────────────────────────
@pytest.mark.parametrize("value,shown", [
    (1250.0, "R$ 1.250,00"),
    (45.0, "R$ 45,00"),
    (150.5, "R$ 150,50"),
    (12500.0, "R$ 12.500,00"),
    (1234567.89, "R$ 1.234.567,89"),
    (0.5, "R$ 0,50"),
    (0.0, "R$ 0,00"),
])
def test_the_reply_figure_is_written_in_pt_br(value, shown):
    assert _brl(value) == shown


def test_the_separators_swap_rather_than_chase_each_other():
    """A two-step ``.replace`` would map every ',' to '.' and then every '.' back to ','.

    ``1234567.89`` is the case that exposes it: it needs BOTH separators in one string.
    """
    assert _brl(1234567.89) == "R$ 1.234.567,89"
    assert _brl(1234567.89).count(".") == 2 and _brl(1234567.89).count(",") == 1


def test_the_output_matches_this_repos_own_declaration_of_brazilian_money():
    """``grounding._PT.money`` is the anti-fabrication money ANCHOR for the pt bundle.

    It reads ``1.234,56``; ``_EN.money`` reads ``1,234.56``. The vertical was writing the
    grammar its own pt bundle does not recognise, so a reply quoting a bare figure — one that
    dropped the ``R$`` the first alternative keys on — did not anchor at all.
    """
    figure = _brl(1250.0).replace("R$ ", "")
    assert _PT.money.search(figure), f"{figure!r} is not pt money to this repo's own lexicon"
    assert not _EN.money.search(figure)


def test_the_entry_line_and_the_summary_carry_it_too():
    svc = BookkeeperService()
    svc.add_outcome("material", "R$ 1.250,00", ME)
    row = svc.get_summary(ME, "")["outcomes"][0]
    assert "R$ 1.250,00" in _entry_line(row)


# ── the whole cycle: entrada -> lançamento -> resposta ────────────────────────────────
@pytest.mark.parametrize("typed", ["R$ 1.250,00", "1.250,00", "1.250", "R$ 1.250"])
def test_the_value_survives_the_whole_cycle_in_both_graphies(typed):
    """What the contact typed, what the ledger holds, and what the contact reads back."""
    svc = BookkeeperService()
    tx = svc.add_outcome("material", typed, ME)
    assert tx.amount == 1250.00                                   # lançamento
    summary = svc.get_summary(ME, "")
    assert summary["total_outcome"] == 1250.00
    assert _brl(summary["total_outcome"]) == "R$ 1.250,00"        # resposta


@pytest.mark.parametrize("value", [1250.0, 45.0, 150.5, 1234567.89, 12500.0])
def test_the_tools_own_output_reads_back_as_the_same_number(value):
    """The round trip is what makes the model's own re-reading safe.

    The executor quotes a tool's figure back into the next call all the time — measured live,
    a removal query was built out of one. If the printed form did not parse back to the same
    number, the vertical would be feeding itself a value it could not re-read.
    """
    assert parse_amount(_brl(value)) == value

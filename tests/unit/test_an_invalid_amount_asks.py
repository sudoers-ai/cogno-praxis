"""An invalid amount ASKS the user — it never invents one, and never gives up silently.

The defect, measured against ``parse_amount`` on the base commit: the cleaner kept every digit
in the string and dropped everything else, so an argument naming two numbers was CONCATENATED
into a third. ``"150 ou 200"`` recorded 150200.00; ``"12/05 R$ 300"`` recorded 1205300.00, a
date glued onto an amount.

Both halves of the correction are pinned here, and the second is the one that keeps the first
honest:

  * an argument the tool cannot read as ONE number is refused, and the refusal names the
    numbers it saw and tells the model to ASK;
  * a VALID argument still records on the FIRST call, with no question at all — a correction
    that made every write ask would have traded one defect for another.
"""

import pytest

from cogno_praxis.bookkeeper.engine import BookkeeperError, parse_amount
from cogno_praxis.bookkeeper.service import BookkeeperService

# Synthetic figures throughout — no tenant, contact or real value appears in this file.

# Each of these silently recorded a number the user never said. The comment is what the base
# commit produced, so a regression is legible without re-deriving it.
INVENTED = [
    ("150 ou 200", "150200.00"),          # the user offered two, the ledger got a third
    ("R$ 100 a R$ 200", "100200.00"),     # a range
    ("entre 300 e 400", "300400.00"),     # a range in words
    ("12/05 R$ 300", "1205300.00"),       # a DATE glued onto the amount
    ("2 x 75,00", "275.00"),              # a quantity glued onto a unit price
]


@pytest.mark.parametrize("raw,used_to_record", INVENTED)
def test_several_numbers_are_refused_instead_of_concatenated(raw, used_to_record):
    with pytest.raises(BookkeeperError) as exc:
        parse_amount(raw)
    msg = str(exc.value)
    # It refuses, and it says WHY in terms of what it saw...
    assert "no single amount to record" in msg
    # ...naming the candidates rather than making the model guess which it disliked.
    assert "names" in msg
    # ...and it never returns the concatenation that used to reach the books.
    assert used_to_record not in msg.replace(",", "")


@pytest.mark.parametrize("raw", ["150 ou 200", "abc", "R$ ", "", "-50", "0", "1.2.3"])
def test_every_refusal_tells_the_model_to_ask(raw):
    """The reason must say what to DO. An error naming only the accepted FORMS gets the same
    wrong input reworded — the ``resolve_date`` lesson, already written into ``math``'s error.
    """
    with pytest.raises(BookkeeperError) as exc:
        parse_amount(raw)
    msg = str(exc.value)
    assert "Nothing was recorded." in msg
    assert "ASK the user" in msg
    assert "never guess, average, round, or pick one of several numbers" in msg


def test_the_refusal_forbids_approximating_by_name():
    """Not merely 'invalid': the four ways a model reaches for a plausible number are named.

    A reply that approximates is the failure this refusal exists to prevent, and a rule that
    only says "invalid" leaves approximating as an unexamined option.
    """
    with pytest.raises(BookkeeperError) as exc:
        parse_amount("uns 150 ou 200")
    for forbidden in ("guess", "average", "round", "pick one"):
        assert forbidden in str(exc.value)


# ── the negative twin — a valid argument is NOT asked about ───────────────────────────
VALID = [
    (150, 150.0), (150.5, 150.5), ("150", 150.0),
    ("R$ 1.500,50", 1500.50),          # pt-BR, both separators
    ("1,500.50", 1500.50),             # en, both separators
    ("89,90", 89.90),                  # comma decimal
    ("R$100,50", 100.50),              # no space after the symbol
    ("1.500,50 (aprox)", 1500.50),     # one figure, words around it
]


@pytest.mark.parametrize("raw,expected", VALID)
def test_a_valid_amount_still_parses_unchanged(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", VALID)
def test_a_valid_amount_records_on_the_first_call_with_no_question(raw, expected):
    """The twin that makes the correction a correction: it must not ask about a good value.

    Through the SERVICE, not just the parser — a refusal that moved up a layer would still
    have cost the contact a round trip.
    """
    svc = BookkeeperService()
    tx = svc.add_outcome("material", raw, "identity-synthetic-1")
    assert tx.amount == expected


def test_a_refused_amount_writes_nothing_to_the_store():
    """The refusal is raised BEFORE the store is touched — nothing half-written stays behind."""
    svc = BookkeeperService()
    with pytest.raises(BookkeeperError):
        svc.add_outcome("material", "150 ou 200", "identity-synthetic-1")
    assert svc.get_summary("identity-synthetic-1", "")["outcome_count"] == 0

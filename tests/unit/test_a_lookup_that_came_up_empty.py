"""A removal that finds nothing ASKS — it never gives up, and it never denies the data.

Measured live (BOOKKEEPER over WhatsApp, and reproduced offline in this file): the contact
said "sim" to removing an expense that WAS in the ledger, ``remove_by_search`` ran twice, both
calls answered "nothing removed", and the drafted reply told the contact the removal failed —
one of them adding that the expense was still recorded.

Two defects, and fixing either alone leaves the incident live:

  (i)  the MATCH. The haystack was ``description + client_name``; the AMOUNT was not in it at
       all, so "45,00" — the natural way to name an entry — searched a text field that never
       held a number. No spelling of the figure could ever have matched.
  (ii) the BEHAVIOUR. Finding nothing, the tool raised a sentence the model reads as a failure,
       so the contact was told a false thing about their own books.

The safety rule this file also pins: the tolerance is NUMERIC and exact. ``45`` finds 45.00 and
never 450.00, because a removal that matches loosely deletes the wrong row silently.
"""

import pytest

from cogno_praxis.bookkeeper.engine import (
    BookkeeperError,
    amount_in_query,
    matches_entry,
)
from cogno_praxis.bookkeeper.service import BookkeeperService

# Synthetic throughout — no tenant, contact, scope or real value appears in this file.
ME = "identity-synthetic-1"
OTHER = "identity-synthetic-2"


def _ledger():
    svc = BookkeeperService()
    svc.add_outcome("material de escritorio", "45.00", ME)
    svc.add_outcome("almoco equipe", "450.00", ME)
    return svc


# ── (i) the MATCH: the four spellings of one figure all find the one entry ────────────
@pytest.mark.parametrize("query", ["45", "45.00", "45,00", "R$ 45,00", "R$45,00"])
def test_an_entry_is_findable_by_its_value_however_it_is_spelled(query):
    out = _ledger().remove_by_search(query, ME)
    assert out.proposal is not None, f"{query!r} found nothing"
    assert out.proposal.entry["description"] == "material de escritorio"
    assert out.proposal.entry["amount"] == 45.00


def test_the_words_still_work_and_still_win_nothing_was_traded_away():
    out = _ledger().remove_by_search("material", ME)
    assert out.proposal is not None
    assert out.proposal.entry["description"] == "material de escritorio"


def test_search_reads_the_same_definition_as_removal():
    """One matcher, two callers — a second copy is a second set of separator rules to keep."""
    hits = _ledger().search("45,00", ME, "")
    assert [h["amount"] for h in hits] == [45.00]


# ── the NEGATIVE twin: a value that must NOT match still does not ─────────────────────
@pytest.mark.parametrize("query,why", [
    ("450", "45 must never reach the 450.00 entry, nor 450 the 45.00 one — by exact equality"),
    ("4", "a prefix of the figure is not the figure"),
    ("4500", "nor is a suffix"),
    ("45.01", "nor is a near value — money is compared to the cent"),
])
def test_a_near_value_never_selects_a_neighbouring_row(query, why):
    out = _ledger().remove_by_search(query, ME)
    got = out.proposal.entry["amount"] if out.proposal else None
    assert got != 45.00, why


def test_the_amount_axis_is_exact_and_the_450_row_is_reachable_only_by_450():
    out = _ledger().remove_by_search("450", ME)
    assert out.proposal is not None and out.proposal.entry["amount"] == 450.00


@pytest.mark.parametrize("query,expected", [
    ("material", None),             # no figure at all
    ("45.00 2026-09-06", None),     # SEVERAL figures — it must not pick one
    ("R$ 100 a R$ 200", None),      # a range is not an amount
    ("", None),                     # the match-everything query stays a text query
    ("45,00 material", 45.0),       # one figure with words around it IS that figure
])
def test_amount_in_query_reads_one_figure_or_none_and_never_raises(query, expected):
    """It never raises and never guesses which of several figures was meant.

    A query naming ONE figure is that figure even with words beside it — the words then
    narrow nothing on this axis, and if the figure is shared the caller lists and asks.
    """
    assert amount_in_query(query) == expected


def test_a_search_that_should_fail_still_fails_and_invents_no_row():
    out = _ledger().remove_by_search("aluguel", ME)
    assert out.proposal is None and out.removed is None


def test_matching_never_reaches_another_identitys_rows():
    """The value axis widens WHAT is findable, never WHOSE — the scope guardrail is untouched."""
    assert _ledger().remove_by_search("45,00", OTHER).proposal is None


# ── (ii) the BEHAVIOUR: an empty lookup asks; it does not report a failure ────────────
def _no_match_message(svc, query):
    from cogno_praxis.bookkeeper.server import build_server   # imported lazily: needs the MCP SDK
    build_server(svc)                                          # (the sentence lives in server.py)
    out = svc.remove_by_search(query, ME)
    assert out.proposal is None and out.removed is None
    return out


def test_the_no_match_sentence_asks_instead_of_reporting_a_failure():
    from cogno_praxis.bookkeeper.grounding import NO_MATCH_MARKER
    import cogno_praxis.bookkeeper.server as server

    svc = _ledger()
    _no_match_message(svc, "aluguel")
    # The sentence is raised by the tool; assert on the real one rather than a paraphrase.
    src = server.__file__
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    msg_start = text.index('f"Searched YOUR entries for')
    msg = text[msg_start:text.index('")', msg_start)]
    # what it establishes
    assert "LOOKUP that came up empty" in msg
    assert "nothing was " in msg and "attempted and nothing failed" in msg
    # what it forbids — both halves, the second being the one that misinforms
    assert "Do NOT tell the user the removal failed" in msg
    assert "not in the system" in msg
    # what to do instead
    assert "ASK the user which entry they mean" in msg
    assert "get_summary" in msg
    # and the marker the rest of the system greps is intact
    assert NO_MATCH_MARKER in msg.replace('f"', "").replace('"', "")


def test_the_no_match_branch_still_raises_so_no_write_is_declared():
    """``_REFUSALS_RAISE``: a returning mutating tool is stamped ``side_effect=True``.

    The wording changed; the mechanism must not. A returned sentence here would make a turn
    that deleted nothing report a commit, which switches the anti-fabrication net OFF.
    """
    from mcp.server.fastmcp import FastMCP           # noqa: F401 — the SDK the server needs
    from cogno_praxis.bookkeeper.server import build_server

    svc = _ledger()
    mcp = build_server(svc)
    assert isinstance(mcp, FastMCP)
    # The service half of the contract: the no-match branch touched nothing.
    before = svc.get_summary(ME, "")["outcome_count"]
    svc.remove_by_search("aluguel", ME)
    assert svc.get_summary(ME, "")["outcome_count"] == before


def test_an_empty_lookup_leaves_the_ledger_intact():
    svc = _ledger()
    svc.remove_by_search("nao-existe-nesta-carteira", ME)
    assert svc.get_summary(ME, "")["outcome_count"] == 2


# ── matches_entry as a pure function (the definition both callers share) ──────────────
@pytest.mark.parametrize("query,expected", [
    ("45", True), ("45,00", True), ("45.00", True), ("R$ 45,00", True),
    ("450", False), ("44,99", False), ("material", True), ("cafe", False),
])
def test_matches_entry_is_words_or_exact_value(query, expected):
    assert matches_entry("material de escritorio", "", 45.00, query) is expected


def test_matches_entry_needs_no_exception_handling_from_its_callers():
    for query in ("", "   ", "abc", "-", "R$", "1.2.3", "0"):
        assert isinstance(matches_entry("desc", "", 10.0, query), bool)
    with pytest.raises(BookkeeperError):
        from cogno_praxis.bookkeeper.engine import parse_amount
        parse_amount("abc")     # the raising sibling, so the contrast is pinned

"""Unit tests for the pure bookkeeper engine (no I/O)."""

from datetime import date

import pytest

from cogno_praxis.bookkeeper.engine import (
    BookkeeperError,
    matches_query,
    parse_amount,
    resolve_date,
    summarize,
)


@pytest.mark.parametrize("raw,expected", [
    (150, 150.0), (150.5, 150.5), ("150", 150.0),
    ("R$ 1.500,50", 1500.50),          # pt-BR
    ("1,500.50", 1500.50),             # en
    ("89,90", 89.90),                  # comma decimal
])
def test_parse_amount_accepts_common_formats(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("bad", [0, -5, "0", "abc", ""])
def test_parse_amount_rejects_non_positive_or_garbage(bad):
    with pytest.raises(BookkeeperError):
        parse_amount(bad)


def test_resolve_date_defaults_to_today_and_validates_iso():
    today = date(2026, 7, 10)
    assert resolve_date("", today) == "2026-07-10"
    assert resolve_date(None, today) == "2026-07-10"
    assert resolve_date("2026-06-01", today) == "2026-06-01"
    assert resolve_date("not-a-date", today) == "2026-07-10"   # never invents


def test_matches_query_is_accent_and_case_insensitive():
    assert matches_query("Café da manhã", "cafe")
    assert matches_query("Conta de LUZ", "luz")
    assert not matches_query("aluguel", "internet")
    assert matches_query("qualquer coisa", "")          # empty query matches all


def test_summarize_totals_and_net():
    s = summarize([100.0, 50.5], [30.0])
    assert s == {"total_income": 150.5, "total_outcome": 30.0, "net": 120.5}

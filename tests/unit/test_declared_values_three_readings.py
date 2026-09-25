"""The shared grammar's three blind spots — each one a value the extractor read WRONG.

``cogno_praxis.declared_values`` is the one grammar behind the declared-values exemption (M3c),
the nets that call it, and the host's value provenance. Measured over the provenance
disagreements (F2.1), three shapes were not a missing source but a misreading:

* (i) ``R$ -45,00`` read as ``45,00`` — the sign lost, so a value of the OPPOSITE sign could pass
  as the same value;
* (ii) ``**R$**\\n**1.440**`` — the voice's broken bold — read as nothing (a number without
  cents is not a bare amount, and a single-blank gap was all the currency allowed);
* (iii) ``"window_days": 7`` read as nothing, so "7 dias" could never have a machine source.

Each has its twin and its CONTROL. "Sourced" here is the grammar's own question —
``values_declared(reply, declared_values(source))`` — the one every consumer asks. All values and
keys are invented.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cogno_praxis.declared_values import declared_values, value_keys, values_declared


def _sourced(reply: str, source: str) -> bool:
    return values_declared(reply, declared_values(source))


# ── (i) the sign ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["R$ -45,00", "R$-45,00", "-R$ 45,00", "R$ −45,00", "-45.00",
                                  '"ajuste": -45.00', "-45 reais"])
def test_a_minus_written_against_the_value_is_read(text):
    assert value_keys(text) == [("money", Decimal("-45.00"))], text


def test_TWIN_a_negative_value_is_sourced_by_the_same_negative():
    assert _sourced("O ajuste do mês foi de R$ -45,00.", '{"ajuste": -45.00, "id": 12}')


def test_CONTROL_a_negative_value_is_NOT_sourced_by_its_positive():
    """The source holds only 45.00 — an entry, not an exit: minus forty-five has no source."""
    assert not _sourced("O ajuste do mês foi de R$ -45,00.", '{"entrada": 45.00}')


def test_CONTROL_a_positive_value_is_NOT_sourced_by_its_negative():
    """The other direction of the same swap: the voice dropped the sign."""
    assert not _sourced("O ajuste do mês foi de R$ 45,00.", '{"ajuste": -45.00}')


@pytest.mark.parametrize("text, keys", [
    ("R$ 45,00 - R$ 10,00", [("money", Decimal("45.00")), ("money", Decimal("10.00"))]),
    ("de 10-20,00", [("money", Decimal("20.00"))]),                   # a range, not a negative
    ("em 2026-09-25", [("date", 25, 9, 2026)]),                        # a date
    ("ligue (11) 91234-5678", []),                                     # a phone
])
def test_a_dash_that_is_not_a_sign_changes_nothing(text, keys):
    assert value_keys(text) == keys


# ── (ii) the broken bold ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["Total: **R$**\n**1.440**", "**R$\n1.440**", "R$ \n1.440",
                                  "**R$ **\n1.440"])
def test_TWIN_a_value_on_the_line_after_its_currency_is_one_value(text):
    assert value_keys(text) == [("money", Decimal("1440.00"))], repr(text)
    assert declared_values(text) == ("R$ 1.440",)             # the literal, without the emphasis
    assert _sourced(text, "Mensalidade: R$ 1.440,00")


@pytest.mark.parametrize("text", ["R$", "Valor em **R$**\n", "Pagamento em R$\n\n1.440 alunos inscritos"])
def test_CONTROL_a_currency_with_no_number_after_it_reads_nothing(text):
    """No number, or a number in the NEXT paragraph: nothing is glued to the symbol."""
    assert value_keys(text) == [], repr(text)


# ── (iii) the unit under a machine key ────────────────────────────────────────────────

@pytest.mark.parametrize("source, unit", [
    ('{"window_days": 7, "id": 12}', "d"), ("window_days: 7", "d"), ('"days": 7', "d"),
    ("days=7", "d"), ("Window_Days: 7", "d"), ('{"retention_weeks": 7}', "w"),
])
def test_TWIN_a_machine_key_that_names_the_unit_sources_it(source, unit):
    assert value_keys(source) == [("unit", Decimal("7"), unit)], source
    word = {"d": "7 dias", "w": "7 semanas"}[unit]
    assert _sourced(f"O prazo é de {word}.", source)


@pytest.mark.parametrize("source", [
    '{"id": 7}', '{"count": 7}', "item_count: 7",
    '{"year": 2026, "month": 7, "day": 7}',              # calendar components, not durations
    "day_of_week: 7", "price_per_hour: 7",                 # a weekday, a rate
    "Dias: 7", "days: 7",                                  # prose, not a machine key
    "holidays_count: 7",                                   # "days" inside a word is no part
    '{"days_hours": 7}',                                   # two units: the key does not say which
])
def test_CONTROL_a_bare_number_under_a_key_that_names_no_unit_sources_no_unit(source):
    assert not _sourced("O prazo é de 7 dias.", source), source
    assert all(k[0] != "unit" for k in value_keys(source)), source


def test_a_key_that_names_no_unit_leaves_its_number_to_the_rest_of_the_grammar():
    """The unit is required IN the pattern: an ``"amount": 45.00`` is never consumed by the key
    reading, so its number is read as money exactly as before."""
    assert value_keys('{"amount": 45.00, "window_days": 7}') == [
        ("money", Decimal("45.00")), ("unit", Decimal("7"), "d")]


# ── every literal the extractor hands on reads back as the same value ─────────────────

@pytest.mark.parametrize("text", [
    "Ajuste: R$ -45,00; saldo -45.00; **R$**\n**1.440**; \"window_days\": 7; ttl_h=24; "
    "Aula: R$ 120,00 por hora, mínimo 4 h; vence 05/10; multa 2%",
])
def test_every_literal_reads_back_as_its_own_key(text):
    distinct = list(dict.fromkeys(value_keys(text)))      # first spelling wins, like the literals
    literals = declared_values(text)
    assert len(literals) == len(distinct) >= 8
    for lit, key in zip(literals, distinct):
        assert value_keys(lit) == [key], lit

"""A value the business DECLARED in the persona's configuration is a source — and nothing else is.

The defect, as a shape (the invented values below are not any tenant's): a business writes its
fixed values into a persona's rules — a rent, an hourly rate, a fee — and the persona answers a
question by quoting them. No tool ran, because none was needed: the rules ARE the source. The
bookkeeper net saw money plus *"tenho registrado"* on a turn that consulted no ledger, read the
description as a receipt, and rewrote a correct answer into *"deixa eu consultar"*.

The fix is by VALUE (``cogno_praxis.declared_values``): the host hands over the literal values of
the rules resolved for THIS contact's role, and a reply whose every value is among them has a
source. Everything the fix must NOT open is pinned beside it:

* a value NOT declared, and a value DERIVED from declared ones (a sum, a monthly total) — still
  caught;
* an EXPLICIT write claim quoting a declared price ("Registrei R$ 150,00") — still caught: a
  declaration grounds a FIGURE, never an ACT;
* a WRITE request answered with a receipt carrying the declared price — still caught: the most
  likely amount of a fabricated entry is the tenant's own price;
* no declared values at all — every rule reads exactly as before.

And M4, the same rule in the other two bundles: en/es used to read the bare participle ("the
recorded income", "los ingresos registrados") as an explicit claim, so a truthful listing was
rewritten even WITH a ledger read in hand. pt has had that split since the attributive fix.
"""

from __future__ import annotations

import pytest

from cogno_praxis.bookkeeper.grounding import ground_reply
from cogno_praxis.declared_values import (MAX_DECLARED_VALUES, declared_values, value_keys,
                                          values_declared)
from cogno_praxis.grounding import ToolCall
from cogno_praxis.scheduler.grounding import ground_reply as sched_ground

# Invented configuration: nothing here belongs to a real business.
RULES_PT = ("Aluguel da sala: R$ 10,00 por dia. Aula avulsa: R$ 120,00 por hora, mínimo 4 h. "
            "Mensalidade: R$ 1.440,00. Multa por atraso: 2%. Vencimento todo 05/10.")
DECLARED = declared_values(RULES_PT)

LEITURA = [ToolCall(tool="get_summary", ok=True,
                    result="Income: R$ 1.440,00\nExpenses: R$ 10,00\nNet: R$ 1.430,00")]


def _rule(reply, *, declared=DECLARED, read=True, tools=(), locale="pt"):
    v = ground_reply(reply, tools=list(tools), is_read_query=read, locale=locale,
                     declared_values=declared)
    return v.rule if v else None


# ── the extraction: values only, as written ─────────────────────────────────────────────────
def test_the_declared_set_is_the_literal_values_of_the_rules():
    assert DECLARED == ("R$ 10,00", "R$ 120,00", "4 h", "R$ 1.440,00", "2%", "05/10")


def test_names_and_sentences_are_never_values():
    assert declared_values("Fale com a Ana Beltrão. Atendemos todos os clientes. Sala 3.") == ()


def test_two_grammars_are_one_value_and_a_thousands_point_is_never_a_decimal():
    assert values_declared("R$ 120", ["R$ 120,00"])
    assert values_declared("$1,440.00", ["R$ 1.440,00"])
    assert values_declared("R$ 1.440", ["1.440,00"])
    assert not values_declared("R$ 1,44", ["R$ 1.440,00"])


def test_a_date_without_a_year_is_the_same_day_but_two_years_are_two_dates():
    assert values_declared("vence em 05/10/2026", ["05/10"])
    assert values_declared("vence em 05/10", ["05/10/2026"])
    assert not values_declared("vence em 05/10/2027", ["05/10/2026"])


def test_a_reply_with_no_value_and_an_empty_declaration_ground_nothing():
    assert not values_declared("Tudo certo por aqui.", DECLARED)
    assert not values_declared("R$ 10,00", [])
    assert not values_declared("R$ 10,00", ["sem valores"])


def test_the_cap_is_the_strict_direction():
    rules = " ".join(f"R$ {n},00" for n in range(1, MAX_DECLARED_VALUES + 20))
    got = declared_values(rules)
    assert len(got) == MAX_DECLARED_VALUES
    assert not values_declared(f"R$ {MAX_DECLARED_VALUES + 5},00", got)


def test_value_keys_is_the_one_grammar_both_sides_use():
    assert value_keys("R$ 120,00 e 4 horas") == value_keys("R$ 120 e 4 h")


# ── the main twin: a declared value quoted exactly ─────────────────────────────────────────
@pytest.mark.parametrize("reply,declared,locale", [
    ("Tenho registrado o seguinte: R$ 10,00 de aluguel da sala.", DECLARED, "pt"),
    ("A mensalidade registrada é R$ 1.440,00.", DECLARED, "pt"),
    ("Os valores que tenho registrados: aula R$ 120,00 por hora, mínimo 4 h.", DECLARED, "pt"),
    ("I have $10.00 recorded for the room rent.", ("$10.00",), "en"),
    ("Tengo registrado: €10,00 de alquiler de la sala.", ("€10,00",), "es"),
])
def test_a_declared_value_quoted_exactly_is_not_a_fabricated_entry(reply, declared, locale):
    assert _rule(reply, declared=declared, locale=locale) is None
    # …and the SAME reply with nothing declared is what `main` does to it — the pair that
    # proves the exemption is the declaration and not a change in how the sentence is read.
    assert _rule(reply, declared=(), locale=locale) == "fabricated_entry"


def test_a_declared_total_is_not_conjured():
    reply = "O total da mensalidade é R$ 1.440,00."
    assert _rule(reply) is None
    assert _rule(reply, declared=()) == "conjured_totals"


# ── the controls: what the declaration must NOT reach ──────────────────────────────────────
def test_a_value_the_rules_do_not_carry_is_still_caught():
    assert _rule("Tenho registrado o seguinte: R$ 12,00 de aluguel.") == "fabricated_entry"
    assert _rule("O total do mês é R$ 1.500,00.") == "conjured_totals"


def test_ONE_undeclared_value_beside_declared_ones_is_still_caught():
    assert _rule("Tenho registrado: aluguel R$ 10,00 e luz R$ 85,00.") == "fabricated_entry"


@pytest.mark.parametrize("reply,rule", [
    # 4 h x R$ 120,00 — written nowhere in the rules
    ("Tenho registrado para a aula: R$ 480,00.", "fabricated_entry"),
    ("O total da aula de 4 h é R$ 480,00.", "conjured_totals"),
    # R$ 1.440,00 corrected by some index — written nowhere
    ("O total corrigido da mensalidade é R$ 1.512,00.", "conjured_totals"),
])
def test_a_value_DERIVED_from_declared_values_is_not_declared(reply, rule):
    assert _rule(reply) == rule


def test_an_EXPLICIT_write_claim_is_never_exempted_by_a_declared_price():
    """M4's own twin. «Registrei» is a write, and a declared R$ 10,00 does not make it one."""
    for reply in ("Registrei a despesa de R$ 10,00 do aluguel.",
                  "Acabei de lançar R$ 120,00 de aula.",
                  "Certo, já está lançado o valor de R$ 10,00."):
        assert _rule(reply) == "fabricated_entry", reply
        assert _rule(reply, tools=LEITURA) == "fabricated_entry", reply


def test_a_WRITE_request_answered_with_a_receipt_of_the_declared_price_is_still_caught():
    """The hole the `is_read_query` half closes: "registra o aluguel" → "Registrado! R$ 10,00"
    with nothing written. The declared price is exactly the amount a fabricated receipt quotes."""
    assert _rule("Registrado! R$ 10,00 do aluguel.", read=False) == "fabricated_entry"
    assert _rule("Registrado! R$ 10,00 do aluguel.", read=True) is None


def test_a_real_write_still_passes_and_a_persona_without_values_is_unchanged():
    wrote = [ToolCall(tool="add_outcome", ok=True, side_effect=True,
                      result="Expense recorded: Aluguel = R$ 10,00 on 2026-10-05.")]
    assert _rule("Registrei a despesa de R$ 10,00.", tools=wrote) is None
    for reply in ("Tenho registrado o seguinte: R$ 10,00 de aluguel.",
                  "O total é R$ 1.440,00.", "Registrei a despesa de R$ 50,00."):
        a = ground_reply(reply, tools=[], is_read_query=True, locale="pt")
        b = ground_reply(reply, tools=[], is_read_query=True, locale="pt", declared_values=())
        assert (a.rule if a else None) == (b.rule if b else None) is not None


def test_the_scheduler_accepts_the_keyword_and_reads_nothing_from_it():
    reply = "Sua consulta está agendada para 05/10 às 11:00."
    a = sched_ground(reply, tools=[], locale="pt")
    b = sched_ground(reply, tools=[], locale="pt", declared_values=("05/10",))
    assert (a.rule if a else None) == (b.rule if b else None)


# ── M4 in en / es: the attributive participle is a description when the ledger was read ──────
@pytest.mark.parametrize("reply,locale", [
    ("The recorded income for the month is $1,440.00.", "en"),
    ("Logged entries today: Expenses $10.00.", "en"),
    ("Los ingresos registrados del mes son €1.440,00.", "es"),
    ("Tengo registrados estos gastos: €10,00.", "es"),
])
def test_en_es_a_listing_with_the_ledger_read_is_not_a_claim(reply, locale):
    assert _rule(reply, declared=(), tools=LEITURA, locale=locale) is None
    # the pair: with NOTHING read the same grammar is still a receipt nobody wrote
    assert _rule(reply, declared=(), locale=locale) == "fabricated_entry"


@pytest.mark.parametrize("reply,locale", [
    ("Done! I've recorded the $150.00 consultation.", "en"),
    ("Your $150.00 consultation is recorded.", "en"),
    ("The amount of $150.00 was already recorded.", "en"),
    ("¡Listo! Registré la consulta de €150,00.", "es"),
    ("Ya está registrado el monto de €150,00.", "es"),
    ("Ya fue registrado el monto de €150,00.", "es"),
])
def test_en_es_the_EXPLICIT_claim_fires_even_with_a_read_in_hand(reply, locale):
    assert _rule(reply, declared=(), tools=LEITURA, locale=locale) == "fabricated_entry"

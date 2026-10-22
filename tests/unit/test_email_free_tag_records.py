"""A persona's e-mail values are the TENANT's tags, never code — and a free tag may hold RECORDS.

R-T13, 2026-10-22. The owner: «preciso de algo genérico. Quando entrar uma persona nova, faço via
tags personalizadas, senão teria que fazer via código» — and asked that the coordination follow
that rule. What is pinned here, one line each:

* :data:`FIELD_PROVIDERS` is EMPTY and every persona's template is validated and filled alike —
  the eight generic markers and the tenant's tags; the coordination's five names are ordinary
  company-tag names, refused as unknown markers until the tenant declares them;
* a FREE tag's value is text OR a list of records (``[{key: value}, …]``): the records door
  (:func:`free_records_problems`/:func:`free_records`) — simple keys, one-line text cells, a
  number as written — and its refusals, each asked, never sent; an empty list is a value nobody
  said; a list never goes in a subject;
* the text of a list: a record of ONE key is its value, of TWO filled keys «first: second», of
  more «chave: valor · …», the dated form as before; in HTML a list of one-key records is a list;
* the e-mail goes out as HTML only when its body carries a free tag whose value is a list;
* where a cell came from (:func:`record_cells_unverified`): literal by the host's predicate, or
  a derivation checked here — ``dia`` the weekday of ``data``, ``mês`` its month, the year from
  the cell or the send's month; a wrong derivation and a record with no ``data`` are held to the
  literal rule.

Everything here is synthetic: invented names, an invented school.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.email_fields import (
    EMAIL_FIELDS,
    FIELD_PROVIDERS,
    GENERIC_FIELDS,
    EmailContext,
    custom_tag_problems,
    fill_email_fields,
    is_custom_tag_name,
    known_markers,
    records_html,
    records_text,
    render_email_forms,
    template_fields,
    validate_template,
)

FIVE = ("aulas", "disciplinas", "valor_por_aula", "valores_por_bonus", "total")
PERSONAS = ("COORDINATOR", "SECRETARY", "BOOKKEEPER", "CLOSER", "INTERVIEWER", "NOVA", "", None)
SCHOOL = "Colégio Horizonte"      # invented
#: The owner's «Cronograma de aulas» SHAPE, the five names as the tenant's tags. Text invented.
SUBJECT = "Cronograma de aulas — [mes]"
BODY = ("Olá, [nome],\n\nSegue o seu cronograma de [mes]:\n\n[aulas]\n\nDisciplinas:\n"
        "[disciplinas]\n\nValor por aula: [valor_por_aula]\n\n[valores_por_bonus]\n\n"
        "Total: [total]\n\nAtenciosamente,\n[assinatura]")
FREE = {n: "" for n in FIVE}
AULAS = [{"mês": "setembro", "dia": "sáb", "data": "05/09", "horário": "08:00",
          "disciplina": "Redes", "turma": "Turma XA_01"},
         {"mês": "setembro", "dia": "sáb", "data": "12/09", "horário": "",
          "disciplina": "Zoologia", "turma": "Turma XA_01"}]


def _ctx(values: dict, tags: "dict | None" = None) -> EmailContext:
    return EmailContext(recipient_name="Prof Quintino", recipient_email="q@captura.local",
                        tenant_name=SCHOOL, month="2026-09", today=date(2026, 9, 20),
                        persona_name="Coordenação", requester_name="Prof Ubaldo",
                        custom_tags=FREE if tags is None else tags, free_tag_values=values)


# ── no persona has markers in code ─────────────────────────────────────────────────────────

def test_the_registry_of_persona_markers_is_empty_and_the_list_is_the_eight():
    assert dict(FIELD_PROVIDERS) == {}
    assert dict(EMAIL_FIELDS) == dict(GENERIC_FIELDS) and len(EMAIL_FIELDS) == 8


def test_every_persona_offers_and_validates_the_same_markers():
    verdicts = {p: (known_markers(p), validate_template(SUBJECT, BODY, persona=p,
                                                        custom_tags=FREE)) for p in PERSONAS}
    assert len(set(verdicts.values())) == 1
    assert verdicts["SECRETARY"][1] == ()                 # the five, declared, save everywhere


def test_without_the_tenants_tags_the_five_are_unknown_markers_for_every_persona():
    refusals = {p: validate_template(SUBJECT, BODY, persona=p) for p in PERSONAS}
    assert len(set(refusals.values())) == 1
    sentences = refusals["COORDINATOR"]
    for name in FIVE:
        assert any(f"[{name}] não é um marcador" in r for r in sentences), name
    assert not any("coordenação" in r for r in sentences)


def test_the_five_names_are_company_tag_names_now():
    for name in FIVE:
        assert is_custom_tag_name(name) and custom_tag_problems(name, "") == (), name


# ── a free tag's value may be a list of records ──────────────────────────────────────────────

def test_a_list_of_records_fills_with_its_text():
    values, missing = fill_email_fields(["aulas"], _ctx({"aulas": AULAS}))
    assert missing == () and values["aulas"] == (
        "Turma XA_01\n05/09 (sáb) 08:00 — Redes\n12/09 (sáb) — Zoologia")


def test_numbers_are_written_as_given_and_none_is_empty():
    values, missing = fill_email_fields(
        ["total"], _ctx({"total": [{"faixa": "Base", "valor": 2880}, {"faixa": "x", "valor": None}]}))
    assert missing == () and values["total"] == "Base: 2880\nfaixa: x"


@pytest.mark.parametrize("bad, words", [
    ([{"faixa": True}], "não é texto"),
    ([{"faixa": ["a"]}], "não é texto"),
    ([{"faixa": {"a": 1}}], "não é texto"),
    ([{"  ": "x"}], "chave que não serve"),
    ([{"k" * 41: "x"}], "chave que não serve"),
    ([{f"k{i}": "x" for i in range(13)}], "o máximo é 12"),
    ([{"a": "x\x07"}], "caractere de controle"),
    ([{"a": "x" * 501}], "o máximo é 500"),
    (["texto"], "tem de ser um objeto"),
    ([{}], "tem de ser um objeto"),
    ([{"a": "x"}] * 501, "o máximo é 500"),
])
def test_a_list_the_rule_refuses_is_asked_never_sent(bad, words):
    values, missing = fill_email_fields(["aulas"], _ctx({"aulas": bad}))
    assert "aulas" not in values and len(missing) == 1
    assert missing[0].field == "aulas" and words in missing[0].reason, missing[0].reason


def test_an_empty_list_is_a_value_nobody_said():
    _values, missing = fill_email_fields(["aulas"], _ctx({"aulas": []}))
    assert [m.reason for m in missing] == [ef.CUSTOM_TAG_FREE_MISSING]


def test_a_multi_line_cell_becomes_one_line():
    values, _ = fill_email_fields(["aulas"], _ctx({"aulas": [{"a": " linha 1\n linha 2 "}]}))
    assert values.get("aulas") == "linha 1 linha 2"


def test_a_list_never_goes_in_a_subject():
    import inspect
    assert "in_subject" in inspect.signature(fill_email_fields).parameters
    _v, missing = fill_email_fields(["aulas"], _ctx({"aulas": AULAS}), in_subject=["aulas"])
    assert [m.field for m in missing] == ["aulas"] and "assunto" in missing[0].reason
    # Control: the same value for a tag of the body fills.
    assert fill_email_fields(["aulas"], _ctx({"aulas": AULAS}), in_subject=["mes"])[1] == ()


def test_a_list_for_a_fixed_tag_changes_nothing():
    values, missing = fill_email_fields(["aulas"], _ctx({"aulas": AULAS}, tags={"aulas": "fixo"}))
    assert missing == () and values["aulas"] == "fixo"


# ── the text and the HTML of a list ─────────────────────────────────────────────────────────

def test_one_key_is_its_value_two_filled_keys_are_label_and_value_more_are_key_value():
    assert records_text([{"disciplina": "Redes"}, {"disciplina": "Zoologia"}]) == "Redes\nZoologia"
    assert records_text([{"faixa": "Sem bônus", "valor": "R$ 1,00"}]) == "Sem bônus: R$ 1,00"
    assert records_text([{"faixa": "Sem bônus", "valor": ""}]) == "faixa: Sem bônus"
    assert records_text([{"a": "1", "b": "2", "c": "3"}]) == "a: 1 · b: 2 · c: 3"
    # the group key is not a shown key: one key besides it is its value, under the title
    assert records_text([{"disciplina": "Redes", "turma": "A1"}]) == "Turma A1\nRedes"


def test_a_list_of_one_key_records_is_an_html_list_and_two_keys_a_table():
    assert records_html([{"disciplina": "Redes"}, {"disciplina": "<b>"}]) == (
        '<ul style="margin:0 0 12px;padding-left:24px"><li>Redes</li><li>&lt;b&gt;</li></ul>')
    assert "<table" in records_html([{"faixa": "a", "valor": "b"}])
    grouped = records_html([{"disciplina": "Redes", "turma": "A1"}])
    assert grouped.startswith('<p style=') and "Turma A1" in grouped and "<ul" in grouped


def test_the_email_is_html_only_when_its_body_carries_a_list():
    def doc(values: dict, tags: "dict | None" = None, body: str = BODY) -> str:
        ctx = _ctx(values, tags)
        vals, missing = fill_email_fields(template_fields(SUBJECT, body), ctx)
        assert missing == (), missing
        return render_email_forms(SUBJECT, body, vals, ctx)[2]
    text_only = {"aulas": "texto", "disciplinas": "Redes", "valor_por_aula": "R$ 480,00",
                 "valores_por_bonus": "x", "total": "R$ 1,00"}
    assert doc(text_only) == ""
    assert doc({n: "v" for n in FIVE}, tags={n: "fixo" for n in FIVE}) == ""
    with_list = dict(text_only, aulas=AULAS)
    # A list handed to a FIXED tag is never read (the fixed value fills): no table, no HTML.
    assert doc(with_list, tags={**FREE, "aulas": "fixo"}) == ""
    html = doc(with_list)
    assert html.startswith("<!DOCTYPE html>") and html.count("<table") == 1
    # A figure is never bold by its NAME (the provider's [total] was).
    assert "<strong>R$ 1,00</strong>" not in html


# ── where a cell came from ───────────────────────────────────────────────────────────────────

READ = "*Setembro de 2026*\n- 05/09 08:00 · Turma XA_01 · Redes\n- 12/09 · Turma XA_01 · Zoologia"


def _unverified(records, month="2026-09"):
    check = getattr(ef, "record_cells_unverified", None)
    assert check is not None, "the record grammar's check is part of the contract"
    return check(records, month=month, is_literal=lambda c: c.casefold() in READ.casefold())


def test_literal_cells_and_right_derivations_pass():
    assert _unverified(AULAS) == ()
    for dia in ("sáb", "SAB", "sábado", "sabado-feira"[:6], "sábado-feira"):
        assert _unverified([{"dia": dia, "data": "05/09"}]) == (), dia
    for mes in ("setembro", "Setembro", "set"):
        assert _unverified([{"mês": mes, "data": "05/09"}]) == (), mes


def test_a_wrong_derivation_is_refused_like_a_cell_nobody_read():
    assert _unverified([{"dia": "dom", "data": "05/09", "disciplina": "Redes"}]) == ((0, "dia"),)
    assert _unverified([{"mês": "outubro", "data": "05/09"}]) == ((0, "mês"),)
    assert _unverified([{"data": "05/09", "disciplina": "Inventada"}]) == ((0, "disciplina"),)


def test_a_record_with_no_date_holds_the_weekday_to_the_literal_rule():
    assert _unverified([{"dia": "sáb", "disciplina": "Redes"}]) == ((0, "dia"),)
    assert _unverified([{"dia": "sáb", "data": "dia cinco"}]) == ((0, "dia"), (0, "data"))


def test_the_year_comes_from_the_cell_or_else_from_the_month():
    # 05/09/2027 is a Sunday: the cell's year wins over the send's month.
    assert _unverified([{"dia": "dom", "data": "05/09/2027"}], month="2026-09") == ((0, "data"),)
    assert _unverified([{"dia": "sáb", "data": "05/09"}], month="") == ((0, "dia"),)


# ── the year of the date: derived from the send's month, checked (the Director, 2026-10-22) ─────

def test_the_html_date_column_carries_the_year_of_the_send_month_and_the_text_does_not():
    ctx = _ctx({"aulas": AULAS})                          # month 2026-09
    values, missing = fill_email_fields(["aulas"], ctx)
    assert missing == () and "05/09/26" not in values["aulas"]      # the text: dd/mm, as before
    html = render_email_forms("A", "[aulas]", values, ctx)[2]
    assert ">05/09/26<" in html and ">12/09/26<" in html and ">05/09<" not in html
    # no month → as written; a date of another month → as written
    no_month = dataclasses.replace(ctx, month="")
    assert ">05/09<" in render_email_forms("A", "[aulas]", values, no_month)[2]
    other = [{**AULAS[0], "data": "03/10"}]
    assert records_html(other, month="2026-09").count(">03/10<") == 1
    assert ">05/09/26<" in records_html(AULAS, month="2026-09")


def test_a_date_with_the_year_is_verified_against_the_send_month():
    check = getattr(ef, "record_cells_unverified", None)
    assert check is not None, "the record grammar's check is part of the contract"
    literal = lambda c: c in READ   # noqa: E731
    # the right derivation: «05/09» read, the year of 2026-09
    assert check([{"data": "05/09/26"}], month="2026-09", is_literal=literal) == ()
    assert check([{"data": "05/09/2026"}], month="2026-09", is_literal=literal) == ()
    # a wrong year — refused like a cell nobody read
    assert check([{"data": "05/09/25"}], month="2026-09", is_literal=literal) == ((0, "data"),)
    # no month: the year is derivable from nothing — refused; the literal dd/mm still passes
    assert check([{"data": "05/09/26"}], month="", is_literal=literal) == ((0, "data"),)
    assert check([{"data": "05/09"}], month="", is_literal=literal) == ()
    # a dd/mm nobody read, with the right year — refused
    assert check([{"data": "06/09/26"}], month="2026-09", is_literal=literal) == ((0, "data"),)


def test_a_predicate_that_raises_verifies_nothing_and_a_non_list_is_unverified():
    def boom(_c: str) -> bool:
        raise RuntimeError("no")
    check = getattr(ef, "record_cells_unverified", None)
    assert check is not None, "the record grammar's check is part of the contract"
    assert check([{"data": "05/09"}], month="2026-09", is_literal=boom) == ((0, "data"),)
    assert check("texto", month="2026-09", is_literal=lambda c: True) == ((0, ""),)


# ── the preview's HTML: force_html (the reviewer's decision, 2026-10-22) ─────────────────────────

def test_force_html_draws_the_document_without_records_and_the_default_does_not():
    """A preview shows the tenant's appearance and rich text even when the template carries no
    list (its free tags are placeholders until the send); a SEND never forces it — an e-mail
    with no records goes out as text, as always."""
    import inspect
    assert "force_html" in inspect.signature(render_email_forms).parameters
    ctx = _ctx({"total": "R$ 1,00"})
    body = "Olá, [nome].\n\nSobre as aulas:\n• Chegue cedo.\n\nTotal: [total]"
    values, missing = fill_email_fields(template_fields("Aviso", body), ctx)
    assert missing == ()
    plain = render_email_forms("Aviso", body, values, ctx)
    assert plain[2] == ""                                         # the default: text only
    forced = render_email_forms("Aviso", body, values, ctx, force_html=True)
    assert forced[2].startswith("<!DOCTYPE html>")
    assert "<strong>Sobre as aulas:</strong>" in forced[2] and "<li>Chegue cedo.</li>" in forced[2]
    assert "<table" not in forced[2]                              # no row is invented
    assert forced[0] == plain[0] and forced[1] == plain[1]        # no signature configured

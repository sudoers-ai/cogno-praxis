"""The TENANT's own markers — company tags with a FIXED value (``cogno_praxis.email_fields``).

The owner (2026-10-21) asked for a field to create tags of one's own beside the thirteen standard
markers; the Director's design keeps only tags with a FIXED value, the tenant's, valid in EVERY
persona («tags padrão para tudo»). A tag is ``{name: value}``: the name is
``[a-z][a-z0-9_]{1,30}`` and never one of the thirteen nor a reserved name; the value is plain
text, one line or several, at most 500 characters. What is pinned, one line each:

* the twin — a template with ``[horario_atendimento]`` SAVES when the tenant has that tag, and
  is filled with its value (on the base it was refused as «não é um marcador»);
* the control — without the tag the refusal is byte for byte the base's, and a template that
  uses no company tag validates, fills and renders the same with or without the tenant's tags;
* a collision with any of the thirteen and with the reserved names is refused, and a tag can
  never unlock a reserved marker nor override a standard one;
* a tag removed after the template was saved: the save door refuses the template, the turn door
  (``any_company_tag=True``) keeps it, and the fill says ``missing`` — «tag personalizada
  removida» — so the send asks the requester instead of sending;
* PER PERSONA: the company tag fills in EVERY row of the per-persona matrix
  (``test_email_fill_by_persona.py``'s, derived from :data:`FIELD_PROVIDERS`), and leaves the
  rest of each row exactly as it was. A provider persona without a row fails here too;
* the name grammar and the value limits, with the adversarial spellings that must NOT pass;
* a multi-line value never reaches a subject, and a value is never read as a template.

Everything here is invented.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.email_fields import (
    EMAIL_FIELDS,
    FIELD_PROVIDERS,
    REFUSED_FIELDS,
    EmailContext,
    fill_email_fields,
    known_markers,
    missing_question,
    render_email,
    template_fields,
    validate_template,
)
from tests.unit.test_email_fill_by_persona import EXPECTED_FILLS, T_ALL, _full_context

TAG = "horario_atendimento"
VALUE = "de segunda a sexta, das 8h às 18h"
TAGS = {TAG: VALUE}

#: A front-desk notice that quotes the tenant's opening hours — the owner's example, invented.
T_HOURS = ("Horário de atendimento — [empresa]",
           "Olá, [nome],\n\nAtendemos [horario_atendimento].\n\n[assinatura]")


def _host_half(**kw) -> EmailContext:
    base = dict(recipient_name="Prof Alfa", recipient_email="alfa@captura.local",
                tenant_name="Escola Exemplo", month="2026-10", today=date(2026, 10, 7),
                persona_name="Assistente Vexa", requester_name="Coord Gama")
    base.update(kw)
    return EmailContext(**base)


def _with_tags(ctx: EmailContext, tags) -> EmailContext:
    return dataclasses.replace(ctx, custom_tags=tags)


# ── the twin and its control ─────────────────────────────────────────────────────────────────

def test_a_template_with_the_tenants_tag_saves_and_fills_with_its_value():
    assert validate_template(*T_HOURS, custom_tags=TAGS) == ()
    values, missing = fill_email_fields(template_fields(*T_HOURS),
                                        _with_tags(_host_half(), TAGS))
    assert missing == ()
    assert values[TAG] == VALUE
    subject, body = render_email(*T_HOURS, values)
    assert subject == "Horário de atendimento — Escola Exemplo"
    assert body == ("Olá, Prof Alfa,\n\nAtendemos de segunda a sexta, das 8h às 18h.\n\n"
                    "Assistente Vexa")


def test_control_without_the_tag_the_refusal_is_the_bases():
    """The sentence a tenant with no such tag reads is the one of before, byte for byte."""
    (reason,) = validate_template(*T_HOURS)
    assert reason == ("no corpo, [horario_atendimento] não é um marcador; os marcadores são "
                      + ", ".join(known_markers()))


def test_the_tenants_other_tags_do_not_open_it():
    (reason,) = validate_template(*T_HOURS, custom_tags={"outra_tag": "x"})
    assert reason.startswith("no corpo, [horario_atendimento] não é um marcador;")


def test_control_a_template_without_company_tags_is_unchanged_by_the_tenants_tags():
    fields = template_fields(*T_ALL)
    assert validate_template(*T_ALL, custom_tags=TAGS) == validate_template(*T_ALL) == ()
    plain = fill_email_fields(fields, _full_context(), persona="COORDINATOR")
    tagged = fill_email_fields(fields, _with_tags(_full_context(), TAGS), persona="COORDINATOR")
    assert plain == tagged
    assert render_email(*T_ALL, plain[0]) == render_email(*T_ALL, tagged[0])


def test_the_refusal_lists_the_tenants_tags_beside_the_thirteen():
    (reason,) = validate_template("Aviso", "Olá [nmoe]", custom_tags=TAGS)
    assert reason == ("no corpo, [nmoe] não é um marcador; os marcadores são "
                      + ", ".join(known_markers()) + "; e os da empresa: [horario_atendimento]")


# ── collisions ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(EMAIL_FIELDS))
def test_a_tag_named_like_a_standard_marker_is_refused(name):
    stored, refusals = ef.normalise_custom_tags({name: "valor"})
    assert stored == {}
    assert refusals == (f"[{name}] já é um marcador padrão ({EMAIL_FIELDS[name].source}); "
                        "escolha outro nome",)


@pytest.mark.parametrize("name", sorted(REFUSED_FIELDS))
def test_a_tag_named_like_a_reserved_marker_is_refused(name):
    stored, refusals = ef.normalise_custom_tags({name: "valor"})
    assert stored == {}
    assert refusals == (f"[{name}] é um nome reservado: {REFUSED_FIELDS[name]}",)


def test_a_tag_can_never_unlock_a_reserved_marker_nor_override_a_standard_one():
    # handed over around the save door, a colliding "tag" is not a tag
    assert validate_template("NF", "CPF: [cpf_cnpj]", custom_tags={"cpf_cnpj": "x"}) == \
        validate_template("NF", "CPF: [cpf_cnpj]")
    values, _ = fill_email_fields(("nome",), _with_tags(_host_half(), {"nome": "OUTRO"}))
    assert values["nome"] == "Prof Alfa"


# ── a tag removed after the template was saved ──────────────────────────────────────────────

def test_a_removed_tag_the_save_refuses_the_turn_keeps_and_the_fill_asks():
    # the save door, with the tenant's tags of NOW (none): refused, as any unknown marker
    assert validate_template(*T_HOURS, custom_tags={}) != ()
    # the turn door: a template whose tag was removed still EXISTS
    assert validate_template(*T_HOURS, custom_tags={}, any_company_tag=True) == ()
    values, missing = fill_email_fields(template_fields(*T_HOURS), _with_tags(_host_half(), {}))
    assert [m.field for m in missing] == [TAG]
    assert missing[0].reason == "tag personalizada removida"
    assert missing[0].source == ef.CUSTOM_TAG_SOURCE
    assert TAG not in values
    assert ("- [horario_atendimento] — tag personalizada removida (fonte: as tags "
            "personalizadas da empresa)") in missing_question(missing)
    with pytest.raises(ValueError):          # the floor under it: never rendered blank
        render_email(*T_HOURS, values)


def test_the_turn_door_still_refuses_what_is_not_a_tag_name():
    """``any_company_tag`` opens only the tag GRAMMAR: a reserved marker, a ``[`` that opens no
    marker and the subject rules are refused all the same."""
    for subject, body in (("NF", "[cpf_cnpj]"), ("Aviso", "Olá [Nome]"), ("Aviso", "[x]"),
                          ("Aviso", "[1abc]"), ("Total [aulas]", "corpo")):
        assert validate_template(subject, body, any_company_tag=True) == \
            validate_template(subject, body), (subject, body)


# ── per persona ──────────────────────────────────────────────────────────────────────────────

def test_every_provider_persona_has_a_row():
    """The rows are the per-persona matrix's (derived from FIELD_PROVIDERS + a persona with no
    provider): a provider persona that arrives without a row fails here, by name."""
    assert set(FIELD_PROVIDERS) <= set(EXPECTED_FILLS), set(FIELD_PROVIDERS) - set(EXPECTED_FILLS)
    assert any(p not in FIELD_PROVIDERS for p in EXPECTED_FILLS)


@pytest.mark.parametrize("persona", sorted(EXPECTED_FILLS))
def test_the_company_tag_fills_in_every_persona_and_leaves_the_row_as_it_was(persona):
    subject, body = T_ALL[0], T_ALL[1] + "\n\nAtendimento: [horario_atendimento]"
    fields = template_fields(subject, body)
    assert validate_template(subject, body, persona=persona, custom_tags=TAGS) == ()
    values, missing = fill_email_fields(fields, _with_tags(_full_context(), TAGS),
                                        persona=persona)
    assert values[TAG] == VALUE
    assert set(values) == EXPECTED_FILLS[persona] | {TAG}
    assert {m.field for m in missing} == set(EMAIL_FIELDS) - EXPECTED_FILLS[persona]
    # …and with the tag removed, the same row plus the one question about it
    _, gone = fill_email_fields(fields, _with_tags(_full_context(), {}), persona=persona)
    assert {m.field for m in gone} == (set(EMAIL_FIELDS) - EXPECTED_FILLS[persona]) | {TAG}
    assert [m.reason for m in gone if m.field == TAG] == ["tag personalizada removida"]


# ── the name, the value, the whole map ───────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["ab", "a1", "a_", "sala2", "horario_atendimento",
                                  "a" + "b" * 30])
def test_names_that_are_tags(name):
    assert ef.custom_tag_problems(name, "valor") == ()
    assert ef.is_custom_tag_name(name)


@pytest.mark.parametrize("name", ["", "a", "Horario", "horário", "1abc", "_abc", "a-b", "a b",
                                  " ab", "ab ", "a" + "b" * 31, "ab\n", "[ab]"])
def test_names_that_are_not(name):
    (reason,) = ef.custom_tag_problems(name, "valor")
    assert "não serve como nome de tag" in reason
    assert not ef.is_custom_tag_name(name)


@pytest.mark.parametrize("value, words", [
    ("", "está vazio"),
    ("   \n  ", "está vazio"),
    ("x" * 501, "tem 501 caracteres; o máximo é 500"),
    ("linha\x00com nulo", "caractere de controle"),
    ("sino\x07", "caractere de controle"),
    (42, "tem de ser texto"),
    (None, "tem de ser texto"),
])
def test_values_that_are_refused(value, words):
    (reason,) = ef.custom_tag_problems(TAG, value)
    assert reason.startswith(f"o valor de [{TAG}] ") and words in reason, reason


@pytest.mark.parametrize("value, stored", [
    ("x" * 500, "x" * 500),
    ("  Rua Exemplo, 10  ", "Rua Exemplo, 10"),
    ("Segunda a sexta\r\nSábado até 12h", "Segunda a sexta\nSábado até 12h"),
    ("coluna\ta\ncoluna\tb", "coluna\ta\ncoluna\tb"),
    ("[nome] fica como texto", "[nome] fica como texto"),
])
def test_values_that_are_kept_and_how_they_are_stored(value, stored):
    assert ef.custom_tag_problems(TAG, value) == ()
    assert ef.normalise_custom_tags({TAG: value}) == ({TAG: stored}, ())


def test_the_whole_map_is_refused_by_every_reason_and_stores_nothing():
    stored, refusals = ef.normalise_custom_tags({"nome": "x", "boa_tag": "ok", "Ruim": "y"})
    assert stored == {} and len(refusals) == 2
    assert ef.normalise_custom_tags(["nao", "um", "mapa"]) == (
        {}, ("as tags personalizadas são um objeto {nome: valor}",))
    too_many = {f"tag_{i}": "v" for i in range(ef.MAX_CUSTOM_TAGS + 1)}
    assert ef.normalise_custom_tags(too_many) == (
        {}, (f"{ef.MAX_CUSTOM_TAGS + 1} tags personalizadas; o máximo é {ef.MAX_CUSTOM_TAGS}",))
    assert ef.normalise_custom_tags({}) == ({}, ())


def test_the_tolerant_reader_drops_what_the_save_would_refuse_and_never_raises():
    raw = {TAG: f"  {VALUE}  ", "nome": "x", "Ruim": "y", "vazia": "  ", "n2": 7}
    assert ef.parse_custom_tags(raw) == {TAG: VALUE}
    for garbage in (None, "texto", 7, ["a"], {1: "x"}):
        assert ef.parse_custom_tags(garbage) == {}


# ── the subject, the render, the grammar of a marker ────────────────────────────────────────

def test_a_multi_line_value_never_reaches_a_subject():
    tags = {"endereco_sede": "Rua Exemplo, 10\nCentro"}
    (reason,) = validate_template("Visita — [endereco_sede]", "corpo", custom_tags=tags)
    assert reason == ("[endereco_sede] não pode ir no assunto (o valor dessa tag da empresa tem "
                      "várias linhas)")
    # in the body it is fine, and a one-line value in the subject is fine
    assert validate_template("Visita", "Endereço:\n[endereco_sede]", custom_tags=tags) == ()
    assert validate_template("Visita — [endereco_sede]", "corpo",
                             custom_tags={"endereco_sede": "Rua Exemplo, 10"}) == ()


def test_a_value_is_never_read_as_a_template():
    tags = {TAG: "das 8h às 18h [nome] [total]"}
    values, missing = fill_email_fields(template_fields(*T_HOURS), _with_tags(_host_half(), tags))
    assert missing == ()
    _, body = render_email(*T_HOURS, values)
    assert "Atendemos das 8h às 18h [nome] [total]." in body


def test_a_tag_with_digits_is_a_marker_and_a_bracketed_number_still_opens_none():
    tags = {"sala2": "Sala 2, térreo"}
    assert validate_template("Aviso", "Local: [sala2]", custom_tags=tags) == ()
    assert template_fields("Aviso", "Local: [sala2]") == ("sala2",)
    # a number in brackets was never a marker and is not one now
    (reason,) = validate_template("Aviso", "Ref. [2026]", custom_tags=tags)
    assert "abre um «[» que não é marcador" in reason


def test_the_tenants_tags_change_no_verdict_across_personas():
    verdicts = {validate_template(*T_HOURS, persona=p, custom_tags=TAGS)
                for p in ("COORDINATOR", "SECRETARY", "BOOKKEEPER", "", None)}
    assert verdicts == {()}


def test_EmailContext_keeps_building_without_tags():
    ctx = EmailContext(month="2026-10")
    assert dict(ctx.custom_tags) == {}


def test_the_readme_documents_the_company_tags():
    import pathlib
    root = pathlib.Path(ef.__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8").split(
        "### Templated e-mail fields", 1)[1].split("\n**Prompt-only personas.**", 1)[0]
    for name in ("custom_tags=", "any_company_tag", "normalise_custom_tags", "parse_custom_tags",
                 "custom_tag_problems", "CUSTOM_TAG_NAME", "MAX_CUSTOM_TAG_CHARS",
                 "MAX_CUSTOM_TAGS", "EmailContext.custom_tags", ef.CUSTOM_TAG_REMOVED,
                 ef.CUSTOM_TAG_SOURCE):
        assert name in readme, name
    assert f"({ef.MAX_CUSTOM_TAG_CHARS})" in readme and f"({ef.MAX_CUSTOM_TAGS})" in readme

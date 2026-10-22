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
  keeps it because the host names the tags the tenant REMOVED (``removed_tags=``), and the fill
  says ``missing`` — «tag personalizada removida» — so the send asks the requester instead of
  sending. A name the tenant never declared (a typo) is refused at BOTH doors, as before;
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
    GENERIC_FIELDS,
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
    # T_ALL cites the coordination's five: valid for the COORDINATOR only (2026-10-22)
    assert validate_template(*T_ALL, persona="COORDINATOR", custom_tags=TAGS) == \
        validate_template(*T_ALL, persona="COORDINATOR") == ()
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
    """Every name of the union is refused. The sentence of a GENERIC marker is the one of before,
    byte for byte; a coordination marker is no longer «padrão» (2026-10-22: the default list is
    the eight), so its sentence says whose tag it is — the verdict is the same."""
    stored, refusals = ef.normalise_custom_tags({name: "valor"})
    assert stored == {}
    if name in GENERIC_FIELDS:
        assert refusals == (f"[{name}] já é um marcador padrão ({EMAIL_FIELDS[name].source}); "
                            "escolha outro nome",)
    else:
        assert refusals == (f"[{name}] já é uma tag da coordenação ({EMAIL_FIELDS[name].source}); "
                            "escolha outro nome",)


def test_the_sentence_of_a_generic_collision_is_the_bases_byte_for_byte():
    """CONTROL, pinned as text and not rebuilt from the code: the generic sentence did not move
    (green on the base and on the change)."""
    assert ef.custom_tag_problems("nome", "x") == (
        "[nome] já é um marcador padrão (o nome do destinatário no cadastro); escolha outro nome",)


def test_the_sentence_of_a_coordination_collision_says_whose_tag_it_is():
    """A TEXT change of the company tags, not a behaviour one: the name is refused as before, and
    the sentence no longer calls it «padrão» — the default list is the eight (2026-10-22)."""
    assert ef.custom_tag_problems("aulas", "x") == (
        "[aulas] já é uma tag da coordenação (as aulas do mês na agenda da coordenação); "
        "escolha outro nome",)


#: The coordination's five — typed here: the names the risk below is about.
COORDINATION = ("disciplinas", "aulas", "valor_por_aula", "valores_por_bonus", "total")


@pytest.mark.parametrize("name", COORDINATION)
@pytest.mark.parametrize("persona", ("COORDINATOR", "SECRETARY", None))
def test_a_coordination_name_stays_reserved_as_a_company_tag_after_the_list_shrank(name, persona):
    """The risk of 2026-10-22: the DEFAULT list became the eight generic markers, so a collision
    check that read it would now ACCEPT a company tag named ``aulas`` or ``total`` — a tag that
    collides with what the COORDINATOR computes. The reservation reads the UNION
    (:data:`EMAIL_FIELDS`), never the default list, in every persona."""
    assert f"[{name}]" not in known_markers()             # the condition: the list shrank…
    assert not ef.is_custom_tag_name(name)                 # …and the name is still no tag
    stored, refusals = ef.normalise_custom_tags({name: "valor"})
    assert stored == {} and len(refusals) == 1 and refusals[0].startswith(f"[{name}] já é ")
    assert ef.parse_custom_tags({name: "valor"}) == {}
    # a "tag" of that name unlocks nothing and fills nothing, whoever the template is for
    assert validate_template("Aviso", f"Texto: [{name}]", persona=persona,
                             custom_tags={name: "valor"}) == \
        validate_template("Aviso", f"Texto: [{name}]", persona=persona)
    values, _ = fill_email_fields((name,), _with_tags(_host_half(), {name: "VALOR DA TAG"}),
                                  persona=persona)
    assert values.get(name) != "VALOR DA TAG"


def test_control_a_company_tag_that_collides_with_nothing_still_passes():
    assert ef.is_custom_tag_name(TAG)
    assert ef.normalise_custom_tags(TAGS) == (TAGS, ())
    assert validate_template(*T_HOURS, persona="SECRETARY", custom_tags=TAGS) == ()


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
    # the turn door: a template whose tag was REMOVED still exists
    assert validate_template(*T_HOURS, custom_tags={}, removed_tags={TAG}) == ()
    values, missing = fill_email_fields(template_fields(*T_HOURS), _with_tags(_host_half(), {}))
    assert [m.field for m in missing] == [TAG]
    assert missing[0].reason == "tag personalizada removida"
    assert missing[0].source == ef.CUSTOM_TAG_SOURCE
    assert TAG not in values
    assert ("- [horario_atendimento] — tag personalizada removida (fonte: as tags "
            "personalizadas da empresa)") in missing_question(missing)
    with pytest.raises(ValueError):          # the floor under it: never rendered blank
        render_email(*T_HOURS, values)


def test_a_name_never_declared_is_refused_at_the_turn_as_at_the_save():
    """The turn opens only the names the tenant REMOVED: a typo (``[nmoe]``) is not one, and a
    template that says it is still refused — and dropped — at the turn, as it always was."""
    (reason,) = validate_template("Aviso", "Olá [nmoe]", custom_tags=TAGS, removed_tags={"outra"})
    assert reason.startswith("no corpo, [nmoe] não é um marcador;")
    # CONTROL — the same template, once [nmoe] is a name the tenant removed, is kept
    assert validate_template("Aviso", "Olá [nmoe]", removed_tags={"nmoe"}) == ()


def test_removed_names_open_nothing_but_a_tag_name():
    """A «removed» name that cannot be a tag (a reserved marker, a capital, one letter, a digit
    first, a standard marker) changes no verdict."""
    junk = {"cpf_cnpj", "Nome", "x", "1abc", "nome", "aulas"}
    for subject, body in (("NF", "[cpf_cnpj]"), ("Aviso", "Olá [Nome]"), ("Aviso", "[x]"),
                          ("Aviso", "[1abc]"), ("Total [aulas]", "corpo"), ("Aviso", "[nmoe]")):
        assert validate_template(subject, body, removed_tags=junk) == \
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
    reasons = validate_template(subject, body, persona=persona, custom_tags=TAGS)
    if EXPECTED_FILLS[persona] == frozenset(EMAIL_FIELDS):
        assert reasons == ()
    else:
        # only the coordination's markers are refused (2026-10-22); the company tag never is
        assert reasons and all("é uma tag da coordenação (COORDINATOR)" in r for r in reasons)
        assert not any(f"[{TAG}]" in r.split(";", 1)[0] for r in reasons)
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
    # 2026-10-22: an EMPTY value is a FREE tag (``test_email_free_tags.py``) — inverted from
    # the refusal «está vazio» the G package pinned.
    ("", ""),
    ("   \n  ", ""),
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
    # 2026-10-22: the blank value is a FREE tag now, kept empty (it was dropped)
    assert ef.parse_custom_tags(raw) == {TAG: VALUE, "vazia": ""}
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
    for name in ("custom_tags=", "removed_tags=", "normalise_custom_tags", "parse_custom_tags",
                 "custom_tag_problems", "CUSTOM_TAG_NAME", "MAX_CUSTOM_TAG_CHARS",
                 "MAX_CUSTOM_TAGS", "EmailContext.custom_tags", ef.CUSTOM_TAG_REMOVED,
                 ef.CUSTOM_TAG_SOURCE):
        assert name in readme, name
    assert f"({ef.MAX_CUSTOM_TAG_CHARS})" in readme and f"({ef.MAX_CUSTOM_TAGS})" in readme

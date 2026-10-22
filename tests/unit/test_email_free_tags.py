"""FREE company tags — a tag of the tenant with no fixed value, filled from the CONVERSATION.

The owner (2026-10-22): «preciso q seja flexivel e chamada pelo usuario»; «o template terá tags
que devem ser preenchidas conforme as mensagens com o agente»; «tags padrões são preenchidas
automaticamente». A company tag whose stored value is EMPTY is FREE: the value comes from what
the person who asked said (``EmailContext.free_tag_values``, what the executor took from the
conversation), and a free tag with no value is a :class:`Missing` — the send ASKS, the path that
already existed. A tag with a value stays FIXED, exactly as the G package left it. What is pinned,
one line each:

* the twin — an empty value SAVES as a free tag (on the base it was refused «está vazio»), a
  template citing it passes both doors, and the fill uses the conversation's value;
* without the value the fill asks, in exact words, with the tenant's hint when there is one;
* a FIXED value of before and a FREE tag of now live in the SAME map, through the save door, the
  turn door and the fill: with the free value in the request the e-mail is
  whole; without it, the one question is about the free tag and the fixed one is filled;
* a fixed tag stays fixed: a value the conversation gives for it, for a generic marker or for a
  name that is no tag, changes nothing;
* the free tag is still a company tag: the thirteen names and the reserved ones are refused
  whatever the value (the reservation of [R-T8]); a REMOVED free tag is the removed path;
* the conversation's value is plain text on ONE line, at most 500 characters, and is never read
  as a template;
* the hint is the tenant's plain text, one line, at most 120 characters, and only for a free tag;
* PER PERSONA, the rows of ``test_email_fill_by_persona.py`` (derived from FIELD_PROVIDERS).

Everything here is invented.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.email_fields import (
    EMAIL_FIELDS,
    REFUSED_FIELDS,
    EmailContext,
    fill_email_fields,
    missing_question,
    render_email,
    template_fields,
    validate_template,
)
from tests.unit.test_email_fill_by_persona import EXPECTED_FILLS, T_ALL, _full_context

FREE = "disciplina"
FIXED = "horario_atendimento"
FIXED_VALUE = "de segunda a sexta, das 8h às 18h"
HINT = "a disciplina da aula remarcada"

#: A notice that cites one FIXED tag (of the G package) and one FREE tag (of now) — invented.
T_MIXED = ("Remarcação de [disciplina] — [empresa]",
           "Olá, [nome],\n\nA aula de [disciplina] foi remarcada.\n"
           "Atendimento: [horario_atendimento].\n\n[assinatura]")


def _host_half(**kw) -> EmailContext:
    base = dict(recipient_name="Prof Alfa", recipient_email="alfa@captura.local",
                tenant_name="Escola Exemplo", month="2026-10", today=date(2026, 10, 7),
                persona_name="Assistente Vexa", requester_name="Coord Gama")
    base.update(kw)
    return EmailContext(**base)


def _ctx(tags, values=None, hints=None, base=None) -> EmailContext:
    return dataclasses.replace(base or _host_half(), custom_tags=dict(tags),
                               free_tag_values=dict(values or {}),
                               custom_tag_hints=dict(hints or {}))


# ── the twin: an empty value is a FREE tag ──────────────────────────────────────────────────

def test_an_empty_value_saves_as_a_free_tag():
    """RED on the base: «o valor de [disciplina] está vazio»."""
    assert ef.custom_tag_problems(FREE, "") == ()
    assert ef.normalise_custom_tags({FREE: ""}) == ({FREE: ""}, ())
    assert ef.parse_custom_tags({FREE: ""}) == {FREE: ""}
    assert ef.free_tags({FREE: "", FIXED: FIXED_VALUE}) == (FREE,)


def test_blanks_are_an_empty_value_and_are_stored_empty():
    assert ef.normalise_custom_tags({FREE: "   \n\t "}) == ({FREE: ""}, ())


def test_a_template_with_a_free_tag_passes_both_doors():
    """A CONTROL (green on the base): the template's validator never read a tag's value except
    to keep a multi-line one out of the subject — the door that refused the empty value was
    the MAP's (above). Pinned so neither door starts refusing a free tag."""
    tags = {FREE: ""}
    assert validate_template("Aviso", "Disciplina: [disciplina]", custom_tags=tags) == ()
    assert validate_template("Aviso", "Disciplina: [disciplina]", custom_tags=tags,
                             removed_tags=()) == ()
    # …and in the subject: its value is one line by construction (below)
    assert validate_template("Aula de [disciplina]", "corpo", custom_tags=tags) == ()


def test_the_free_tag_is_filled_from_the_conversation():
    values, missing = fill_email_fields(("disciplina",), _ctx({FREE: ""}, {FREE: "Física"}))
    assert missing == ()
    assert values == {FREE: "Física"}


def test_without_the_value_the_fill_asks_in_exact_words():
    values, missing = fill_email_fields(("disciplina",), _ctx({FREE: ""}))
    assert FREE not in values
    (m,) = missing
    assert (m.field, m.source, m.reason) == (
        FREE, "o que o solicitante disser na conversa", "o pedido não disse o que pôr nesta tag")
    assert missing_question(missing) == (
        "Não consigo montar este e-mail sem o que falta:\n"
        "- [disciplina] — o pedido não disse o que pôr nesta tag (fonte: o que o solicitante "
        "disser na conversa)")


def test_the_question_carries_the_tenants_hint():
    _, (m,) = fill_email_fields(("disciplina",), _ctx({FREE: ""}, hints={FREE: HINT}))
    assert m.reason == f"o pedido não disse o que pôr nesta tag: {HINT}"
    assert m.sentence() == ("[disciplina] — o pedido não disse o que pôr nesta tag: a disciplina "
                            "da aula remarcada (fonte: o que o solicitante disser na conversa)")


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_a_blank_value_is_a_value_nobody_said(blank):
    _, (m,) = fill_email_fields(("disciplina",), _ctx({FREE: ""}, {FREE: blank}))
    assert m.reason == ef.CUSTOM_TAG_FREE_MISSING


# ── a FIXED value of before and a FREE tag of now, in the SAME map ──────────────────────────

def test_fixed_and_free_live_in_one_map_at_the_save_and_at_the_turn():
    raw = {FIXED: f"  {FIXED_VALUE}  ", FREE: ""}
    stored, refusals = ef.normalise_custom_tags(raw)
    assert refusals == () and stored == {FIXED: FIXED_VALUE, FREE: ""}
    assert ef.parse_custom_tags(stored) == stored
    assert ef.free_tags(stored) == (FREE,)
    assert validate_template(*T_MIXED, custom_tags=stored) == ()
    assert validate_template(*T_MIXED, persona="SECRETARY", custom_tags=stored) == ()


def test_fixed_and_free_with_the_value_in_the_request_the_email_is_whole():
    tags = {FIXED: FIXED_VALUE, FREE: ""}
    values, missing = fill_email_fields(template_fields(*T_MIXED),
                                        _ctx(tags, {FREE: "Física"}, {FREE: HINT}))
    assert missing == ()
    subject, body = render_email(*T_MIXED, values)
    assert subject == "Remarcação de Física — Escola Exemplo"
    assert body == ("Olá, Prof Alfa,\n\nA aula de Física foi remarcada.\n"
                    f"Atendimento: {FIXED_VALUE}.\n\nAssistente Vexa")


def test_fixed_and_free_without_the_value_one_question_and_the_fixed_one_filled():
    tags = {FIXED: FIXED_VALUE, FREE: ""}
    values, missing = fill_email_fields(template_fields(*T_MIXED), _ctx(tags, hints={FREE: HINT}))
    assert values[FIXED] == FIXED_VALUE
    assert [m.field for m in missing] == [FREE]
    assert missing_question(missing) == (
        "Não consigo montar este e-mail sem o que falta:\n"
        "- [disciplina] — o pedido não disse o que pôr nesta tag: a disciplina da aula "
        "remarcada (fonte: o que o solicitante disser na conversa)")


def test_control_a_map_the_g_package_stored_reads_and_fills_as_before():
    """A string with a value is a FIXED tag, as the G package stored it: read, validated and
    filled exactly as on the base — with or without anything the conversation says."""
    g_map = {FIXED: FIXED_VALUE, "sala2": "Sala 2, térreo"}
    assert ef.parse_custom_tags(g_map) == g_map
    assert ef.free_tags(g_map) == ()
    tpl = ("Horário — [empresa]", "Atendemos [horario_atendimento] na [sala2].")
    base = fill_email_fields(template_fields(*tpl), dataclasses.replace(_host_half(),
                                                                        custom_tags=g_map))
    talked = fill_email_fields(template_fields(*tpl),
                               _ctx(g_map, {FIXED: "OUTRO", "sala2": "OUTRA"}))
    assert base == talked
    assert {k: base[0][k] for k in g_map} == g_map


# ── a fixed tag stays fixed; nothing else is opened ─────────────────────────────────────────

def test_a_value_for_a_fixed_tag_a_generic_marker_or_no_tag_changes_nothing():
    tags = {FIXED: FIXED_VALUE, FREE: ""}
    values, _ = fill_email_fields(("horario_atendimento", "nome", "disciplina"),
                                  _ctx(tags, {FIXED: "outra hora", "nome": "Outro Nome",
                                              "nmoe": "x", FREE: "Física"}))
    assert values == {FIXED: FIXED_VALUE, "nome": "Prof Alfa", FREE: "Física"}


@pytest.mark.parametrize("name", sorted(EMAIL_FIELDS) + sorted(REFUSED_FIELDS))
def test_a_free_tag_cannot_take_a_reserved_name(name):
    """The reservation of [R-T8]: a FREE tag is a company tag, and the thirteen names (the
    union — the coordination's five included) and the reserved ones are refused whatever the
    value. A CONTROL: the name is checked before the value, so this held on the base too."""
    (reason,) = ef.custom_tag_problems(name, "")
    assert reason.startswith(f"[{name}] ") and "está vazio" not in reason
    assert ef.normalise_custom_tags({name: ""})[0] == {}
    assert ef.parse_custom_tags({name: ""}) == {}


@pytest.mark.parametrize("name", sorted(EMAIL_FIELDS) + sorted(REFUSED_FIELDS))
def test_a_reserved_name_is_never_a_free_tag_nor_filled_by_the_conversation(name):
    assert ef.free_tags({name: ""}) == ()
    values, _ = fill_email_fields((name,), _ctx({name: ""}, {name: "VALOR DA CONVERSA"}))
    assert values.get(name) != "VALOR DA CONVERSA"


def test_a_removed_free_tag_is_the_removed_path_whatever_the_conversation_says():
    tpl = ("Aviso", "Disciplina: [disciplina]")
    assert validate_template(*tpl, custom_tags={}, removed_tags={FREE}) == ()
    _, (m,) = fill_email_fields(template_fields(*tpl), _ctx({}, {FREE: "Física"}))
    assert m.reason == ef.CUSTOM_TAG_REMOVED and m.source == ef.CUSTOM_TAG_SOURCE


# ── the conversation's value ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("given, filled", [
    ("  Física  ", "Física"),
    ("terça\nàs 10h", "terça às 10h"),
    ("terça \t às\r\n10h", "terça às 10h"),
    ("x" * 500, "x" * 500),
    ("[nome] e [total]", "[nome] e [total]"),
])
def test_the_conversations_value_is_one_line_of_plain_text(given, filled):
    values, missing = fill_email_fields(("disciplina",), _ctx({FREE: ""}, {FREE: given}))
    assert missing == () and values[FREE] == filled


@pytest.mark.parametrize("given, words", [
    ("x" * 501, "o valor de [disciplina] tem 501 caracteres; o máximo é 500"),
    ("sino\x07", "o valor de [disciplina] tem um caractere de controle"),
    (42, "o valor de [disciplina] tem de ser texto"),
])
def test_a_conversation_value_the_rule_refuses_is_asked_never_sent(given, words):
    values, (m,) = fill_email_fields(("disciplina",), _ctx({FREE: ""}, {FREE: given}))
    assert FREE not in values
    assert m.source == ef.CUSTOM_TAG_FREE_SOURCE and m.reason.startswith(words), m.reason


def test_a_free_value_is_never_read_as_a_template_and_one_line_never_breaks_a_subject():
    tpl = ("Aula de [disciplina]", "Olá [nome]: [disciplina].")
    values, missing = fill_email_fields(template_fields(*tpl),
                                        _ctx({FREE: ""}, {FREE: "Física\n[total] [nome]"}))
    assert missing == ()
    subject, body = render_email(*tpl, values)
    assert subject == "Aula de Física [total] [nome]"
    assert body == "Olá Prof Alfa: Física [total] [nome]."


# ── the hint ────────────────────────────────────────────────────────────────────────────────

def test_a_hint_for_a_free_tag_is_kept():
    tags = {FREE: "", FIXED: FIXED_VALUE}
    assert ef.normalise_custom_tag_hints({FREE: f"  {HINT}  "}, tags) == ({FREE: HINT}, ())
    assert ef.parse_custom_tag_hints({FREE: HINT}, tags) == {FREE: HINT}
    assert ef.normalise_custom_tag_hints(None, tags) == ({}, ())
    assert ef.normalise_custom_tag_hints({FREE: "  "}, tags) == ({}, ())   # empty: no hint


@pytest.mark.parametrize("name, hint, words", [
    (FIXED, "dica", "[horario_atendimento] tem valor fixo"),
    ("nmoe", "dica", "a dica de «nmoe» não é de nenhuma tag da empresa"),
    (FREE, "duas\nlinhas", "a dica de [disciplina] tem de ser uma linha só"),
    (FREE, "sino\x07", "a dica de [disciplina] tem um caractere de controle"),
    (FREE, "x" * 121, "a dica de [disciplina] tem 121 caracteres; o máximo é 120"),
    (FREE, 7, "a dica de [disciplina] tem de ser texto"),
])
def test_hints_that_are_refused(name, hint, words):
    tags = {FREE: "", FIXED: FIXED_VALUE}
    (reason,) = ef.custom_tag_hint_problems(name, hint, tags)
    assert reason.startswith(words), reason
    stored, refusals = ef.normalise_custom_tag_hints({name: hint}, tags)
    assert stored == {} and refusals == (reason,)
    assert ef.parse_custom_tag_hints({name: hint}, tags) == {}


def test_the_hint_map_is_an_object():
    assert ef.normalise_custom_tag_hints(["x"], {FREE: ""}) == (
        {}, ("as dicas das tags são um objeto {nome: dica}",))
    for garbage in ("texto", 7, ["a"]):
        assert ef.parse_custom_tag_hints(garbage, {FREE: ""}) == {}


def test_a_hint_the_fill_is_handed_around_the_door_is_not_used():
    _, (m,) = fill_email_fields(("disciplina",), _ctx({FREE: ""}, hints={FREE: "a\nb"}))
    assert m.reason == ef.CUSTOM_TAG_FREE_MISSING


# ── per persona ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("persona", sorted(EXPECTED_FILLS))
def test_the_free_tag_fills_or_asks_in_every_persona_and_leaves_the_row_as_it_was(persona):
    subject, body = T_ALL[0], T_ALL[1] + "\n\nDisciplina: [disciplina]"
    fields = template_fields(subject, body)
    tags = {FREE: "", FIXED: FIXED_VALUE}
    base = _full_context()
    values, missing = fill_email_fields(fields, _ctx(tags, {FREE: "Física"}, base=base),
                                        persona=persona)
    assert values[FREE] == "Física"
    assert set(values) == EXPECTED_FILLS[persona] | {FREE}
    assert {m.field for m in missing} == set(EMAIL_FIELDS) - EXPECTED_FILLS[persona]
    _, asked = fill_email_fields(fields, _ctx(tags, base=base), persona=persona)
    assert {m.field for m in asked} == (set(EMAIL_FIELDS) - EXPECTED_FILLS[persona]) | {FREE}
    assert [m.reason for m in asked if m.field == FREE] == [ef.CUSTOM_TAG_FREE_MISSING]


def test_EmailContext_keeps_building_without_free_values_or_hints():
    ctx = EmailContext(month="2026-10")
    assert dict(ctx.free_tag_values) == {} and dict(ctx.custom_tag_hints) == {}


def test_the_readme_documents_the_free_tags():
    import pathlib
    root = pathlib.Path(ef.__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8").split(
        "### Templated e-mail fields", 1)[1].split("\n**Prompt-only personas.**", 1)[0]
    for name in ("free_tags", "free_tag_values", "custom_tag_hints",
                 "normalise_custom_tag_hints", "parse_custom_tag_hints",
                 "custom_tag_hint_problems", "MAX_CUSTOM_TAG_HINT_CHARS",
                 ef.CUSTOM_TAG_FREE_SOURCE, ef.CUSTOM_TAG_FREE_MISSING):
        assert name in readme, name

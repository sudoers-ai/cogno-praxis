"""Templated e-mail fields (``cogno_praxis.email_fields``): the validator, the one definition, the
fill and the render.

Everything here is synthetic: invented professors, an invented school, invented values. What is
pinned, one line each:

* the template validator refuses each bad shape, and the SAME template corrected passes;
* the marker list has ONE definition, and the prose that documents it cites nothing outside it;
* every field that cannot be filled is a named ``Missing``, and a complete context has none;
* the render is byte-for-byte over the owner's two template shapes, deterministic, and one pass.

**R-T13 (2026-10-22): what is NO LONGER here, and where it lives.** The coordination's five values
were filled by a provider from ``CoordinatorService.email_context``; they are the tenant's FREE
tags now, filled by the persona from its tools, and the provider and its read are gone. The two
e-mails it rendered are pinned below byte for byte, from the values the coordination copies. The
provider's own behaviours moved with the arithmetic, to the TOOLS: the classes of a month, the
hour, the payable rows (``test_coordinator_*``), the pay figures, every band in every bonus state
and the condition (``test_coordinator_pay.py``,
``test_the_tools_print_what_an_email_copies.py``); a value no read gives is a free tag nobody
filled, and asked (``test_email_free_tag_records.py``); the generic path's equality with the
provider over a whole corpus is ``test_the_coordination_by_the_generic_path.py``.
"""

from __future__ import annotations

import dataclasses
import pathlib
from datetime import date

import pytest

from cogno_praxis.email_fields import (
    EMAIL_FIELDS,
    MAX_BODY_CHARS,
    MAX_CONTEUDO_CHARS,
    REFUSED_FIELDS,
    SUBJECT_FORBIDDEN,
    EmailContext,
    email_digest,
    fill_email_fields,
    known_markers,
    markers_cited,
    month_words,
    render_email,
    template_fields,
    validate_template,
)

ME = "Prof Alfa"                  # invented
SCHOOL = "Escola Exemplo"         # invented
ADDRESS = "alfa@captura.local"    # invented, under a capture domain
_TODAY = date(2026, 9, 20)

#: The coordination's five, as the tenant's FREE tags (R-T13).
FIVE = ("aulas", "disciplinas", "valor_por_aula", "valores_por_bonus", "total")
FREE = {n: "" for n in FIVE}
#: What the coordination passes for them, COPIED from its two tools for one professor's September
#: (four classes × 4 h × R$ 120,00 = R$ 1.920,00; the IBOPE result read is 92%).
VALUES = {
    "aulas": [
        {"mês": "setembro", "dia": "sáb", "data": "05/09", "horário": "08:00",
         "disciplina": "Bancos NoSQL", "turma": "Turma AA_01"},
        {"mês": "setembro", "dia": "sáb", "data": "12/09", "horário": "08:00",
         "disciplina": "Bancos NoSQL", "turma": "Turma AA_01"},
        {"mês": "setembro", "dia": "sáb", "data": "19/09", "horário": "13:30",
         "disciplina": "Bancos NoSQL", "turma": "Turma BB_02"},
        {"mês": "setembro", "dia": "sáb", "data": "26/09", "horário": "",
         "disciplina": "Estatistica Aplicada", "turma": "Turma AA_01"}],
    "disciplinas": [{"disciplina": "Bancos NoSQL"}, {"disciplina": "Estatistica Aplicada"}],
    "valor_por_aula": "R$ 480,00",
    "valores_por_bonus": [
        {"faixa": "Sem bônus", "valor": "R$ 1.920,00"},
        {"faixa": "IBOPE 80–89%", "valor": "R$ 2.400,00"},
        {"faixa": "IBOPE 90%+", "valor": "R$ 2.560,00 ← apurado (IBOPE 92%)"}],
    "total": "R$ 2.560,00",
}


def _ctx(*, month: str = "2026-09", conteudo: str = "", values: "dict | None" = None,
         **kw) -> EmailContext:
    base = dict(recipient_name=ME, recipient_email=ADDRESS, tenant_name=SCHOOL, month=month,
                conteudo=conteudo, today=_TODAY, custom_tags=FREE,
                free_tag_values=VALUES if values is None else values)
    return EmailContext(**{**base, **kw})


# The owner's two templates, in their SHAPE (2026-10-06): a class schedule, and the
# informative e-mail for the invoice the professor issues. Text and names invented.
T_SCHEDULE = ("Cronograma de aulas — [mes]",
              "Olá, [nome],\n\nSegue o seu cronograma de aulas de [mes] na [empresa]:\n\n"
              "[aulas]\n\nDisciplinas do mês:\n[disciplinas]\n\n[conteudo]\n\n"
              "Atenciosamente,\nCoordenação — [empresa]")
T_INVOICE = ("Emissão de nota fiscal — [mes]",
             "Olá, [nome],\n\nPara a sua nota fiscal de [mes], estes são os valores estimados por "
             "nível de bônus (valor por aula: [valor_por_aula]):\n\n[valores_por_bonus]\n\n"
             "Aulas consideradas:\n[aulas]\n\nAtenciosamente,\n[empresa]")


# ── validate_template: each refusal, and the same template corrected ─────────────────────────

@pytest.mark.parametrize("bad, fixed, words", [
    (("Aulas", "Olá [nmoe]"), ("Aulas", "Olá [nome]"), "[nmoe] não é um marcador"),
    (("Aulas", "Olá [Nome]"), ("Aulas", "Olá [nome]"), "não é marcador"),
    (("Aulas", "valor [ em aberto"), ("Aulas", "valor em aberto"), "não é marcador"),
    (("Aulas", "[conteudo] e [conteudo]"), ("Aulas", "[conteudo] e mais"), "aparece 2 vezes"),
    (("[conteudo]", "corpo [nome]"), ("Aviso", "corpo [nome] [conteudo]"), "assunto"),
    (("Contrato", "Anexo: [contrato]"), ("Contrato", "Anexo em breve"), "fase E3"),
    (("NF", "CPF: [cpf_cnpj]"), ("NF", "Nome: [nome]"), "decisão do dono"),
    (("", "corpo"), ("Assunto", "corpo"), "o assunto está vazio"),
    (("Assunto", "   "), ("Assunto", "corpo"), "o corpo está vazio"),
    (("Assunto", "x" * (MAX_BODY_CHARS + 1)), ("Assunto", "x" * MAX_BODY_CHARS), "o máximo é"),
    (("Linha 1\nLinha 2", "corpo"), ("Linha 1", "corpo"), "uma linha só"),
])
def test_each_refusal_and_the_same_template_corrected_passes(bad, fixed, words):
    reasons = validate_template(*bad)
    assert reasons and any(words in r for r in reasons), reasons
    assert validate_template(*fixed) == ()


def test_an_unknown_marker_refusal_lists_the_markers_that_exist():
    (reason,) = validate_template("Aulas", "Olá [nmoe]")
    for marker in known_markers():
        assert marker in reason


def test_the_owners_two_templates_are_valid_with_the_tenants_tags_for_every_persona():
    """R-T13: the coordination's five are the tenant's FREE tags. With them declared, the owner's
    two templates save for any persona; without them, they are unknown markers — the same verdict
    for every persona, naming no persona."""
    for persona in ("COORDINATOR", "SECRETARY", None):
        assert validate_template(*T_SCHEDULE, persona=persona, custom_tags=FREE) == ()
        assert validate_template(*T_INVOICE, persona=persona, custom_tags=FREE) == ()
    for template in (T_SCHEDULE, T_INVOICE):
        reasons = validate_template(*template)
        assert reasons and all("não é um marcador" in r for r in reasons)


def test_contrato_opens_in_E3_and_cpf_never_does():
    assert validate_template("Contrato", "[contrato]", phase="E3") == ()
    assert validate_template("NF", "[cpf_cnpj]", phase="E3")
    with pytest.raises(ValueError):
        validate_template("x", "y", phase="E9")


# ── one definition ───────────────────────────────────────────────────────────────────────────

def test_the_list_is_derived_once_and_the_docs_cite_nothing_outside_it():
    """The molde of ``test_code_domains_match_prompt_domains_exactly``: the doc that explains the
    markers is checked AGAINST the list, so a marker added to the prose and not to the code (or
    the other way round) fails here."""
    import cogno_praxis.email_fields as ef
    # ``[nmoe]`` is the docs' deliberate counter-example — the typo the validator exists to catch;
    # ``[horario_atendimento]`` is their example of a tenant's company tag, and is one; the
    # coordination's five (R-T13) are the docs' example of FREE tags, and are names a tag may take.
    examples = {"horario_atendimento", *FIVE}
    allowed = set(EMAIL_FIELDS) | set(REFUSED_FIELDS) | {"nmoe"} | examples
    assert all(ef.is_custom_tag_name(n) for n in examples)
    root = pathlib.Path(ef.__file__).resolve().parents[1]
    whole = (root / "README.md").read_text(encoding="utf-8")
    head = "### Templated e-mail fields"
    assert head in whole, "the README section on templated e-mail is missing"
    readme = whole.split(head, 1)[1].split("\n**Prompt-only personas.**", 1)[0]
    for text in (ef.__doc__ or "", readme):
        stray = [m for m in markers_cited(text) if m not in allowed]
        assert stray == [], stray
    # every marker is documented in the README, by name — the default list and each persona's
    for marker in EMAIL_FIELDS:
        assert f"[{marker}]" in readme, marker
    assert SUBJECT_FORBIDDEN <= set(EMAIL_FIELDS)


def test_template_fields_are_in_order_of_first_use_subject_first():
    assert template_fields("[mes] — [nome]", "[aulas] [nome] [mes] [total]") == (
        "mes", "nome", "aulas", "total")


# ── fill: each Missing, and the complete context ─────────────────────────────────────────────

def _fill(template, ctx):
    return fill_email_fields(template_fields(*template), ctx)


def test_the_complete_context_has_no_missing_field():
    values, missing = _fill(T_SCHEDULE, _ctx(conteudo="Bom mês!"))
    assert missing == ()
    values, missing = _fill(T_INVOICE, _ctx())
    assert missing == ()
    assert set(values) == set(template_fields(*T_INVOICE))


@pytest.mark.parametrize("change, field, words", [
    ({"recipient_name": ""}, "nome", "não tem nome no cadastro"),
    ({"recipient_email": ""}, "email", "não tem e-mail no cadastro"),
    ({"tenant_name": ""}, "empresa", "o tenant não tem nome"),
    ({"conteudo": ""}, "conteudo", "não trouxe o texto"),
    ({"conteudo": "x" * (MAX_CONTEUDO_CHARS + 1)}, "conteudo", "o máximo é"),
])
def test_each_missing_field_names_itself_and_its_source(change, field, words):
    ctx = dataclasses.replace(_ctx(conteudo="Bom mês!"), **change)
    _, missing = _fill(T_SCHEDULE, ctx)
    assert [m.field for m in missing] == [field], missing
    assert words in missing[0].reason
    assert missing[0].source == EMAIL_FIELDS[field].source


def test_a_value_the_coordination_did_not_pass_is_asked():
    """A free tag no read filled is a ``Missing`` — the question, never an e-mail with a gap."""
    values = {k: v for k, v in VALUES.items() if k != "aulas"}
    _, missing = _fill(T_SCHEDULE, _ctx(conteudo="x", values=values))
    assert [m.field for m in missing] == ["aulas"]


def test_the_address_STOPS_the_send_even_when_the_body_never_quotes_it():
    ctx = dataclasses.replace(_ctx(conteudo="x"), recipient_email="")
    assert "email" not in template_fields(*T_SCHEDULE)
    _, missing = _fill(T_SCHEDULE, ctx)
    assert [m.field for m in missing] == ["email"]


def test_free_text_for_a_template_with_no_room_for_it_is_refused():
    values, missing = _fill(T_INVOICE, _ctx(conteudo="um recado"))
    assert [m.field for m in missing] == ["conteudo"]
    assert "não tem espaço para texto livre" in missing[0].reason


@pytest.mark.parametrize("month, words", [("", "não diz de que mês"),
                                          ("setembro", "não é AAAA-MM"),
                                          ("2026-13", "não é AAAA-MM")])
def test_a_month_that_is_not_YYYY_MM_is_missing(month, words):
    _, missing = _fill(T_SCHEDULE, _ctx(month=month, conteudo="x"))
    by = {m.field: m.reason for m in missing}
    assert set(by) == {"mes"} and words in by["mes"]


# ── render: byte for byte, deterministic, one pass ───────────────────────────────────────────

_EXPECTED_SCHEDULE = (
    "Cronograma de aulas — setembro/2026",
    "Olá, Prof Alfa,\n\nSegue o seu cronograma de aulas de setembro/2026 na Escola Exemplo:\n\n"
    "Turma AA_01\n05/09 (sáb) 08:00 — Bancos NoSQL\n12/09 (sáb) 08:00 — Bancos NoSQL\n"
    "26/09 (sáb) — Estatistica Aplicada\n\nTurma BB_02\n19/09 (sáb) 13:30 — Bancos NoSQL\n\n"
    "Disciplinas do mês:\nBancos NoSQL\nEstatistica Aplicada\n\n"
    "Lembre de confirmar a sala.\n\nAtenciosamente,\nCoordenação — Escola Exemplo")
_EXPECTED_INVOICE = (
    "Emissão de nota fiscal — setembro/2026",
    "Olá, Prof Alfa,\n\nPara a sua nota fiscal de setembro/2026, estes são os valores estimados "
    "por nível de bônus (valor por aula: R$ 480,00):\n\n"
    "Sem bônus: R$ 1.920,00\nIBOPE 80–89%: R$ 2.400,00\n"
    "IBOPE 90%+: R$ 2.560,00 ← apurado (IBOPE 92%)\n\n"
    "Aulas consideradas:\nTurma AA_01\n05/09 (sáb) 08:00 — Bancos NoSQL\n"
    "12/09 (sáb) 08:00 — Bancos NoSQL\n26/09 (sáb) — Estatistica Aplicada\n\n"
    "Turma BB_02\n19/09 (sáb) 13:30 — Bancos NoSQL\n\nAtenciosamente,\nEscola Exemplo")


@pytest.mark.parametrize("template, conteudo, expected", [
    (T_SCHEDULE, "Lembre de confirmar a sala.", _EXPECTED_SCHEDULE),
    (T_INVOICE, "", _EXPECTED_INVOICE),
])
def test_render_byte_for_byte_and_deterministic(template, conteudo, expected):
    """The two e-mails the provider rendered (pinned by value before R-T13), byte for byte —
    now from the values the coordination COPIES into the tenant's free tags."""
    shas = set()
    for _ in range(2):
        values, missing = _fill(template, _ctx(conteudo=conteudo))
        assert missing == ()
        out = render_email(*template, values)
        assert out == expected
        shas.add(email_digest(*out))
    assert len(shas) == 1


def test_render_is_ONE_pass_a_marker_inside_a_value_stays_text():
    out = render_email("Aviso [mes]", "Recado: [conteudo]",
                       {"mes": "setembro/2026", "conteudo": "o [total] e o [nome]"})
    assert out == ("Aviso setembro/2026", "Recado: o [total] e o [nome]")
    # ...and the subject the same way: a NAME that looks like a marker stays the name.
    assert render_email("Para [nome]", "x", {"nome": "o [total]"}) == ("Para o [total]", "x")


def test_render_refuses_a_marker_with_no_value_and_a_multiline_subject():
    with pytest.raises(ValueError):
        render_email("Aviso", "[total]", {})
    with pytest.raises(ValueError):
        render_email("Aviso [mes]", "x", {"mes": "a\nb"})


def test_the_digest_is_of_subject_newline_body():
    import hashlib
    assert email_digest("a", "b") == hashlib.sha256(b"a\nb").hexdigest()
    assert month_words("2026-10") == "outubro/2026" and month_words("10") == ""

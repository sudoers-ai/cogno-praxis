"""The markers are ONE list for every persona — the eight generic ones — and a persona's own
values are the TENANT's tags (R-T13, 2026-10-22).

History, because the pins below are the third reading of the same question:

* until 2026-10-21 the thirteen markers were valid in every persona;
* 2026-10-22 (the owner: «vamos deixar somente as tags que servem para todos, tags especificas
  precisam ser adicionadas») the COORDINATOR's five were valid in its template only, refused
  elsewhere naming the coordination;
* R-T13, the same day (the owner: «preciso de algo genérico. Quando entrar uma persona nova, faço
  via tags personalizadas, senão teria que fazer via código» — and asked that the coordination
  follow that rule): no persona has markers in code. The five are the tenant's FREE tags; the
  coordination fills them from its tools. Every pin of the second reading is inverted here.

What is pinned:

* the twin — a SECRETARY template with ``[aulas]`` and the COORDINATOR's same template get the
  SAME verdict: refused as an unknown marker without the tenant's tag, saved with it;
* every name in every persona: a generic marker valid everywhere, a coordination name valid
  everywhere as the tenant's tag and nowhere without it — one verdict per name, whatever the
  persona;
* a refusal's sentences never depend on the persona, and the list it offers is the eight;
* the fill: a coordination name nobody declared is a removed tag — asked, never filled.

Everything here is invented.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.email_fields import (
    CUSTOM_TAG_REMOVED,
    EMAIL_FIELDS,
    FIELD_PROVIDERS,
    GENERIC_FIELDS,
    EmailContext,
    fields_for,
    fill_email_fields,
    known_markers,
    provider_of,
    template_fields,
    validate_template,
)

COORD = "COORDINATOR"
NO_PROVIDER = "PERSONA_ZETA_SEM_PROVIDER"
PERSONAS = (COORD, "SECRETARY", "BOOKKEEPER", "ARCHIVIST", NO_PROVIDER, "", None)

#: The coordination's five — typed HERE on purpose: the expectation, not a copy of the code.
COORDINATION = ("disciplinas", "aulas", "valor_por_aula", "valores_por_bonus", "total")
#: The eight generic markers, typed for the same reason.
GENERIC = ("nome", "email", "empresa", "mes", "data", "assinatura", "solicitante", "conteudo")
FREE = {n: "" for n in COORDINATION}
LISTED = ", ".join(f"[{n}]" for n in GENERIC)

#: The front desk's template that uses the classes.
T_SECRETARY = ("Agenda de [mes]", "Olá, [nome],\n\nAs suas aulas:\n[aulas]\n\n[assinatura]")


def _host_half(**kw) -> EmailContext:
    base = dict(recipient_name="Prof Alfa", recipient_email="alfa@captura.local",
                tenant_name="Escola Exemplo", month="2026-10", today=date(2026, 10, 7),
                persona_name="Assistente Vexa", requester_name="Coord Gama")
    base.update(kw)
    return EmailContext(**base)


def test_the_list_is_the_eight_for_every_persona():
    assert tuple(GENERIC_FIELDS) == GENERIC and tuple(EMAIL_FIELDS) == GENERIC
    assert dict(FIELD_PROVIDERS) == {}
    for persona in PERSONAS:
        assert known_markers(persona) == tuple(f"[{n}]" for n in GENERIC), persona


def test_a_secretary_template_with_aulas_gets_the_coordinators_verdict():
    """The twin of the second reading: there, the SECRETARY was refused naming the coordination
    and the COORDINATOR saved. Now both get one verdict — the tenant's tag decides."""
    refused = ("no corpo, [aulas] não é um marcador; os marcadores são " + LISTED,)
    for persona in ("SECRETARY", COORD):
        assert validate_template(*T_SECRETARY, persona=persona) == refused
        assert validate_template(*T_SECRETARY, persona=persona, custom_tags=FREE) == ()


@pytest.mark.parametrize("marker", GENERIC + COORDINATION)
def test_each_name_has_one_verdict_whatever_the_persona(marker):
    in_subject = marker not in ("aulas", "disciplinas", "valores_por_bonus", "conteudo")
    subject = f"Aviso [{marker}]" if in_subject else "Aviso"
    bare = {validate_template(subject, f"Texto: [{marker}]", persona=p) for p in PERSONAS}
    tagged = {validate_template(subject, f"Texto: [{marker}]", persona=p, custom_tags=FREE)
              for p in PERSONAS}
    assert len(bare) == 1 and tagged == {()}
    (verdict,) = bare
    if marker in GENERIC:
        assert verdict == ()
    else:
        assert verdict and all(f"[{marker}] não é um marcador" in r and "coordenação" not in r
                               for r in verdict)


@pytest.mark.parametrize("subject, body", [
    ("NF", "CPF: [cpf_cnpj]"),                     # removed by the owner
    ("Contrato", "[contrato]"),                    # a later phase
    ("Aviso", "[conteudo] e [conteudo]"),          # the free text twice
    ("", "[nome]"),                                # empty subject
    ("Total [aulas]", "corpo"),                    # a name nobody declared, in the subject
    ("Aviso", "[total] e [conteudo] e [conteudo]"),
])
def test_a_refusal_is_the_same_in_every_persona(subject, body):
    verdicts = {validate_template(subject, body, persona=p) for p in PERSONAS}
    assert len(verdicts) == 1 and verdicts != {()}


@pytest.mark.parametrize("persona", PERSONAS, ids=repr)
def test_an_unknown_marker_lists_the_eight(persona):
    (reason,) = validate_template("Aviso", "Olá [nmoe]", persona=persona)
    assert reason == "no corpo, [nmoe] não é um marcador; os marcadores são " + LISTED


def test_no_persona_fills_a_coordination_name_from_code():
    assert provider_of("aulas") is None
    assert all("aulas" not in fields_for(p) for p in PERSONAS)
    # the fill with no persona reads every marker — the eight
    assert fields_for(None) is EMAIL_FIELDS


def test_a_coordination_name_the_tenant_did_not_declare_is_asked_never_filled():
    values, missing = fill_email_fields(template_fields(*T_SECRETARY), _host_half())
    assert [(m.field, m.reason) for m in missing] == [("aulas", CUSTOM_TAG_REMOVED)]
    assert values == {"mes": "outubro/2026", "nome": "Prof Alfa", "assinatura": "Assistente Vexa"}


def test_control_declared_and_given_by_the_conversation_it_fills():
    records = [{"data": "08/10", "dia": "qui", "horário": "19:00",
                "disciplina": "Disciplina Exemplo", "turma": "Turma X"}]
    values, missing = fill_email_fields(template_fields(*T_SECRETARY), _host_half(
        custom_tags={"aulas": ""}, free_tag_values={"aulas": records}))
    assert missing == ()
    assert values["aulas"] == "Turma X\n08/10 (qui) 19:00 — Disciplina Exemplo"

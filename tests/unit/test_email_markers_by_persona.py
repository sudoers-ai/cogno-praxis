"""The DEFAULT markers are the eight generic ones; a persona's own markers are valid only in that
persona's template.

The owner's rule (2026-10-22): «vamos deixar somente as tags que servem para todos, tags
especificas precisam ser adicionadas». So two lists, by persona:

* **the default list** — :data:`GENERIC_FIELDS`, the eight markers every persona fills (the
  recipient, the tenant, the month, today, the persona that sends, the person who asked, the free
  text). :func:`known_markers` with no persona answers them, and a template of ANY persona may
  use them;
* **a persona's own markers** — what its :class:`FieldProvider` declares (today the
  COORDINATOR's five). They are valid in THAT persona's template and in no other: a template of
  any other persona — or one saved with no persona at all — that cites one is REFUSED at the
  save, with a sentence that names the marker and the persona it belongs to.

From 2026-10-21 until this rule the thirteen were valid in every persona (this file pinned that,
as ``test_email_markers_are_one_list.py``); every pin of that kind is inverted here. What did not
move: :data:`EMAIL_FIELDS` is still the union of the thirteen (the names the fill knows and the
names a company tag may never take), and the fill — what a persona can FILL — is unchanged.

What is pinned:

* the twin — a SECRETARY template with ``[aulas]`` is refused naming the coordination (it saved
  on the base), and the same template saves for the COORDINATOR (the control);
* every marker in every persona: a generic one is valid everywhere, a coordination one only for
  the COORDINATOR; the row table is derived from :data:`FIELD_PROVIDERS` and fails when a
  provider persona arrives without a row;
* the refusals that name no list are the same sentences in every persona, and the ones that list
  the markers list THIS persona's — eight, or the COORDINATOR's thirteen;
* the fill WITHOUT a persona, unchanged: a sentence handed over as ``schedule_error`` is carried
  verbatim, and with none the reason is the code's own. The control: the coordinator's context
  fills it. (The fill FOR a persona is ``test_email_fill_by_persona.py``.)

Everything here is invented.
"""

from __future__ import annotations

from datetime import date

import pytest

from cogno_praxis.email_fields import (
    EMAIL_FIELDS,
    FIELD_PROVIDERS,
    GENERIC_FIELDS,
    EmailClass,
    EmailContext,
    fields_for,
    fill_email_fields,
    known_markers,
    provider_of,
    template_fields,
    validate_template,
)

COORD = "COORDINATOR"
#: A persona with no provider of its own, as any of the host's other business personas is here.
NO_PROVIDER = "PERSONA_ZETA_SEM_PROVIDER"
PERSONAS = (COORD, "SECRETARY", "BOOKKEEPER", "ARCHIVIST", NO_PROVIDER, "", None)

#: The coordination's five — typed HERE on purpose: the expectation, not a copy of the code.
COORDINATION = ("disciplinas", "aulas", "valor_por_aula", "valores_por_bonus", "total")
#: The eight generic markers, typed for the same reason.
GENERIC = ("nome", "email", "empresa", "mes", "data", "assinatura", "solicitante", "conteudo")

#: The markers a template of each persona may use. A key per provider persona, plus the row of a
#: persona with none and the row of a template saved with no persona at all.
EXPECTED_MARKERS: "dict[object, tuple[str, ...]]" = {
    COORD: GENERIC + COORDINATION,
    NO_PROVIDER: GENERIC,
    None: GENERIC,
}

#: The front desk's template that uses the coordination's schedule.
T_SECRETARY = ("Agenda de [mes]", "Olá, [nome],\n\nAs suas aulas:\n[aulas]\n\n[assinatura]")

#: The sentence a host hands over for a provider this persona does not read (cogno-host's
#: ``send_email`` — the praxis does not write it, it carries it verbatim).
HOST_SENTENCE = ("o template usa [aulas], que esta persona não consegue preencher: só a "
                 "coordenação lê a agenda")


def _listed(persona) -> str:
    return ", ".join(f"[{n}]" for n in EXPECTED_MARKERS[COORD if persona == COORD else None])


def _coordination(where: str, name: str, persona) -> str:
    """The refusal of a coordination marker outside the COORDINATOR — the expectation, typed."""
    return (f"no {where}, [{name}] é uma tag da coordenação (COORDINATOR): só pode ser usada no "
            f"template dessa persona; os marcadores são {_listed(persona)}")


def _host_half(**kw) -> EmailContext:
    base = dict(recipient_name="Prof Alfa", recipient_email="alfa@captura.local",
                tenant_name="Escola Exemplo", month="2026-10", today=date(2026, 10, 7),
                persona_name="Assistente Vexa", requester_name="Coord Gama")
    base.update(kw)
    return EmailContext(**base)


# ── the two lists ────────────────────────────────────────────────────────────────────────────

def test_the_default_list_is_the_eight_generic_markers_and_the_union_stays_thirteen():
    """Inverted (was: «the list is thirteen markers and the same for every persona»)."""
    assert tuple(GENERIC_FIELDS) == GENERIC
    assert known_markers() == tuple(f"[{n}]" for n in GENERIC)
    assert known_markers("SECRETARY") == known_markers(NO_PROVIDER) == known_markers()
    assert known_markers(COORD) == tuple(f"[{n}]" for n in GENERIC + COORDINATION)
    # the union the fill knows, and a company tag may never take, is still the thirteen
    assert len(EMAIL_FIELDS) == 13 and set(EMAIL_FIELDS) == set(GENERIC + COORDINATION)


def test_every_provider_persona_has_a_row():
    """Derived: a persona that gains a provider without a row here fails, by name."""
    assert set(FIELD_PROVIDERS) <= set(EXPECTED_MARKERS), \
        set(FIELD_PROVIDERS) - set(EXPECTED_MARKERS)
    assert NO_PROVIDER not in FIELD_PROVIDERS
    for persona, p in FIELD_PROVIDERS.items():
        assert set(EXPECTED_MARKERS[persona]) == set(GENERIC) | p.field_names


@pytest.mark.parametrize("persona", list(EXPECTED_MARKERS), ids=str)
def test_each_row_lists_exactly_its_markers(persona):
    assert known_markers(persona) == tuple(f"[{n}]" for n in EXPECTED_MARKERS[persona])


def test_a_secretary_template_with_aulas_is_refused_naming_the_coordination():
    """The twin: on the base this saved. The control: the coordinator saves it."""
    assert validate_template(*T_SECRETARY, persona="SECRETARY") == (
        _coordination("corpo", "aulas", "SECRETARY"),)
    assert validate_template(*T_SECRETARY, persona=COORD) == ()


@pytest.mark.parametrize("marker", list(EMAIL_FIELDS))
@pytest.mark.parametrize("persona", PERSONAS, ids=repr)
def test_each_marker_by_persona(marker, persona):
    """Inverted (was: «every marker is valid in every persona»). A generic marker is valid in
    every persona; a coordination one only in the COORDINATOR's template — elsewhere, one refusal
    per place it is cited, each naming the coordination."""
    in_subject = marker not in ("aulas", "disciplinas", "valores_por_bonus", "conteudo")
    subject = f"Aviso [{marker}]" if in_subject else "Aviso"
    reasons = validate_template(subject, f"Texto: [{marker}]", persona=persona)
    exact = isinstance(persona, str) and persona.strip() == COORD
    if marker in GENERIC or exact:
        assert reasons == ()
    else:
        assert reasons == ((_coordination("assunto", marker, persona),) if in_subject else ()) \
            + (_coordination("corpo", marker, persona),)


@pytest.mark.parametrize("subject, body", [
    ("NF", "CPF: [cpf_cnpj]"),                     # removed by the owner
    ("Contrato", "[contrato]"),                    # a later phase
    ("Aviso", "[conteudo] e [conteudo]"),          # the free text twice
    ("", "[nome]"),                                # empty subject
])
def test_a_refusal_that_lists_no_markers_is_the_same_in_every_persona(subject, body):
    verdicts = {validate_template(subject, body, persona=p) for p in PERSONAS}
    assert len(verdicts) == 1 and verdicts != {()}


@pytest.mark.parametrize("subject, body", [
    ("Total [aulas]", "corpo"),                    # multi-line in the subject
    ("", "[aulas]"),                               # empty subject
    ("Aviso", "[total] e [conteudo] e [conteudo]"),
])
def test_a_coordination_marker_changes_the_verdict_by_its_sentences_only(subject, body):
    """Inverted (was: «the persona changes no verdict»). Outside the COORDINATOR the verdict is
    the COORDINATOR's plus one sentence per coordination marker cited — nothing else moves."""
    own = validate_template(subject, body, persona=COORD)
    assert own != ()
    for persona in PERSONAS:
        if persona == COORD:
            continue
        other = validate_template(subject, body, persona=persona)
        extra = [r for r in other if r not in own]
        assert [r for r in other if r in own] == list(own)
        assert extra and all("é uma tag da coordenação (COORDINATOR)" in r for r in extra), extra


@pytest.mark.parametrize("persona", PERSONAS, ids=repr)
def test_an_unknown_marker_lists_this_personas_markers(persona):
    """Inverted (was: «lists all thirteen in every persona»): the list a refusal offers is the
    list this persona's template may use — never a marker it would then refuse."""
    (reason,) = validate_template("Aviso", "Olá [nmoe]", persona=persona)
    assert reason == "no corpo, [nmoe] não é um marcador; os marcadores são " + _listed(persona)
    assert ("[aulas]" in reason) is (persona == COORD)


# ── filling: who has somewhere to read a marker from (unchanged) ─────────────────────────────

def test_field_providers_still_say_who_fills():
    assert provider_of("aulas") is FIELD_PROVIDERS[COORD]
    assert "aulas" in fields_for(COORD)
    assert "aulas" not in fields_for("SECRETARY")
    assert set(fields_for("SECRETARY")) == set(GENERIC_FIELDS)
    # the fill with no persona still reads every marker of the union — the save's default list
    # and the fill's are different questions (the module docstring says why)
    assert fields_for(None) is EMAIL_FIELDS


def test_aulas_comes_out_missing_with_the_sentence_the_host_hands_over():
    """The fill is not changed: a sentence a host hands over as ``schedule_error`` is carried
    verbatim and never wrapped, and the send then asks."""
    fields = template_fields(*T_SECRETARY)
    values, missing = fill_email_fields(fields, _host_half(schedule_error=HOST_SENTENCE))
    assert [m.field for m in missing] == ["aulas"]
    assert missing[0].reason == HOST_SENTENCE
    assert missing[0].sentence() == (f"[aulas] — {HOST_SENTENCE} (fonte: "
                                     f"{EMAIL_FIELDS['aulas'].source})")
    # the generic markers of the same template are filled all the same
    assert values == {"mes": "outubro/2026", "nome": "Prof Alfa", "assinatura": "Assistente Vexa"}


def test_without_the_hosts_sentence_the_reason_is_the_codes_own():
    _, missing = fill_email_fields(template_fields(*T_SECRETARY), _host_half())
    assert [m.field for m in missing] == ["aulas"]
    assert missing[0].reason == ("não encontro aulas de Prof Alfa em 10/2026 na agenda; "
                                 "confirma o mês?")


def test_the_coordinator_fills_aulas():
    """The control: the coordinator's own read fills the same template."""
    cls = (EmailClass(when=date(2026, 10, 8), time="19:00", subject="Disciplina Exemplo",
                      turma="Turma X"),)
    values, missing = fill_email_fields(template_fields(*T_SECRETARY), _host_half(classes=cls))
    assert missing == ()
    assert values["aulas"] == "Turma X\n08/10 (qui) 19:00 — Disciplina Exemplo"

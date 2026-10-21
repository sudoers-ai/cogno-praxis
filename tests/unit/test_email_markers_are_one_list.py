"""ONE list of e-mail markers for every persona; who can FILL each one is a separate question.

The owner's rule (2026-10-21): the template markers are standard for everything, not specific to
a persona. Two questions that E3 answered with one function are now two:

* **which markers EXIST** — :data:`EMAIL_FIELDS`, the same for every persona.
  :func:`validate_template` accepts any of them in any persona's template;
* **who has somewhere to READ a marker from** — :data:`FIELD_PROVIDERS` (:func:`fields_for`), as
  before. A marker the persona cannot fill comes out of :func:`fill_email_fields` as a
  :class:`Missing`, and the send asks the requester instead of sending.

What is pinned:

* the twin — a SECRETARY template with ``[aulas]`` SAVES (it was refused on the base);
* every marker in every persona, and the persona argument changes no verdict;
* the refusals that stay — an unknown marker, a removed one, a ``[`` that opens nothing — list
  the thirteen markers in every persona;
* the fill WITHOUT a persona, unchanged: a sentence handed over as ``schedule_error`` is carried
  verbatim, and with none the reason is the code's own («não encontro aulas …; confirma o mês?»).
  The control: the coordinator's context fills it. (The fill FOR a persona, with its own reason,
  is ``test_email_fill_by_persona.py``);
* :data:`FIELD_PROVIDERS` still says who fills (the SECRETARY cannot, the COORDINATOR can).

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
PERSONAS = (COORD, "SECRETARY", "BOOKKEEPER", "ARCHIVIST", "", None)

#: The front desk's template that uses the coordination's schedule.
T_SECRETARY = ("Agenda de [mes]", "Olá, [nome],\n\nAs suas aulas:\n[aulas]\n\n[assinatura]")

#: The sentence a host hands over for a provider this persona does not read (cogno-host's
#: ``send_email`` — the praxis does not write it, it carries it verbatim).
HOST_SENTENCE = ("o template usa [aulas], que esta persona não consegue preencher: só a "
                 "coordenação lê a agenda")


def _host_half(**kw) -> EmailContext:
    base = dict(recipient_name="Prof Alfa", recipient_email="alfa@captura.local",
                tenant_name="Escola Exemplo", month="2026-10", today=date(2026, 10, 7),
                persona_name="Assistente Vexa", requester_name="Coord Gama")
    base.update(kw)
    return EmailContext(**base)


def test_the_list_is_thirteen_markers_and_the_same_for_every_persona():
    assert len(EMAIL_FIELDS) == 13
    assert known_markers() == tuple(f"[{n}]" for n in EMAIL_FIELDS)


def test_a_secretary_template_with_aulas_saves():
    """The twin: on the base this was refused («[aulas] é um marcador da persona COORDINATOR»)."""
    assert validate_template(*T_SECRETARY, persona="SECRETARY") == ()
    assert validate_template(*T_SECRETARY, persona=COORD) == ()


@pytest.mark.parametrize("marker", list(EMAIL_FIELDS))
@pytest.mark.parametrize("persona", PERSONAS)
def test_every_marker_is_valid_in_every_persona(marker, persona):
    subject = "Aviso" if marker in ("aulas", "disciplinas", "valores_por_bonus", "conteudo") \
        else f"Aviso [{marker}]"
    assert validate_template(subject, f"Texto: [{marker}]", persona=persona) == ()


@pytest.mark.parametrize("subject, body", [
    ("Aviso", "Olá [nmoe]"),                       # unknown
    ("NF", "CPF: [cpf_cnpj]"),                     # removed by the owner
    ("Contrato", "[contrato]"),                    # a later phase
    ("Aviso", "Olá [Aulas]"),                      # a [ that opens no marker
    ("Total [aulas]", "corpo"),                    # multi-line in the subject
    ("Aviso", "[conteudo] e [conteudo]"),          # the free text twice
    ("", "[aulas]"),                               # empty subject
])
def test_the_persona_changes_no_verdict(subject, body):
    """The refusals that stay are the same sentences for every persona — the argument is inert."""
    verdicts = {validate_template(subject, body, persona=p) for p in PERSONAS}
    assert len(verdicts) == 1 and verdicts != {()}


@pytest.mark.parametrize("persona", PERSONAS)
def test_an_unknown_marker_lists_all_thirteen_in_every_persona(persona):
    (reason,) = validate_template("Aviso", "Olá [nmoe]", persona=persona)
    assert reason == ("no corpo, [nmoe] não é um marcador; os marcadores são "
                      + ", ".join(known_markers()))
    assert "[aulas]" in reason and "desta persona" not in reason


# ── filling: who has somewhere to read a marker from ─────────────────────────────────────────

def test_field_providers_still_say_who_fills():
    assert provider_of("aulas") is FIELD_PROVIDERS[COORD]
    assert "aulas" in fields_for(COORD)
    assert "aulas" not in fields_for("SECRETARY")
    assert set(fields_for("SECRETARY")) == set(GENERIC_FIELDS)


def test_aulas_comes_out_missing_with_the_sentence_the_host_hands_over():
    """A persona that cannot fill [aulas]: the host has no reader for the coordinator's provider
    there and hands its sentence over as ``schedule_error``. The fill is not changed: it already
    carries that sentence, verbatim and never wrapped, and the send then asks."""
    fields = template_fields(*T_SECRETARY)
    values, missing = fill_email_fields(fields, _host_half(schedule_error=HOST_SENTENCE))
    assert [m.field for m in missing] == ["aulas"]
    assert missing[0].reason == HOST_SENTENCE
    assert missing[0].sentence() == (f"[aulas] — {HOST_SENTENCE} (fonte: "
                                     f"{EMAIL_FIELDS['aulas'].source})")
    # the generic markers of the same template are filled all the same
    assert values == {"mes": "outubro/2026", "nome": "Prof Alfa", "assinatura": "Assistente Vexa"}


def test_without_the_hosts_sentence_the_reason_is_the_codes_own():
    """What the fill says when NOTHING was read and nobody said why: that it found no classes,
    and asks about the month. True of an empty schedule; misleading for a persona that cannot
    read one — which is why the host hands its sentence over."""
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
    assert values["aulas"] == "08/10 19:00 — Disciplina Exemplo — Turma X"

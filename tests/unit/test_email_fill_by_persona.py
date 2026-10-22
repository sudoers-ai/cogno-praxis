"""The fill, PER PERSONA: a template with all thirteen markers, filled FOR each persona.

The owner's order (2026-10-21): «essa parte do template do e-mail precisa estar bem feita e
validada com testes por persona». Since 2026-10-22 a template may use the eight generic markers
and its OWN persona's (``validate_template`` refuses another persona's, so only the COORDINATOR's
template saves with all thirteen); what a persona can FILL is :func:`fields_for`, and the fill is
unchanged — it is asked here with every marker, as a host whose stored template predates the rule
would ask it. ``fill_email_fields(…, persona=X)``
fills, for X, the markers X has somewhere to read from, and returns each other one as a
:class:`Missing` that names the marker and WHO reads it — never a value taken from a context X was
not the reader of.

The matrix is DERIVED: its rows are every persona :data:`FIELD_PROVIDERS` declares plus «a persona
with no provider», and the test fails when a provider's persona arrives without a row. The praxis
does not know the host's persona catalogue (it does not import the host); the matrix over that
catalogue — every business persona the host ships — is the host's
(``tests/unit/test_send_email_by_persona.py`` in cogno-host), and it reads these same rows.

Everything here is invented.
"""

from __future__ import annotations

import pytest

from cogno_praxis.email_fields import (
    EMAIL_FIELDS,
    FIELD_PROVIDERS,
    GENERIC_FIELDS,
    fill_email_fields,
    template_fields,
    validate_template,
)
from tests.unit.test_email_fields import _ctx, _svc

#: All thirteen markers: the multi-line and free-text ones in the body only.
T_ALL = ("Aviso de [mes] — [empresa] — [nome] — [email] — [data] — [assinatura] — [solicitante] "
         "— [valor_por_aula] — [total]",
         "[conteudo]\n\n[aulas]\n\n[disciplinas]\n\n[valores_por_bonus]")

#: A persona with NO provider: what any of the host's other business personas is, here.
NO_PROVIDER = "PERSONA_ZETA_SEM_PROVIDER"

#: The expected row per persona: the markers it FILLS. Everything else must come out `missing`.
#: A key per provider persona, plus the row of a persona with none.
EXPECTED_FILLS: "dict[str, frozenset[str]]" = {
    "COORDINATOR": frozenset(EMAIL_FIELDS),
    NO_PROVIDER: frozenset(GENERIC_FIELDS),
}


def _full_context():
    """A context that HOLDS every value — the coordinator's read included — so a marker that
    comes out missing is missing because of the persona, never because the data was absent."""
    return _ctx(_svc(ibope="92"), conteudo="Bom mês!", today=__import__("datetime").date(2026, 9, 7),
                persona_name="Assistente Vexa", requester_name="Coord Gama")


#: The coordination's sentence for each of its markers in :data:`T_ALL`, where it is cited.
_REFUSED_OUTSIDE = ("no assunto, [valor_por_aula]", "no assunto, [total]", "no corpo, [aulas]",
                    "no corpo, [disciplinas]", "no corpo, [valores_por_bonus]")


def test_the_template_uses_all_thirteen_and_is_valid_only_for_the_row_that_fills_them():
    """Inverted (was: «valid for every row»): only the persona whose provider declares the five
    may SAVE a template that uses them; every other row is refused once per coordination marker,
    each sentence naming the coordination."""
    assert set(template_fields(*T_ALL)) == set(EMAIL_FIELDS) and len(EMAIL_FIELDS) == 13
    for persona, fills in EXPECTED_FILLS.items():
        reasons = validate_template(*T_ALL, persona=persona)
        if fills == frozenset(EMAIL_FIELDS):
            assert reasons == (), (persona, reasons)
            continue
        assert [r.split(" é uma tag da coordenação (COORDINATOR):", 1)[0] for r in reasons] == \
            list(_REFUSED_OUTSIDE), (persona, reasons)


def test_every_provider_persona_has_a_row():
    """Derived: a persona that gains a provider without a row here fails, by name."""
    assert set(FIELD_PROVIDERS) <= set(EXPECTED_FILLS), set(FIELD_PROVIDERS) - set(EXPECTED_FILLS)
    assert NO_PROVIDER not in FIELD_PROVIDERS


@pytest.mark.parametrize("persona", sorted(EXPECTED_FILLS))
def test_the_thirteen_markers_filled_for_each_persona(persona):
    values, missing = fill_email_fields(template_fields(*T_ALL), _full_context(), persona=persona)
    fills = EXPECTED_FILLS[persona]
    assert set(values) == fills
    assert {m.field for m in missing} == set(EMAIL_FIELDS) - fills
    for m in missing:
        owner = next(p for p in FIELD_PROVIDERS.values() if m.field in p.field_names)
        # the reason names the marker and WHO reads it
        assert m.reason == (f"o template usa [{m.field}], que esta persona não consegue "
                            f"preencher: só a {owner.label} ({owner.persona}) o lê")
        assert m.source == EMAIL_FIELDS[m.field].source


def test_a_marker_the_persona_cannot_fill_is_never_taken_from_the_context():
    """The context holds the classes; a persona that is not their reader still gets them missing."""
    values, _ = fill_email_fields(("aulas", "nome"), _full_context(), persona=NO_PROVIDER)
    assert "aulas" not in values and values["nome"]


def test_control_no_persona_fills_from_the_context_as_before():
    values, missing = fill_email_fields(template_fields(*T_ALL), _full_context())
    assert missing == () and set(values) == set(EMAIL_FIELDS)
    # …and the persona that reads everything gets byte for byte the same values
    same, _ = fill_email_fields(template_fields(*T_ALL), _full_context(), persona="COORDINATOR")
    assert same == values

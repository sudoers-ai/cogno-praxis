"""The fill, PER PERSONA: one template — the eight markers and the coordination's five as the
tenant's tags — filled the SAME for every persona (R-T13, 2026-10-22).

The owner's order (2026-10-21): «essa parte do template do e-mail precisa estar bem feita e
validada com testes por persona»; and (2026-10-22) «preciso de algo genérico. Quando entrar uma
persona nova, faço via tags personalizadas, senão teria que fazer via código». From E3 until R-T13
the coordination's five were filled by its field provider and only for the COORDINATOR; they are
the tenant's FREE tags now, filled from what the persona copied from its tools, and
``fill_email_fields(…, persona=X)`` answers the same for every X.

The rows are DERIVED: every persona :data:`FIELD_PROVIDERS` declares (none — the test fails the
day one arrives without a row), the persona that had a provider, and one nobody ships. The praxis
does not know the host's persona catalogue (it does not import the host); the matrix over that
catalogue is the host's (``hostbench``'s ``email_templates_por_persona``).

Everything here is invented.
"""

from __future__ import annotations

import pytest

from cogno_praxis.email_fields import (
    FIELD_PROVIDERS,
    GENERIC_FIELDS,
    fill_email_fields,
    template_fields,
    validate_template,
)
from tests.unit.test_email_fields import FIVE, FREE, _ctx

#: The eight markers and the five tags: the multi-line and free-text ones in the body only.
T_ALL = ("Aviso de [mes] — [empresa] — [nome] — [email] — [data] — [assinatura] — [solicitante] "
         "— [valor_por_aula] — [total]",
         "[conteudo]\n\n[aulas]\n\n[disciplinas]\n\n[valores_por_bonus]")

#: The persona that HAD a provider, and one nobody ships.
ROWS = ("COORDINATOR", "PERSONA_ZETA_SEM_PROVIDER", *FIELD_PROVIDERS)


def _full_context():
    return _ctx(conteudo="Bom mês!", today=__import__("datetime").date(2026, 9, 7),
                persona_name="Assistente Vexa", requester_name="Coord Gama")


def test_the_template_uses_the_eight_and_the_five_and_is_valid_for_every_row():
    assert set(template_fields(*T_ALL)) == set(GENERIC_FIELDS) | set(FIVE)
    for persona in ROWS:
        assert validate_template(*T_ALL, persona=persona, custom_tags=FREE) == (), persona


def test_no_persona_has_a_provider():
    assert dict(FIELD_PROVIDERS) == {}


@pytest.mark.parametrize("persona", ROWS)
def test_every_row_fills_everything_and_the_same_bytes(persona):
    values, missing = fill_email_fields(template_fields(*T_ALL), _full_context(), persona=persona)
    assert missing == ()
    assert values == fill_email_fields(template_fields(*T_ALL), _full_context())[0]


def test_control_without_the_tenants_tags_every_row_asks_the_same():
    """The same template on a tenant that declared none of the five: each is a removed tag for
    every row, alike — never filled from anywhere."""
    ctx = _full_context()
    ctx = type(ctx)(**{**ctx.__dict__, "custom_tags": {}})
    answers = {p: fill_email_fields(template_fields(*T_ALL), ctx, persona=p)[1] for p in ROWS}
    assert len(set(answers.values())) == 1
    assert {m.field for m in answers["COORDINATOR"]} == set(FIVE)

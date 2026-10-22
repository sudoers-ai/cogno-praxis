"""The SCOPE of a company tag — every persona, or the personas the tenant names (R-T16).

The owner (2026-10-22): «são por persona. Mas no caso as que existem são só do coordinator». The
coordination's five tags were offered in every persona's «E-mails» tab, where the secretary and the
bookkeeper have no tool that reads them. A tag may now carry a scope, ``{name: [persona id, …]}``;
no scope (absent, empty) is every persona, the behaviour of before. What is pinned, one line each:

* the twin — the five scoped to the COORDINATOR: a SECRETARY or BOOKKEEPER template that cites one
  is REFUSED naming the scope, the COORDINATOR's is accepted (on the base ``tag_scopes=`` does not
  exist: every test of the twin is red there);
* the control — a GLOBAL tag (no scope) answers the same in every persona, byte for byte the
  verdict with no scopes at all;
* the refusal is the CALLER's sentence (``scope_refusal``) — the host names a persona as its panel
  does — and the ids' sentence when the caller has none, fails or answers no text;
* an out-of-scope tag is never LISTED among the markers a refusal says the persona may use;
* two personas in a scope are named in the order of their ids;
* the save door (``normalise_custom_tag_scopes``): ids of the host's catalogue only, every refusal
  named, nothing stored on any refusal; the turn door (``parse_custom_tag_scopes``) keeps what the
  save would keep and never WIDENS a scope over an id the catalogue lost;
* the fill never fills an out-of-scope tag for that persona, fixed or free; ``persona=None`` reads
  no scope.

Everything here is invented.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.email_fields import EmailContext, fill_email_fields, template_fields

#: The host's catalogue of business personas, as it hands it to the save door — invented order.
CATALOGUE = ("SECRETARY", "BOOKKEEPER", "COORDINATOR", "CLOSER", "INTERVIEWER")
FIVE = ("aulas", "disciplinas", "valor_por_aula", "valores_por_bonus", "total")
#: The tenant's map: the coordination's five FREE, a GLOBAL fixed tag, a GLOBAL free one.
TAGS = {**{n: "" for n in FIVE}, "pix": "chave-exemplo-0001", "assunto_livre": ""}
SCOPES = {n: ("COORDINATOR",) for n in FIVE}

T_SCHEDULE = ("Cronograma de [mes]", "Olá [nome],\n\n[aulas]\n\nTotal: [total]\n\nPix: [pix]")
T_PIX = ("Pagamento — [empresa]", "Olá [nome], a chave é [pix]. [assunto_livre]")


def _validate(template, persona, **kw):
    return ef.validate_template(*template, persona=persona, custom_tags=TAGS, **kw)


# ── the twin: the five only in the COORDINATOR ──────────────────────────────────────────────────

@pytest.mark.parametrize("persona", ["SECRETARY", "BOOKKEEPER"])
def test_a_scoped_tag_is_refused_outside_its_scope_naming_it(persona):
    """RED on the base: ``tag_scopes`` is not a parameter there."""
    why = _validate(T_SCHEDULE, persona, tag_scopes=SCOPES)
    assert why == (
        "no corpo, [aulas] é uma tag da empresa só da persona COORDINATOR; este template é de "
        "outra persona",
        "no corpo, [total] é uma tag da empresa só da persona COORDINATOR; este template é de "
        "outra persona",
    )


def test_a_scoped_tag_is_accepted_in_its_scope():
    assert _validate(T_SCHEDULE, "COORDINATOR", tag_scopes=SCOPES) == ()


def test_the_twin_against_its_control_the_same_template_with_no_scopes():
    """The refusal is the SCOPE's: with no scopes the same SECRETARY template is valid."""
    assert _validate(T_SCHEDULE, "SECRETARY") == ()
    assert _validate(T_SCHEDULE, "SECRETARY", tag_scopes={}) == ()
    assert _validate(T_SCHEDULE, "SECRETARY", tag_scopes=SCOPES) != ()


# ── the control: a GLOBAL tag answers the same everywhere ───────────────────────────────────────

@pytest.mark.parametrize("persona", [*CATALOGUE, "PERSONA_ZETA", None])
def test_a_global_tag_is_unchanged_in_every_persona(persona):
    assert _validate(T_PIX, persona, tag_scopes=SCOPES) == _validate(T_PIX, persona) == ()


@pytest.mark.parametrize("persona", [*CATALOGUE, None])
def test_a_typo_reads_the_same_with_scopes_only_the_list_shrinks(persona):
    """A template with a typo: the sentence is the one of before, and the markers it LISTS are the
    ones this persona may use — the out-of-scope tags are not offered."""
    template = ("Aviso", "Olá [nmoe]")
    with_scopes = _validate(template, persona, tag_scopes=SCOPES)
    assert len(with_scopes) == 1
    listed = with_scopes[0].split("e os da empresa: ", 1)[1]
    in_scope = persona in (None, "COORDINATOR")
    for name in FIVE:
        assert (f"[{name}]" in listed) is in_scope, (persona, name)
    assert "[pix]" in listed and "[assunto_livre]" in listed
    if in_scope:
        assert with_scopes == _validate(template, persona)


def test_persona_none_reads_no_scope():
    assert _validate(T_SCHEDULE, None, tag_scopes=SCOPES) == ()


def test_the_persona_id_is_compared_as_written():
    for persona in ("coordinator", "COORDINATORS", "", " COORDINATOR "):
        why = _validate(T_SCHEDULE, persona, tag_scopes=SCOPES)
        assert (why == ()) is (persona == " COORDINATOR "), persona


# ── the refusal: the caller composes it; the ids' sentence is the floor ─────────────────────────

def test_the_callers_sentence_is_used_with_where_name_and_the_ids():
    seen = []

    def compose(where, name, scope):
        seen.append((where, name, scope))
        return f"[{name}] é uma tag só da persona Coordenação ({scope[0]})"

    why = _validate(("Aulas: [aulas]", "Total: [total]"), "SECRETARY", tag_scopes=SCOPES,
                    scope_refusal=compose)
    assert why == ("[aulas] é uma tag só da persona Coordenação (COORDINATOR)",
                   "[total] é uma tag só da persona Coordenação (COORDINATOR)")
    assert seen == [("assunto", "aulas", ("COORDINATOR",)), ("corpo", "total", ("COORDINATOR",))]


@pytest.mark.parametrize("compose", [
    lambda where, name, scope: 1 / 0,
    lambda where, name, scope: None,
    lambda where, name, scope: "   ",
    lambda where, name, scope: 7,
])
def test_a_composer_that_fails_still_refuses_with_the_ids(compose):
    why = _validate(("Aviso", "[aulas]"), "SECRETARY", tag_scopes=SCOPES, scope_refusal=compose)
    assert why == (ef.default_scope_refusal("corpo", "aulas", ("COORDINATOR",)),)


def test_two_personas_are_named_in_the_order_of_their_ids():
    scopes = {"aulas": ["COORDINATOR", "BOOKKEEPER", "COORDINATOR"]}
    why = _validate(("Aviso", "[aulas]"), "SECRETARY", tag_scopes=scopes)
    assert why == ("no corpo, [aulas] é uma tag da empresa só das personas BOOKKEEPER, "
                   "COORDINATOR; este template é de outra persona",)
    assert _validate(("Aviso", "[aulas]"), "BOOKKEEPER", tag_scopes=scopes) == ()
    assert ef.scope_words(("BOOKKEEPER",)) == "da persona BOOKKEEPER"


def test_every_occurrence_is_refused_like_an_unknown_marker():
    why = _validate(("[aulas]", "[aulas] e [aulas]"), "SECRETARY", tag_scopes=SCOPES)
    assert [w.split(",", 1)[0] for w in why] == ["no assunto", "no corpo", "no corpo"]


# ── the save door ───────────────────────────────────────────────────────────────────────────────

def test_the_save_door_stores_the_ids_stripped_deduplicated_sorted():
    stored, why = ef.normalise_custom_tag_scopes(
        {"aulas": [" COORDINATOR ", "BOOKKEEPER", "COORDINATOR"], "pix": [],
         "total": ["SECRETARY", "INTERVIEWER", "COORDINATOR", "CLOSER", "BOOKKEEPER"]},
        TAGS, CATALOGUE)
    assert why == ()
    assert stored == {"aulas": ("BOOKKEEPER", "COORDINATOR"),     # an empty list: every persona
                      "total": ("BOOKKEEPER", "CLOSER", "COORDINATOR", "INTERVIEWER", "SECRETARY")}


@pytest.mark.parametrize("raw, refusals", [
    ({"aulas": ["ARCHIVIST"]},
     ("o alcance de [aulas] nomeia «ARCHIVIST», que não é uma persona; as personas são "
      "SECRETARY, BOOKKEEPER, COORDINATOR, CLOSER, INTERVIEWER",)),
    ({"aulas": ["coordinator"]},
     ("o alcance de [aulas] nomeia um valor que não é um id de persona, que não é uma persona; "
      "as personas são SECRETARY, BOOKKEEPER, COORDINATOR, CLOSER, INTERVIEWER",)),
    ({"aulas": ["<script>"]},
     ("o alcance de [aulas] nomeia um valor que não é um id de persona, que não é uma persona; "
      "as personas são SECRETARY, BOOKKEEPER, COORDINATOR, CLOSER, INTERVIEWER",)),
    ({"aulas": [7]},
     ("o alcance de [aulas] nomeia um valor que não é um id de persona, que não é uma persona; "
      "as personas são SECRETARY, BOOKKEEPER, COORDINATOR, CLOSER, INTERVIEWER",)),
    ({"aulas": "COORDINATOR"}, ("o alcance de [aulas] é uma lista de personas",)),
    ({"aulas": None}, ("o alcance de [aulas] é uma lista de personas",)),
    ({"sala9": ["COORDINATOR"]}, ("o alcance de «sala9» não é de nenhuma tag da empresa",)),
    ({"nome": ["COORDINATOR"]}, ("o alcance de «nome» não é de nenhuma tag da empresa",)),
    ({"aulas": ["COORDINATOR"], "total": ["ARCHIVIST"]},
     ("o alcance de [total] nomeia «ARCHIVIST», que não é uma persona; as personas são "
      "SECRETARY, BOOKKEEPER, COORDINATOR, CLOSER, INTERVIEWER",)),
    (["aulas"], ("os alcances das tags são um objeto {nome: [personas]}",)),
])
def test_the_save_door_refuses_by_name_and_stores_nothing(raw, refusals):
    assert ef.normalise_custom_tag_scopes(raw, TAGS, CATALOGUE) == ({}, refusals)


def test_no_scopes_and_an_empty_catalogue():
    assert ef.normalise_custom_tag_scopes(None, TAGS, CATALOGUE) == ({}, ())
    assert ef.normalise_custom_tag_scopes({}, TAGS, CATALOGUE) == ({}, ())
    assert ef.normalise_custom_tag_scopes({"aulas": ["COORDINATOR"]}, TAGS, ()) == (
        {}, ("o alcance de [aulas] nomeia «COORDINATOR», que não é uma persona; as personas são "
             "nenhuma",))


def test_a_scope_for_a_fixed_tag_is_allowed():
    """A scope is about WHO may use the tag, fixed or free alike."""
    assert ef.normalise_custom_tag_scopes({"pix": ["BOOKKEEPER"]}, TAGS, CATALOGUE) == (
        {"pix": ("BOOKKEEPER",)}, ())


# ── the turn door ───────────────────────────────────────────────────────────────────────────────

def test_the_turn_door_keeps_what_the_save_would_keep():
    raw = {"aulas": ["COORDINATOR"], "total": ["COORDINATOR", "COORDINATOR"],
           "gone": ["COORDINATOR"], "pix": [], "disciplinas": "COORDINATOR",
           "valor_por_aula": ["COORDINATOR", 5], 7: ["COORDINATOR"]}
    assert ef.parse_custom_tag_scopes(raw, TAGS) == {"aulas": ("COORDINATOR",),
                                                     "total": ("COORDINATOR",)}
    assert ef.parse_custom_tag_scopes(None, TAGS) == {}
    assert ef.parse_custom_tag_scopes(["aulas"], TAGS) == {}


def test_an_id_the_catalogue_lost_narrows_the_tag_never_widens_it():
    scopes = ef.parse_custom_tag_scopes({"aulas": ["RETIRED_PERSONA"]}, TAGS)
    assert scopes == {"aulas": ("RETIRED_PERSONA",)}
    for persona in CATALOGUE:
        assert not ef.tag_in_scope("aulas", persona, scopes), persona


def test_tags_in_scope_filters_any_map_keyed_by_tag():
    assert list(ef.tags_in_scope(TAGS, "SECRETARY", SCOPES)) == ["pix", "assunto_livre"]
    assert ef.tags_in_scope(TAGS, "COORDINATOR", SCOPES) == TAGS
    assert ef.tags_in_scope({"aulas": "a dica", "pix": ""}, "BOOKKEEPER", SCOPES) == {"pix": ""}
    assert ef.tags_in_scope(TAGS, None, SCOPES) == TAGS
    assert ef.tags_in_scope("nope", "SECRETARY", SCOPES) == {}


# ── the fill ────────────────────────────────────────────────────────────────────────────────────

def _ctx(**kw) -> EmailContext:
    base = dict(recipient_name="Prof Alfa", recipient_email="alfa@captura.local",
                tenant_name="Escola Exemplo", month="2026-10", today=date(2026, 10, 7),
                persona_name="Assistente Vexa", requester_name="Coord Gama", custom_tags=TAGS,
                free_tag_values={"aulas": "duas aulas", "total": "R$ 10,00"})
    base.update(kw)
    return EmailContext(**base)


def test_the_fill_never_fills_an_out_of_scope_tag_for_that_persona():
    fields = template_fields(*T_SCHEDULE)
    ctx = _ctx(custom_tag_scopes=SCOPES)
    values, missing = fill_email_fields(fields, ctx, persona="SECRETARY")
    assert "aulas" not in values and "total" not in values
    assert values["pix"] == "chave-exemplo-0001"
    assert [(m.field, m.reason, m.source) for m in missing] == [
        ("aulas", "[aulas] é uma tag da empresa só da persona COORDINATOR: esta persona não a "
                  "preenche", ef.CUSTOM_TAG_SOURCE),
        ("total", "[total] é uma tag da empresa só da persona COORDINATOR: esta persona não a "
                  "preenche", ef.CUSTOM_TAG_SOURCE)]


def test_the_fill_in_scope_and_with_no_persona_is_the_one_of_before():
    fields = template_fields(*T_SCHEDULE)
    before = fill_email_fields(fields, _ctx(), persona="COORDINATOR")
    assert before[1] == ()
    assert fill_email_fields(fields, _ctx(custom_tag_scopes=SCOPES), persona="COORDINATOR") == before
    assert fill_email_fields(fields, _ctx(custom_tag_scopes=SCOPES)) == fill_email_fields(fields, _ctx())


def test_a_scoped_fixed_tag_is_not_filled_outside_its_scope():
    ctx = dataclasses.replace(_ctx(), custom_tag_scopes={"pix": ("BOOKKEEPER",)})
    values, missing = fill_email_fields(("pix", "nome"), ctx, persona="SECRETARY")
    assert "pix" not in values and values["nome"] == "Prof Alfa"
    assert [m.field for m in missing] == ["pix"]
    assert fill_email_fields(("pix",), ctx, persona="BOOKKEEPER")[0] == {"pix": "chave-exemplo-0001"}
